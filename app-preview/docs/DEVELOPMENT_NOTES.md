# Development Notes & Lessons Learned

This document captures the key issues encountered during development and the solutions implemented.

## Table of Contents

1. [PokerKit Integration Challenges](#pokerkit-integration-challenges)
2. [Statistics Tracking Bugs](#statistics-tracking-bugs)
3. [Information Hiding Issues](#information-hiding-issues)
4. [Knowledge Persistence Design](#knowledge-persistence-design)
5. [LLM Integration Nuances](#llm-integration-nuances)
6. [Multi-Agent Ensemble Issues](#multi-agent-ensemble-issues)
7. [Configuration Simplification](#configuration-simplification)

---

## PokerKit Integration Challenges

### Issue 1: Card Display Format

**Problem**: PokerKit's `str(card)` returns verbose strings like `"ACE OF HEARTS (Ah)"` instead of simple `"Ah"`.

**Impact**: Caused `TypeError: Card.__init__() missing 1 required positional argument: 'suit'` when parsing cards.

**Solution**: Use `card.rank` and `card.suit` properties directly:

```python
# ❌ Wrong
hole_cards = [Card(rank=str(c)[0], suit=str(c)[1]) for c in state.hole_cards[i]]

# ✅ Correct
hole_cards = [Card(rank=str(c.rank), suit=str(c.suit)) for c in state.hole_cards[i]]
```

### Issue 2: Non-Positive Starting Stacks

**Problem**: `ValueError: Cannot start hand: Non-positive starting stacks was supplied.` crashed tournaments.

**Cause**: Tournament tried to start new hands with players who had 0 chips.

**Solution**: Catch the exception and signal tournament end gracefully:

```python
def _play_hand(self) -> bool:
    try:
        self._env.start_hand()
    except ValueError as e:
        logger.info(f"Tournament ending: {e}")
        return False  # Signal tournament should end
```

### Issue 3: Pot Size Always 0.0

**Problem**: Hand results always showed `pot_size=0.0`.

**Cause**: `state.total_pot_amount` becomes 0 after PokerKit distributes the pot to winners.

**Solution**: Calculate pot from positive payoffs:

```python
# ❌ Wrong (reads post-distribution value)
pot_size = state.total_pot_amount

# ✅ Correct (sum of winnings)
pot_size = sum(p for p in state.payoffs if p > 0)
```

### Issue 4: Bet/Raise Null Checks

**Problem**: `TypeError` when comparing `float` to `None` for min/max raise amounts.

**Cause**: `min_completion_betting_or_raising_to_amount` and `max_completion_betting_or_raising_to_amount` can be `None`.

**Solution**: Add null-coalescing:

```python
min_amount = state.min_completion_betting_or_raising_to_amount or 0
max_amount = state.max_completion_betting_or_raising_to_amount or float('inf')
```

### Issue 5: Blinds Not Updating in PokerKit

**Problem**: Blind increases during tournament weren't being applied to new hands.

**Solution**: Recreate the PokerKit game instance when blinds change:

```python
def set_blinds(self, small_blind: int, big_blind: int) -> None:
    self.small_blind = small_blind
    self.big_blind = big_blind
    self._game = NoLimitTexasHoldem(
        automations=AI_AUTOMATIONS,
        raw_blinds_or_straddles=(self.small_blind, self.big_blind),
        min_bet=self.big_blind,
        # ... other params
    )
```

---

## Statistics Tracking Bugs

### Issue 6: VPIP/PFR Counted Per Action (Not Per Hand)

**Problem**: `hands_played`, `_vpip_hands`, and `_pfr_hands` were incremented on every action, not once per hand.

**Impact**: All percentage calculations were wildly incorrect (100%+ values).

**Solution**: Use hand-tracking sets to ensure single counting:

```python
# Track VPIP once per hand per player
vpip_key = f"{player_id}_vpip"
if hand_num not in self._hands_counted[vpip_key]:
    self._hands_counted[vpip_key].add(hand_num)
    stats._vpip_hands += 1
```

### Issue 7: Limp Frequency Always 0.0

**Problem**: Limp frequency was never being tracked despite having the counter.

**Cause**: No logic existed to detect limps (calling preflop without a prior raise).

**Solution**: Track preflop raises per hand and detect limps:

```python
# Initialize per-hand tracking
if hand_num not in self._preflop_raised:
    self._preflop_raised[hand_num] = False

# Track raises
if action.type in (ActionType.RAISE, ActionType.ALL_IN):
    self._preflop_raised[hand_num] = True

# Detect limp: call preflop when no one has raised
if action.type == ActionType.CALL and not self._preflop_raised[hand_num]:
    if hand_num not in self._hands_counted[limp_key]:
        self._hands_counted[limp_key].add(hand_num)
        stats._limp_hands += 1
```

### Issue 8: Aggression Stats Over-Counted

**Problem**: `_bets_and_raises` and `_calls` were counted for every action, inflating aggression factor.

**Cause**: Unlike VPIP/PFR, aggression tracking had no guard to prevent double-counting.

**Solution**: Track aggression once per street per hand:

```python
agg_key = f"{player_id}_agg_{street.value}"
if hand_num not in self._hands_counted[agg_key]:
    self._hands_counted[agg_key].add(hand_num)
    if action.type in (ActionType.BET, ActionType.RAISE, ActionType.ALL_IN):
        stats._bets_and_raises += 1
    elif action.type == ActionType.CALL:
        stats._calls += 1
```

### Issue 9: C-bet River Flag Not Set

**Problem**: `_track_river` incremented `_cbet_river_count` but didn't set `hand_state["cbet_river"] = True`.

**Impact**: Inconsistent with `_track_flop` and `_track_turn`, breaking future river-dependent stats.

**Solution**: Add the missing flag:

```python
if action.type in (ActionType.BET, ActionType.RAISE, ActionType.ALL_IN):
    hand_state["cbet_river"] = True  # Was missing
    stats._cbet_river_count += 1
```

---

## Information Hiding Issues

### Issue 10: Hole Cards Exposed to Observing Agents

**Problem**: When Agent A acts, Agent B's `observe_action()` received a `game_state` containing Agent A's hole cards.

**Risk**: Violates poker information hiding; could lead to cheating if method is extended.

**Solution**: Create a sanitized state for observers that hides the actor's hole cards:

```python
def observe_action(self, actor_id, action, game_state, street, hand_num):
    # game_state should not contain actor's hole cards
    # Only our own hole cards should be visible
    pass  # Current implementation doesn't use hole cards from state
```

### Issue 11: Action Key Mismatch in Hand History

**Problem**: Hand history displayed to LLM showed `"Player1 ? 100"` instead of proper action types.

**Cause**: `environment.py` stores actions with key `"action"`, but `poker_agent.py` read `"action_type"`.

**Solution**: Try both keys with fallback:

```python
# Format action - NOTE: environment.py uses "action" key, not "action_type"
action_type = action.get("action", action.get("action_type", "?"))
```

---

## Knowledge Persistence Design

### Issue 12: Agent D Knowledge Not Persisting

**Problem**: Agent D started fresh each tournament, losing accumulated knowledge.

**Design Decision**: Implement two knowledge persistence modes:
- **Agent D (Veteran)**: Loads calibrated stats + persisted knowledge, saves after tournament
- **Agent E (Newcomer)**: Always starts empty, discards knowledge after tournament

**Implementation**:

```python
# Agent D: Load and merge multiple knowledge sources
if strategy.has_shared_knowledge:
    calibrated_kb = KnowledgeBase.load_from_file("calibrated_stats.json")
    persisted_kb = KnowledgeBase.load_from_file("agent_d_knowledge.json")
    knowledge_base.merge_with(calibrated_kb)
    knowledge_base.merge_with(persisted_kb)

# Agent E: Always empty
else:
    knowledge_base = KnowledgeBase()
```

### Issue 13: Calibration Stats Overwritten

**Problem**: Running multiple calibration tournaments overwrote stats instead of accumulating.

**Solution**: Add `accumulate_with()` method that sums raw counters:

```python
class PlayerStatistics:
    def accumulate(self, other: "PlayerStatistics") -> None:
        """Sum raw counters from another instance."""
        self.hands_played += other.hands_played
        self._vpip_hands += other._vpip_hands
        self._pfr_hands += other._pfr_hands
        # ... all counters
        self.recalculate()  # Recompute percentages

class KnowledgeBase:
    def accumulate_with(self, other: "KnowledgeBase") -> None:
        for player_id, profile in other.profiles.items():
            if player_id in self.profiles:
                self.profiles[player_id].statistics.accumulate(profile.statistics)
            else:
                self.profiles[player_id] = profile
```

---

## LLM Integration Nuances

### Issue 14: Remote API Endpoint Support

**Requirement**: Support Ollama and other OpenAI-compatible endpoints.

**Solution**: Add priority-based endpoint configuration:

```python
@property
def use_remote(self) -> bool:
    return bool(self.remote_api_address and self.remote_api_key)

# Priority: Remote > Azure > Direct OpenAI
if settings.use_remote:
    client = AsyncOpenAI(base_url=settings.remote_api_address, api_key=settings.remote_api_key)
```

### Issue 15: Reasoning Effort Parameter

**Requirement**: Support `reasoning_effort` for compatible models.

**Solution**: Conditionally add to `ModelSettings`:

```python
model_settings_kwargs = {"temperature": settings.temperature}
if settings.reasoning_effort:
    model_settings_kwargs["reasoning"] = {"effort": settings.reasoning_effort}

self._agent = Agent(
    model_settings=ModelSettings(**model_settings_kwargs),
    # ...
)
```

### Issue 16: Hand History Context for LLM

**Problem**: Agents had no visibility into previous actions in the current hand.

**Impact**: LLM couldn't make informed decisions based on betting patterns.

**Solution**: Build comprehensive hand history in prompt:

```python
def _build_state_prompt(self, state, action_history):
    # Include street-by-street action history
    for street, actions in grouped_actions.items():
        lines.append(f"\n=== {street.upper()} ===")
        for action in actions:
            lines.append(f"  {player}: {action_type} {amount}")
```

---

## Multi-Agent Ensemble Issues

### Issue 17: Aggression Factor 0 When No Calls

**Problem**: Agent with 20 bets/raises and 0 calls showed `aggression_factor = 0.0` instead of very high.

**Cause**: Division by zero protection left default value (0.0) instead of indicating high aggression.

**Solution**: Cap at 10.0 when no calls but has aggression:

```python
if self._calls > 0:
    self.aggression_factor = self._bets_and_raises / self._calls
elif self._bets_and_raises > 0:
    self.aggression_factor = 10.0  # "Infinitely aggressive"
```

### Issue 18: EnsemblePokerAgent Missing `strategy` Property

**Problem**: `AttributeError: 'EnsemblePokerAgent' object has no attribute 'strategy'`

**Cause**: Orchestrator accessed `agent.strategy.has_shared_knowledge` but EnsemblePokerAgent only had `_strategy`.

**Solution**: Add property to expose strategy:

```python
@property
def strategy(self) -> StrategyConfig:
    return self._strategy
```

### Issue 19: Wrong Attribute Names for Statistics

**Problem**: `AttributeError: 'PlayerStatistics' object has no attribute 'cbet_flop'`

**Cause**: Code referenced `stats.cbet_flop` but actual attribute is `stats.cbet_flop_pct`.

**Solution**: Use correct attribute names:

```python
# ❌ Wrong
lines.append(f"C-bet Flop: {stats.cbet_flop:.1f}%")

# ✅ Correct  
lines.append(f"C-bet Flop: {stats.cbet_flop_pct:.1f}%")
```

### Issue 20: Undefined `Ante.OPTIONAL`

**Problem**: `NameError: name 'Ante' is not defined` in `set_blinds()`.

**Cause**: Copy-paste error used `Ante.OPTIONAL` constant that doesn't exist.

**Solution**: Use `self.ante` (the stored value):

```python
# ❌ Wrong
raw_antes=Ante.OPTIONAL

# ✅ Correct
raw_antes=self.ante
```

### Issue 21: Misleading Stats With Small Samples

**Problem**: Agent said "extremely aggressive with 100% VPIP" based on just 1 hand.

**Cause**: Raw percentages shown to LLM regardless of sample size. 1 hand = 100% VPIP technically.

**Solution**: Hide stats entirely when sample < 20 hands:

```python
def to_prompt_string(self) -> str:
    if self.hands_played < 20:
        return """Hands: {hands_played}
⚠️ INSUFFICIENT DATA - Statistics not meaningful yet.
DO NOT make reads or exploits based on this player.
Play GTO (Game Theory Optimal) against them."""
    # ... show stats for >= 20 hands
```

---

## Configuration Simplification

### Issue 22: Complex Multi-Endpoint Configuration

**Problem**: Separate env vars for OpenAI, Azure, and remote endpoints was confusing.

**Solution**: Unified configuration using standard OpenAI variables:

```bash
# Core (all endpoints)
OPENAI_API_KEY=your-key
OPENAI_MODEL=gpt-4o

# For Azure (add these)
OPENAI_BASE_URL=https://your-resource.openai.azure.com/
ENDPOINT_TYPE=azure
AZURE_OPENAI_API_VERSION=2025-03-01-preview

# Optional
TEMPERATURE=0.7
REASONING_EFFORT=medium
```

**Auto-detection**: If `ENDPOINT_TYPE=azure` or URL contains "azure", use Azure client.

**Tracing disabled**: Automatically for non-OpenAI endpoints to avoid API key errors.

---

## Recent Improvements

### Issue 23: Agent D and E Stats Format Inconsistency

**Problem**: Agent D showed brief one-line opponent stats while Agent E showed detailed multi-line format.

**Impact**: Made comparison between architectures unfair - Agent E had more context.

**Solution**: Unified stats format. Both agents now show:
```
=== OPPONENT STATISTICS ===
(Minimum 50 hands required for reliable exploitation)

agent_a (Stack: 1500):
  ⚠️ LOW SAMPLE (25 hands) - Stats unreliable, play GTO
  VPIP: 45.0%
  PFR: 35.0%
  ...
```

### Issue 24: No GTO Deviation Explanation

**Problem**: Agents didn't explain why they followed or deviated from GTO.

**Impact**: Hard to understand decision-making rationale.

**Solution**: Added `GTO_DEVIATION` field to agent output:
```
GTO_DEVIATION: Following GTO because opponent sample size is too small
ACTION: check
```

### Issue 25: Missing Equity/Pot Odds Tools

**Problem**: Agents couldn't calculate precise pot odds or hand equity.

**Solution**: Added three tools using PokerKit:
- `calculate_pot_odds(pot, to_call)` - Required equity to call
- `calculate_equity(hole_cards, board, opponents)` - Monte Carlo simulation
- `get_position_info(seat, button, players)` - Position analysis

### Issue 26: Knowledge Tools Redundant for Agent D

**Problem**: Agent D used tools to look up opponent stats, adding latency.

**Solution**: Injected stats directly into prompt (same as Agent E). Removed knowledge tools.

### Issue 27: Agent E GTO Analyst Had No Tools

**Problem**: GTO Analyst couldn't calculate equity or pot odds.

**Solution**: Added pot_odds, equity, and position tools to GTO Analyst.

---

---

## Tracking & Analysis Features

### Issue 28: WTSD Always 0% Despite Showdowns

**Problem**: WTSD (Went To Showdown) was always 0.0% for all agents, even after hundreds of hands.

**Cause**: PokerKit's `HandKilling` automation clears `state.hole_cards` after showdown. Our code checked `state.hole_cards[i]` which was already empty.

**Solution**: Read showdown participants from `HoleCardsShowingOrMucking` operations instead:

```python
# ❌ Wrong (hole_cards cleared by HandKilling automation)
for i, hole in enumerate(state.hole_cards):
    if hole and state.statuses[i]:
        shown_hands[i] = [...]

# ✅ Correct (read from operations)
for op in state.operations:
    if type(op).__name__ == 'HoleCardsShowingOrMucking':
        if op.hole_cards:  # Cards were shown (not mucked)
            shown_hands[op.player_index] = [...]
```

### Feature: GTO Deviation Tracking

**Purpose**: Measure whether exploitative deviations are actually profitable.

**Implementation**:
1. `GTODeviationTracker` in `utils.py` records each decision with `is_following_gto` flag
2. Orchestrator tracks profit/loss per hand per agent
3. At tournament end, calculates average profit for GTO vs deviation decisions

**Output**:
```
Agent D (Simple):
  - GTO Profit: +600 (avg: +7.5/hand)
  - Deviation Profit: +500 (avg: +16.7/hand)
  ✅ Deviations were PROFITABLE (avg +9.2/hand better)
```

### Feature: Structured Logging

**Purpose**: Enable detailed analysis of agent decisions.

**Implementation**:
- `LogCollector` captures all log messages during tournament
- `log_agent_decision()` helper adds structured fields to each decision
- Exported to JSON with separate fields for analysis

**Structured Fields**:
- `gto_analysis`, `exploit_analysis`, `gto_deviation`
- `is_following_gto` (boolean for filtering)
- `tools_used`, `cards`, `board`, `pot`, `stack`, `street`

### Feature: Tool Usage Tracking

**Purpose**: Monitor which tools agents use and when.

**Implementation**:
- `ToolUsageTracker` records tool calls per agent per hand
- `extract_tools_used()` parses `ToolCallItem` from Runner result

---

## Key Takeaways

1. **Test with real games early**: Many bugs only appeared during actual tournament play.

2. **Validate counter logic carefully**: Per-hand vs per-action counting is a common source of errors.

3. **PokerKit has quirks**: The library is powerful but has non-obvious behaviors (pot amount after distribution, verbose card strings, hole cards cleared after showdown).

4. **Information hiding matters**: Even if not currently exploited, exposing hidden information creates technical debt.

5. **Accumulation vs replacement**: For statistics, accumulating raw counters then recalculating percentages is more accurate than merging computed percentages.

6. **Log everything initially**: Detailed logging helped identify most bugs, though it should be reduced for production.

7. **Track state per-hand**: Many poker statistics require tracking what happened earlier in the same hand (e.g., who raised preflop for limp detection).

8. **Sample size matters**: Small sample statistics are misleading - better to hide them entirely than show unreliable numbers.

9. **Keep configuration simple**: Standard environment variable names reduce confusion and work across providers.

10. **Read from operations, not state**: PokerKit state can be modified by automations - operations provide the ground truth.

