# Project Structure & Team Delegation

This document outlines how the codebase is organized and how work can be distributed among team members.

---

## Module Overview

```
poc-pokerbot/
├── backend/
│   ├── main.py                 → Experiment Runner
│   ├── config.py               → Configuration
│   └── domain/
│       ├── game/               → Game Engine Integration
│       ├── player/             → Knowledge System
│       ├── agent/              → AI Agents
│       └── tournament/         → Orchestration
├── data/
│   ├── knowledge/              → Persistent Knowledge Store
│   └── results/                → Experiment Results
└── docs/                       → Documentation
```

---

## Team Responsibilities

| Area | Owner | Description | Dependencies |
|------|-------|-------------|--------------|
| **Game Engine** | Backend Dev | PokerKit integration, state management, rules enforcement | None |
| **Knowledge System** | Data Engineer | Statistics tracking, profile storage, accumulation logic | Game Engine (for events) |
| **Single Agent (D)** | ML/Prompt Engineer | Prompt design, tool integration, decision quality | Knowledge System |
| **Ensemble Agent (E)** | ML/Prompt Engineer | Multi-agent coordination, specialist prompts | Knowledge System |
| **Orchestration** | Backend Dev | Tournament flow, experiment runner, results collection | All components |
| **Analysis** | Data Analyst | Results interpretation, statistical significance, reporting | Results data |

---

## Parallel Workstreams

The following diagram shows which components can be developed independently:

```
┌─────────────────────────────────────────────────────────────────┐
│                        INDEPENDENT TRACKS                        │
├─────────────────┬─────────────────┬─────────────────────────────┤
│   Game Engine   │ Knowledge System│      Agent Development      │
│                 │                 │                             │
│  • PokerKit     │  • Statistics   │  ┌─────────┐  ┌─────────┐  │
│    wrapper      │    tracking     │  │ Agent D │  │ Agent E │  │
│  • State mgmt   │  • Persistence  │  │ (simple)│  │(ensemble│  │
│  • Hand eval    │  • Calibration  │  └─────────┘  └─────────┘  │
│                 │                 │       ↓            ↓        │
└────────┬────────┴────────┬────────┴───────┬───────────┬────────┘
         │                 │                │           │
         └─────────────────┴────────────────┴───────────┘
                                   │
                          ┌───────┴───────┐
                          │ Orchestration │
                          │  & Analysis   │
                          └───────────────┘
```

---

## Key Integration Points

### StructuredGameState (Game → Agents)

The main interface providing current game situation to agents.

| Field | Type | Description |
|-------|------|-------------|
| `hand_number` | int | Current hand identifier |
| `street` | Street | PREFLOP, FLOP, TURN, RIVER |
| `pot` | float | Current pot size |
| `community_cards` | list[Card] | Board cards |
| `players` | list[PlayerState] | All players at table |
| `hero_seat` | int | Agent's seat position |
| `current_bet` | float | Amount to call |
| `min_raise` / `max_raise` | float | Legal raise bounds |
| `legal_actions` | list[ActionType] | Valid actions (FOLD, CHECK, CALL, BET, RAISE, ALL_IN) |

**Properties**: `hero`, `opponents`, `pot_odds`, `get_hole_cards_str()`, `get_board_str()`

### Action History Entry (within StructuredGameState.action_history)

Each action during the hand is recorded as a dict in the `action_history` list:

| Field | Type | Description |
|-------|------|-------------|
| `player_index` | int | Seat of acting player |
| `player_name` | str | Name of acting player |
| `action` | str | "fold", "check", "call", "bet", "raise", "all_in" |
| `amount` | float \| None | Chip amount for bet/raise/call |
| `street` | str | "preflop", "flop", "turn", "river" |

Used by agents for contextual decisions and by `StatisticsTracker` for updating opponent profiles.

### Action (Agents → Game)

Agent's decision returned to the game engine.

| Field | Type | Description |
|-------|------|-------------|
| `type` | ActionType | FOLD, CHECK, CALL, BET, RAISE, ALL_IN |
| `amount` | float \| None | Chip amount for bet/raise/call |

### ActionDecision (LLM → Agent)

Structured output from LLM with reasoning (used with Pydantic `output_type`).

| Field | Type | Description |
|-------|------|-------------|
| `gto_analysis` | str | GTO reasoning (1-2 sentences) |
| `exploit_analysis` | str | Exploitation reasoning (1-2 sentences) |
| `gto_deviation` | str | "Following GTO because..." or "Deviating from GTO because..." |
| `action_type` | Literal | fold, check, call, bet, raise, all_in |
| `sizing` | BetSizing \| None | Bet sizing (absolute, bb_multiple, or pot_fraction) |
| `confidence` | float | 0.0 to 1.0 |

