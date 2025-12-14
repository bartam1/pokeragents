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


# =============================================================================
# System Prompts
# =============================================================================

# Baseline prompt for Agents A/B/C - follow your personality
BASELINE_AGENT_PROMPT = """You are an AI poker player in a No-Limit Texas Hold'em tournament.

{strategy_instructions}

**STAY IN CHARACTER** - Play according to your style, not "optimally".

Use calculate_equity and calculate_pot_odds tools as needed.

## Response Format
{{
  "gto_analysis": "What GTO would suggest (1 sentence)",
  "exploit_analysis": "How your style applies (1 sentence)",
  "is_following_gto": true,
  "gto_deviation": "Following my style because...",
  "action_type": "fold|check|call|bet|raise|all_in",
  "sizing": {{"pot_fraction": 0.75}} or {{"bb_multiple": 3}} or null,
  "confidence": 0.0-1.0
}}
"""

# Informed agent prompt for Agents D/E - GTO default, exploit when data supports
INFORMED_AGENT_PROMPT = """You are an AI poker player in a No-Limit Texas Hold'em tournament.

{strategy_instructions}

**GTO IS YOUR DEFAULT** - Only deviate with 60+ hands of clear opponent data.

Use calculate_equity and calculate_pot_odds tools. Opponent stats are provided below.

## Response Format
{{
  "gto_analysis": "GTO reasoning (1 sentence)",
  "exploit_analysis": "Exploitation reasoning (1 sentence)", 
  "is_following_gto": true or false,
  "gto_deviation": "Following GTO because..." or "Deviating because...",
  "action_type": "fold|check|call|bet|raise|all_in",
  "sizing": {{"pot_fraction": 0.75}} or {{"bb_multiple": 3}} or null,
  "confidence": 0.0-1.0
}}
"""

# Keep backward compatibility alias
POKER_AGENT_PROMPT = INFORMED_AGENT_PROMPT


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

        # Choose prompt based on whether agent has pre-loaded knowledge
        # - Agents A/B/C: No knowledge, follow their personality (BASELINE_AGENT_PROMPT)
        # - Agents D/E: Have knowledge, use GTO + exploitation (INFORMED_AGENT_PROMPT)
        if strategy.has_shared_knowledge:
            prompt_template = INFORMED_AGENT_PROMPT
        else:
            prompt_template = BASELINE_AGENT_PROMPT

        # Build system prompt with strategy
        system_prompt = prompt_template.format(
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

        prompt_type = "INFORMED (GTO+exploit)" if strategy.has_shared_knowledge else "BASELINE (personality)"
        logger.info(
            f"Created agent {player_id} with strategy '{strategy.name}', "
            f"prompt={prompt_type}, "
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

        # Use the boolean field directly from the model
        is_following_gto = decision.is_following_gto

        # Console logging (human readable)
        logger.info(f"  [{self.player_id}] Cards: {hole_cards}")
        logger.info(
            f"    GTO: {decision.gto_analysis[:100]}{'...' if len(decision.gto_analysis) > 100 else ''}"
        )
        logger.info(
            f"    Exploit: {decision.exploit_analysis[:100]}{'...' if len(decision.exploit_analysis) > 100 else ''}"
        )
        gto_status = "✅" if is_following_gto else "⚠️"
        logger.info(
            f"    📐 {gto_status} {decision.gto_deviation[:80]}{'...' if len(decision.gto_deviation) > 80 else ''}"
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

        # Only show opponent stats for INFORMED agents (D/E)
        # Baseline agents (A/B/C) should just play their personality, no stats needed
        if self.strategy.has_shared_knowledge:
            lines.append("")
            lines.append("=== OPPONENT STATISTICS (60+ hands to exploit) ===")

            # Show stats for ALL other players (not just active ones)
            # Stats are about general playstyle, useful even if they folded this hand
            for player in state.players:
                if player.seat == state.hero_seat:
                    continue  # Skip hero
                profile = self.knowledge_base.get_profile(player.name)
                if profile and profile.statistics.hands_played > 0:
                    stats = profile.statistics
                    lines.append(f"\n{player.name} ({stats.hands_played} hands):")
                    lines.append(f"  VPIP: {stats.vpip:.1f}%, PFR: {stats.pfr:.1f}%")
                    lines.append(f"  Aggression: {stats.aggression_factor:.2f}")
                    lines.append(f"  C-bet Flop: {stats.cbet_flop_pct:.1f}%")
                    lines.append(f"  Fold to 3-bet: {stats.fold_to_three_bet:.1f}%")
                    lines.append(f"  WTSD: {stats.wtsd:.1f}%")
                else:
                    lines.append(f"\n{player.name}: No data")

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
