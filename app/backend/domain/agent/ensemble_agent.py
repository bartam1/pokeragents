"""
Ensemble Poker Agent - Multi-Agent Architecture for Agent E.

This agent uses three specialized sub-agents:
1. GTO Analyst - Pure game theory analysis
2. Exploit Analyst - Opponent exploitation analysis
3. Decision Maker - Final decision combining both

The GTO and Exploit analyses run in PARALLEL for efficiency,
then the Decision Maker synthesizes both into a final action.
"""
import asyncio

from backend.config import Settings
from backend.domain.agent.models import ActionDecision
from backend.domain.agent.specialists import DecisionMaker, ExploitAnalyst, GTOAnalyst
from backend.domain.agent.strategies.base import StrategyConfig
from backend.domain.agent.utils import deviation_tracker
from backend.domain.game.models import Action, HandResult, StructuredGameState
from backend.domain.player.models import KnowledgeBase
from backend.domain.player.tracker import StatisticsTracker
from backend.logging_config import get_logger, log_agent_decision

logger = get_logger(__name__)


class EnsemblePokerAgent:
    """
    Multi-Agent Ensemble Poker Agent.

    Uses three specialized agents working together:
    - GTOAnalyst: Analyzes from pure game theory perspective
    - ExploitAnalyst: Identifies opponent-specific exploits
    - DecisionMaker: Combines both to make final decision

    This architecture allows for:
    - Better specialization in each analysis domain
    - Parallel execution of GTO and Exploit analysis
    - Clear separation of concerns
    - More transparent decision making
    """

    def __init__(
        self,
        player_id: str,
        strategy: StrategyConfig,
        knowledge_base: KnowledgeBase,
        settings: Settings,
    ):
        self.player_id = player_id
        self._strategy = strategy
        self._knowledge_base = knowledge_base
        self._settings = settings

        # Create the three specialist agents
        self._gto_analyst = GTOAnalyst(settings)
        self._exploit_analyst = ExploitAnalyst(settings)
        self._decision_maker = DecisionMaker(settings)

        # Statistics tracker (same as regular PokerAgent)
        self._tracker = StatisticsTracker(knowledge_base)

        # Hand history tracking
        self._current_hand_history: list[dict] = []

        logger.info(
            f"🎭 Created EnsemblePokerAgent for {player_id} "
            f"(Multi-Agent Architecture: GTO + Exploit + Decision)"
        )

    @property
    def knowledge_base(self) -> KnowledgeBase:
        """Access to the agent's knowledge base."""
        return self._knowledge_base

    @property
    def strategy(self) -> StrategyConfig:
        """Access to the agent's strategy configuration."""
        return self._strategy

    async def decide(self, game_state: StructuredGameState) -> ActionDecision:
        """
        Make a poker decision using the multi-agent ensemble.

        1. Build prompts from game state
        2. Run GTO and Exploit analysis in PARALLEL
        3. Pass both to Decision Maker for final action

        Args:
            game_state: Current game state

        Returns:
            ActionDecision with action and all reasoning
        """
        # Build prompts
        state_prompt = self._build_state_prompt(game_state)
        opponent_stats = self._build_opponent_stats(game_state)
        hand_history = self._build_hand_history(game_state.action_history)

        # Debug logging - print all prompts for testing
        logger.debug(f"Agent {self.player_id} STATE PROMPT:\n{'='*60}\n{state_prompt}\n{'='*60}")
        logger.debug(
            f"Agent {self.player_id} OPPONENT STATS:\n{'='*60}\n{opponent_stats}\n{'='*60}"
        )
        logger.debug(f"Agent {self.player_id} HAND HISTORY:\n{'='*60}\n{hand_history}\n{'='*60}")

        logger.info(f"🎭 {self.player_id} (Ensemble) analyzing situation...")

        # Run GTO and Exploit analysis in PARALLEL
        gto_task = self._gto_analyst.analyze(state_prompt, hand_history)
        exploit_task = self._exploit_analyst.analyze(state_prompt, opponent_stats, hand_history)

        gto_analysis, exploit_analysis = await asyncio.gather(gto_task, exploit_task)

        logger.info(
            f"  🎯 GTO: {gto_analysis.recommended_action} "
            f"(conf: {gto_analysis.confidence:.2f}) - {gto_analysis.reasoning[:50]}..."
        )
        logger.info(
            f"  🔍 Exploit: {exploit_analysis.opponent_type} "
            f"(conf: {exploit_analysis.confidence:.2f}) - {exploit_analysis.recommended_adjustment[:50]}..."
        )

        # Build valid actions list
        valid_actions = [a.value for a in game_state.legal_actions]

        # Decision Maker combines both analyses + hand history
        decision: ActionDecision = await self._decision_maker.decide(
            state_prompt,
            hand_history,  # Include what happened earlier in the hand
            gto_analysis,
            exploit_analysis,
            valid_actions,
        )

        # Resolve to Action and log
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
        logger.info(f"  📐 GTO Deviation: {decision.gto_deviation[:60]}...")
        logger.info(
            f"  🎲 Decision: {action.type.value} "
            f"{action.amount if action.amount else ''} "
            f"(conf: {decision.confidence:.2f})"
        )

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
        """Build a prompt describing the current game state."""
        lines = []

        # Our hand
        our_player = state.hero
        hole_cards_str = (
            " ".join(f"{c.rank}{c.suit}" for c in our_player.hole_cards)
            if our_player.hole_cards
            else "Unknown"
        )

        lines.append(f"Your Hand: {hole_cards_str}")
        lines.append(f"Your Stack: {our_player.stack:.0f}")
        lines.append(f"Your Position: Seat {state.hero_seat}")
        lines.append("")

        # Board
        if state.community_cards:
            board_str = " ".join(f"{c.rank}{c.suit}" for c in state.community_cards)
            lines.append(f"Board: {board_str}")
        else:
            lines.append("Board: (preflop)")

        lines.append(f"Street: {state.street.value}")
        lines.append(f"Pot: {state.pot:.0f}")
        lines.append(f"Current Bet: {state.current_bet:.0f}")
        lines.append("")

        # Opponents
        lines.append("Opponents:")
        for i, player in enumerate(state.players):
            if i != state.hero_seat:
                status = "active" if player.is_active else "folded"
                lines.append(f"  Seat {i}: Stack {player.stack:.0f} ({status})")

        lines.append("")

        # Valid actions
        valid_str = ", ".join(a.value for a in state.legal_actions)
        lines.append(f"Valid Actions: {valid_str}")

        if state.min_raise > 0:
            lines.append(f"Min Raise: {state.min_raise:.0f}")
        if state.max_raise > 0:
            lines.append(f"Max Raise: {state.max_raise:.0f}")

        return "\n".join(lines)

    def _build_opponent_stats(self, state: StructuredGameState) -> str:
        """Build opponent statistics string for the exploit analyst."""
        from backend.domain.player.models import MIN_RELIABLE_SAMPLE_SIZE

        lines = ["Opponent Statistics:"]
        lines.append(
            f"(Minimum {MIN_RELIABLE_SAMPLE_SIZE} hands required for reliable exploitation)"
        )

        # Use state.opponents to get active opponents with their actual names
        # This correctly maps to knowledge base profiles regardless of seating order
        for opp in state.opponents:
            profile = self._knowledge_base.get_profile(opp.name)

            if profile and profile.statistics.hands_played > 0:
                stats = profile.statistics

                lines.append(f"\n{opp.name} (Stack: {opp.stack:.0f}):")

                # Don't show misleading percentages with tiny samples
                if stats.hands_played < 20:
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

    def _build_hand_history(self, action_history: list[dict] | None) -> str:
        """Build hand history string for analysis."""
        if not action_history:
            return "No actions yet in this hand."

        lines = ["Hand History:"]
        current_street = None

        for action in action_history:
            street = action.get("street", "unknown")
            if street != current_street:
                current_street = street
                lines.append(f"\n=== {street.upper()} ===")

            player = action.get("player_name", "?")
            action_type = action.get("action", action.get("action_type", "?"))
            amount = action.get("amount", 0)
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

            if amount and amount > 0 and pot:
                lines.append(
                    f"  {player}: {action_type} {amount:.0f} [before: pot={pot:.0f}, stacks: {stacks_str}]"
                )
            elif amount and amount > 0:
                lines.append(f"  {player}: {action_type} {amount:.0f}")
            else:
                lines.append(f"  {player}: {action_type}")

        return "\n".join(lines)

    # =========================================================================
    # Statistics Tracking (same interface as PokerAgent)
    # =========================================================================

    def observe_action(
        self,
        player_id: str,
        player_name: str,
        action: Action,
        game_state: StructuredGameState,
    ) -> None:
        """
        Observe another player's action (for learning).
        Delegates to the StatisticsTracker.
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
        """Initialize per-hand tracking state."""
        self._tracker.start_hand(player_ids)
        self._current_hand_history = []

    def end_hand_tracking(
        self,
        hand_result: HandResult,
        player_names: list[str],
    ) -> None:
        """Finalize per-hand stats (WTSD/WSD) after a hand is complete."""
        self._tracker.end_hand(player_names, hand_result)
