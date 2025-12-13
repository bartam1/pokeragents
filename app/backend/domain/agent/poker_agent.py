"""
Poker Agent - Main AI agent using OpenAI Agents SDK.

This is a simple agent that:
1. Takes game state as input
2. Uses LLM reasoning + optional tools to analyze the situation
3. Returns a poker action

The agent's behavior is shaped by:
- Strategy configuration (personality/style)
- Knowledge base (opponent stats - pre-loaded for Agent D, learned for Agent E)
"""

from agents import Agent, ModelSettings, Runner

from backend.config import Settings
from backend.domain.agent.models import ActionDecision
from backend.domain.agent.strategies.base import StrategyConfig
from backend.domain.agent.tools.basic_tools import POKER_TOOLS
from backend.domain.agent.utils import deviation_tracker, extract_tools_used
from backend.domain.game.models import Action, HandResult, StructuredGameState
from backend.domain.player.models import KnowledgeBase
from backend.domain.player.tracker import StatisticsTracker
from backend.logging_config import get_logger, log_agent_decision

logger = get_logger(__name__)


# System prompt for the poker agent
POKER_AGENT_PROMPT = """You are an AI poker player in a No-Limit Texas Hold'em tournament.

{strategy_instructions}

## CRITICAL: GTO IS YOUR DEFAULT STRATEGY

⚠️ **FOLLOW GTO UNLESS YOU HAVE STRONG EVIDENCE TO DEVIATE**

The GTO strategy is mathematically unexploitable. Only deviate when you have:
- High confidence opponent reads (100+ hands of data)
- A CLEAR, SPECIFIC exploitation opportunity
- The exploit suggests a DIFFERENT action than GTO

## Your Analysis Process
Think through THREE perspectives before deciding:

### 1. GTO ANALYSIS (Game Theory Optimal) - YOUR BASELINE
- First, use calculate_equity tool to get your hand's equity
- If facing a bet, use calculate_pot_odds tool to get required equity
- Then analyze position and stack-to-pot ratio
- This is your DEFAULT decision

### 2. EXPLOIT ANALYSIS  
- What do you know about your opponents' tendencies?
- Are they too loose/tight? Too passive/aggressive?
- What adjustments can you make to exploit their leaks?

⚠️ **Sample Size Determines If You Can Exploit:**
- **< 50 hands**: DO NOT EXPLOIT - Play GTO only
- **50-99 hands**: Use stats with CAUTION - only exploit extreme tendencies
- **100+ hands**: Stats are reliable - may exploit if clear opportunity

### 3. DECISION - Hard Rules
- **Default to GTO** - start with the GTO recommendation
- **Only deviate when**: Opponent has 100+ hands AND shows clear exploitable leak
- If in doubt, FOLLOW GTO
- Factor in tournament considerations (ICM, stack preservation)

## Available Actions
- FOLD: Give up the hand
- CHECK: Pass (when no bet to call)
- CALL: Match the current bet
- BET/RAISE [amount]: Put chips in (specify amount)
- ALL_IN: Put all chips in

## Response Format (JSON)
Respond with a structured JSON object containing:

- **gto_analysis**: Your GTO-based thinking (1-2 sentences)
- **exploit_analysis**: Opponent exploitation reasoning (1-2 sentences)
- **gto_deviation**: "Following GTO because..." or "Deviating from GTO because..."
- **action_type**: One of: fold, check, call, bet, raise, all_in
- **sizing**: For bet/raise, specify ONE of:
  - {{"bb_multiple": 3}} for 3x big blind
  - {{"pot_fraction": 0.75}} for 75% pot
  - {{"absolute": 150}} for exact chip amount
  - null for fold/check/call/all_in
- **confidence**: Number from 0.0 to 1.0

Example 1 (Following GTO - Default):
{{
  "gto_analysis": "With AKo in late position, standard play is to 3-bet for value.",
  "exploit_analysis": "Villain has only 35 hands - insufficient data for exploitation.",
  "gto_deviation": "Following GTO because opponent sample size is too small for reliable reads.",
  "action_type": "raise",
  "sizing": {{"bb_multiple": 3}},
  "confidence": 0.90
}}

Example 2 (Deviating - Only with strong evidence):
{{
  "gto_analysis": "With AKo, standard 3-bet sizing is 3x.",
  "exploit_analysis": "Villain has 150 hands, 55% VPIP, never folds to 3-bets - extreme calling station.",
  "gto_deviation": "Deviating from GTO because villain's extreme call frequency (150+ hands) justifies larger sizing.",
  "action_type": "raise",
  "sizing": {{"bb_multiple": 4}},
  "confidence": 0.85
}}
"""