**Methods**: `to_action(game_state)` → Resolves to executable `Action`

### PlayerStatistics (Knowledge System)

Core poker metrics tracked per opponent.

| Field | Type | Description |
|-------|------|-------------|
| `hands_played` | int | Sample size |
| `vpip` | float | Voluntarily Put $ In Pot % |
| `pfr` | float | Pre-Flop Raise % |
| `three_bet_pct` | float | 3-bet frequency |
| `fold_to_three_bet` | float | Fold to 3-bet % |
| `cbet_flop_pct` | float | Continuation bet flop % |
| `aggression_factor` | float | (Bet + Raise) / Call ratio |
| `wtsd` | float | Went To ShowDown % |
| `wsd` | float | Won at ShowDown % |

**Properties**: `is_reliable` (>50 hands), `reliability_note`, `to_prompt_string()`

### KnowledgeBase (Player → Agents)

Container for opponent profiles, supports persistence.

| Method | Description |
|--------|-------------|
| `get_profile(player_id)` | Get PlayerProfile or None |
| `get_or_create_profile(player_id, name)` | Get or create new profile |
| `save_to_file(filepath)` | Persist to JSON |
| `load_from_file(filepath)` | Load from JSON |
| `accumulate_with(other)` | Add stats from another KB (for calibration) |

### HandResult (Game → Knowledge)

Result of a completed hand, used for statistics updates.

| Field | Type | Description |
|-------|------|-------------|
| `hand_number` | int | Hand identifier |
| `winners` | list[int] | Winning seat(s) |
| `pot_size` | float | Final pot |
| `showdown` | bool | True if went to showdown |
| `shown_hands` | dict[int, list[Card]] | Seat → revealed cards |
| `actions_by_street` | dict[Street, list] | Action history |

---

## Suggested Development Phases

### Phase 1: Foundation (Can be parallel)
- Game engine integration and testing
- Knowledge system data models
- Basic single-agent prompt

### Phase 2: Core Features (Requires Phase 1)
- Statistics tracking (VPIP, PFR, aggression)
- Single agent with tools (equity, pot odds)
- Tournament orchestration

### Phase 3: Advanced (Requires Phase 2)
- Ensemble agent architecture
- GTO deviation tracking
- Calibration mode

### Phase 4: Analysis (Requires Phase 3)
- Run experiments (100+ tournaments)
- Statistical analysis
- Results documentation

---

## Skills Needed

| Role | Skills | Focus Area |
|------|--------|------------|
| **Backend Developer** | Python, async, state machines | Game engine, orchestration |
| **ML/Prompt Engineer** | LLM prompting, OpenAI SDK | Agent behavior, decision quality |
| **Data Engineer** | Data modeling, JSON, persistence | Knowledge system, accumulation |
| **Data Analyst** | Statistics, visualization | Experiment analysis, conclusions |

---

## File Details

### Game Engine (`domain/game/`)

| File | Purpose |
|------|---------|
| `models.py` | Data structures: `StructuredGameState`, `Card`, `HandResult`, `Action` |
| `environment.py` | PokerKit wrapper, hand management, showdown detection |

### Knowledge System (`domain/player/`)

| File | Purpose |
|------|---------|
| `models.py` | `PlayerStatistics`, `PlayerProfile`, `KnowledgeBase` |
| `tracker.py` | `StatisticsTracker` - observes actions, updates stats |

### AI Agents (`domain/agent/`)

| File | Purpose |
|------|---------|
| `poker_agent.py` | Simple single-agent architecture (Agent D) |
| `ensemble_agent.py` | Multi-agent ensemble architecture (Agent E) |
| `specialists.py` | GTO Analyst, Exploit Analyst, Decision Maker |
| `models.py` | `ActionDecision`, `BetSizing` - structured LLM output |
| `prompts.py` | Shared exploitation guidelines |
| `utils.py` | Tool tracking, GTO deviation tracking |
| `tools/basic_tools.py` | Equity calculator, pot odds, position info |
| `strategies/base.py` | Agent personality configurations |

### Tournament (`domain/tournament/`)

| File | Purpose |
|------|---------|
| `orchestrator.py` | Tournament flow, agent coordination, results collection |

---

## Related Documentation

- **[EXPERIMENT.md](EXPERIMENT.md)** - Project goals, hypotheses, and challenges
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Technical architecture and data flows
- **[DEVELOPMENT_NOTES.md](DEVELOPMENT_NOTES.md)** - Issues encountered and solutions