class PokerAgent:
    """
    AI Poker Agent using OpenAI Agents SDK.

    Simple design:
    - One agent per player
    - Uses LLM reasoning for poker decisions
    - Tools for pot odds and opponent lookup
    """

    def __init__(
        self,
        player_id: str,
        strategy: StrategyConfig,
        knowledge_base: KnowledgeBase,
        settings: Settings,
    ):
        """
        Initialize the poker agent.

        Args:
            player_id: Unique identifier for this agent
            strategy: Strategy configuration (personality/style)
            knowledge_base: Knowledge of opponents (pre-loaded or empty)
            settings: Application settings (API keys, etc.)
        """
        self.player_id = player_id
        self.strategy = strategy
        self.knowledge_base = knowledge_base
        self._settings = settings
        self._tracker = StatisticsTracker(knowledge_base)

        # OpenAI client uses environment variables set by Settings.configure_openai_client()
        # No need for conditional logic - OPENAI_BASE_URL and OPENAI_API_KEY are set automatically

        # Build tools list - opponent stats are injected directly into prompt (no tools needed)
        tools = POKER_TOOLS.copy()

        # Build system prompt with strategy
        system_prompt = POKER_AGENT_PROMPT.format(
            strategy_instructions=strategy.to_prompt_instructions()
        )

        # Build model settings
        model_settings_kwargs = {"temperature": settings.temperature}
        if settings.reasoning_effort:
            model_settings_kwargs["reasoning"] = {"effort": settings.reasoning_effort}

        # Create the agent with structured output
        self._agent = Agent(
            name=f"PokerAgent_{player_id}",
            instructions=system_prompt,
            tools=tools,
            model=settings.model_name,
            model_settings=ModelSettings(**model_settings_kwargs),
            output_type=ActionDecision,  # Structured JSON output
        )

        logger.info(
            f"Created agent {player_id} with strategy '{strategy.name}', "
            f"has_knowledge={strategy.has_shared_knowledge}, "
            f"known_opponents={len(knowledge_base.profiles)}"
        )

    async def decide(self, game_state: StructuredGameState) -> ActionDecision:
        """
        Make a decision for the current game state.

        Args:
            game_state: Current state of the game from this agent's perspective

        Returns:
            ActionDecision with structured output from LLM
        """
        # Build the prompt describing the game state
        prompt = self._build_state_prompt(game_state)

        # Debug logging - print full prompt for testing
        logger.debug(f"Agent {self.player_id} analyzing hand #{game_state.hand_number}")
        logger.debug(f"Agent {self.player_id} PROMPT:\n{'=' * 60}\n{prompt}\n{'=' * 60}")

        # Run the agent - result.final_output is ActionDecision (structured)
        result = await Runner.run(self._agent, prompt)
        decision: ActionDecision = result.final_output

        # Extract tools used during this decision
        tools_used = extract_tools_used(result)

        # Resolve to Action object
        action = decision.to_action(game_state)
        hole_cards = game_state.get_hole_cards_str()
        board = (
            " ".join(str(c) for c in game_state.community_cards)
            if game_state.community_cards
            else ""
        )

        # Determine if following GTO based on deviation text
        is_following_gto = decision.gto_deviation.lower().startswith("following gto")

        # Console logging (human readable)
        logger.info(f"  [{self.player_id}] Cards: {hole_cards}")
        logger.info(
            f"    GTO: {decision.gto_analysis[:100]}{'...' if len(decision.gto_analysis) > 100 else ''}"
        )
        logger.info(
            f"    Exploit: {decision.exploit_analysis[:100]}{'...' if len(decision.exploit_analysis) > 100 else ''}"
        )
        logger.info(
            f"    📐 GTO Deviation: {decision.gto_deviation[:100]}{'...' if len(decision.gto_deviation) > 100 else ''}"
        )
        if tools_used:
            logger.info(f"    🔧 Tools: {', '.join(tools_used)}")

        # Structured logging for JSON export
        log_agent_decision(
            logger=logger,
            agent_id=self.player_id,
            hand_num=game_state.hand_number,
            action=action.type.value,
            amount=action.amount,
            cards=hole_cards,
            confidence=decision.confidence,
            gto_analysis=decision.gto_analysis,
            exploit_analysis=decision.exploit_analysis,
            gto_deviation=decision.gto_deviation,
            is_following_gto=is_following_gto,
            tools_used=tools_used,
            pot=game_state.pot,
            stack=game_state.hero.stack,
            board=board,
            street=game_state.street.value,
        )

        # Track GTO deviation for analysis
        deviation_tracker.record_decision(
            agent_id=self.player_id,
            hand_num=game_state.hand_number,
            action=action.type.value,
            is_following_gto=is_following_gto,
            deviation_reason=decision.gto_deviation if not is_following_gto else "",
            amount=action.amount,
        )

        return decision

    def _build_state_prompt(self, state: StructuredGameState) -> str:
        """Build a prompt describing the current game state in poker client format."""
        hero = state.hero
        hole_cards = state.get_hole_cards_str()

        # Calculate blind positions
        num_players = len(state.players)
        sb_seat = (state.button_seat + 1) % num_players
        bb_seat = (state.button_seat + 2) % num_players

        # Build formatted hand history
        lines = []

        # Seat info with positions
        lines.append(f"=== HAND #{state.hand_number} ===")
        for player in state.players:
            position_markers = []
            if player.seat == state.button_seat:
                position_markers.append("BTN")
            if player.seat == sb_seat:
                position_markers.append("SB")
            if player.seat == bb_seat:
                position_markers.append("BB")
            if player.seat == state.hero_seat:
                position_markers.append("Hero")

            marker = f"({', '.join(position_markers)})" if position_markers else ""
            lines.append(f"Seat {player.seat + 1}: {player.name} ({player.stack:.0f}) {marker}")

        # Blinds and hole cards
        lines.append("")
        lines.append("*** ANTE/BLINDS ***")
        sb_player = next((p for p in state.players if p.seat == sb_seat), None)
        bb_player = next((p for p in state.players if p.seat == bb_seat), None)
        if sb_player:
            lines.append(f"  {sb_player.name} posts small blind {state.small_blind:.0f}")
        if bb_player:
            lines.append(f"  {bb_player.name} posts big blind {state.big_blind:.0f}")
        lines.append(f"  Dealt to {hero.name} [{hole_cards}]")

        # Format actions by street
        current_street = None
        for action in state.action_history:
            action_street = action.get("street", "preflop")

            # Show street header with board when entering new street
            if action_street != current_street:
                current_street = action_street
                if action_street == "preflop":
                    lines.append("")
                    lines.append("*** PREFLOP ***")
                elif action_street == "flop":
                    board_cards = (
                        state.community_cards[:3] if len(state.community_cards) >= 3 else []
                    )
                    board_str = " ".join(str(c) for c in board_cards)
                    lines.append("")
                    lines.append(f"*** FLOP *** [{board_str}]")
                elif action_street == "turn":
                    flop_str = " ".join(str(c) for c in state.community_cards[:3])
                    turn_card = state.community_cards[3] if len(state.community_cards) >= 4 else "?"
                    lines.append("")
                    lines.append(f"*** TURN *** [{flop_str}][{turn_card}]")
                elif action_street == "river":
                    flop_turn_str = " ".join(str(c) for c in state.community_cards[:4])
                    river_card = (
                        state.community_cards[4] if len(state.community_cards) >= 5 else "?"
                    )
                    lines.append("")
                    lines.append(f"*** RIVER *** [{flop_turn_str}][{river_card}]")

            # Format action with pot and stack context
            action_type = action.get("action", action.get("action_type", "?"))
            amount = action.get("amount")
            player_name = action.get("player_name", "?")
            pot = action.get("pot_before_action")
            stacks = action.get("stacks_before", {})

            # Build stacks string (abbreviated names)
            stacks_str = (
                " ".join(
                    f"{name.replace('Agent ', '')}={int(stack)}" for name, stack in stacks.items()
                )
                if stacks
                else ""
            )

            if amount and pot:
                lines.append(
                    f"  {player_name} {action_type} {amount:.0f} [before: pot={pot:.0f}, stacks: {stacks_str}]"
                )
            elif amount:
                lines.append(f"  {player_name} {action_type} {amount:.0f}")
            else:
                lines.append(f"  {player_name} {action_type}")

        # Show current street header if no actions yet or we're on a new street
        if not state.action_history:
            lines.append("")
            lines.append("*** PREFLOP ***")
        elif current_street != state.street.value:
            # We're on a new street with no actions yet
            if state.street.value == "flop":
                board_str = " ".join(str(c) for c in state.community_cards[:3])
                lines.append("")
                lines.append(f"*** FLOP *** [{board_str}]")
            elif state.street.value == "turn":
                flop_str = " ".join(str(c) for c in state.community_cards[:3])
                turn_card = state.community_cards[3] if len(state.community_cards) >= 4 else "?"
                lines.append("")
                lines.append(f"*** TURN *** [{flop_str}][{turn_card}]")
            elif state.street.value == "river":
                flop_turn_str = " ".join(str(c) for c in state.community_cards[:4])
                river_card = state.community_cards[4] if len(state.community_cards) >= 5 else "?"
                lines.append("")
                lines.append(f"*** RIVER *** [{flop_turn_str}][{river_card}]")

        # Current decision point
        to_call = state.current_bet - hero.current_bet
        lines.append("")
        lines.append("=== YOUR TURN ===")
        lines.append(f"Pot: {state.pot:.0f} | To Call: {to_call:.0f}")
        lines.append(f"Your Stack: {hero.stack:.0f}")
        lines.append(f"Legal Actions: {[a.value for a in state.legal_actions]}")
        if state.min_raise > 0:
            lines.append(f"Min Raise: {state.min_raise:.0f} | Max Raise: {state.max_raise:.0f}")

        # Opponent reads (same format as Agent E)
        from backend.domain.player.models import MIN_RELIABLE_SAMPLE_SIZE

        lines.append("")
        lines.append("=== OPPONENT STATISTICS ===")
        lines.append(
            f"(Minimum {MIN_RELIABLE_SAMPLE_SIZE} hands required for reliable exploitation)"
        )

        for opp in state.opponents:
            profile = self.knowledge_base.get_profile(opp.name)
            if profile and profile.statistics.hands_played > 0:
                stats = profile.statistics
                lines.append(f"\n{opp.name} (Stack: {opp.stack:.0f}):")

                if stats.hands_played < 20:
                    # Don't show misleading stats with tiny samples
                    lines.append(f"  Hands: {stats.hands_played}")
                    lines.append("  ⚠️ INSUFFICIENT DATA - Stats not meaningful")
                    lines.append("  DO NOT exploit - Play GTO")
                else:
                    lines.append(f"  {stats.reliability_note}")
                    lines.append(f"  VPIP: {stats.vpip:.1f}%")
                    lines.append(f"  PFR: {stats.pfr:.1f}%")
                    lines.append(f"  Limp: {stats.limp_frequency:.1f}%")
                    lines.append(f"  Aggression: {stats.aggression_factor:.2f}")
                    lines.append(f"  C-bet Flop: {stats.cbet_flop_pct:.1f}%")
                    lines.append(f"  Fold to 3-bet: {stats.fold_to_three_bet:.1f}%")
                    lines.append(f"  WTSD: {stats.wtsd:.1f}%")
            else:
                lines.append(f"\n{opp.name} (Stack: {opp.stack:.0f}): No data - Play GTO")

        return "\n".join(lines)

    def observe_action(
        self,
        player_id: str,
        player_name: str,
        action: Action,
        game_state: StructuredGameState,
    ) -> None:
        """
        Observe another player's action (for learning).

        Delegates to the StatisticsTracker, which updates VPIP/PFR/limp,
        3-bet and c-bet opportunities, aggression, and sets per-hand flags
        used for WTSD/WSD.
        """
        if player_id == self.player_id:
            return

        self._tracker.observe_action(
            player_id=player_id,
            player_name=player_name,
            action=action,
            game_state=game_state,
        )

    def start_hand_tracking(self, player_ids: list[str]) -> None:
        """Initialize per-hand tracking state for this agent's knowledge."""
        self._tracker.start_hand(player_ids)

    def end_hand_tracking(
        self,
        hand_result: HandResult,
        player_names: list[str],
    ) -> None:
        """Finalize per-hand stats (WTSD/WSD) after a hand is complete."""
        self._tracker.end_hand(player_names, hand_result)
