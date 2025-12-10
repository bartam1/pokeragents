"""
Tournament Orchestrator - Runs poker tournaments between AI agents.

This is the main coordinator that:
1. Sets up the game environment (PokerKit)
2. Creates agents with their strategies and knowledge bases
3. Runs hands until tournament completion
4. Tracks results for the POC experiment
5. Calculates EV chips for showdown hands to measure decision quality
"""
import os
from dataclasses import dataclass, field
from typing import Union

from backend.config import Settings
from backend.domain.agent.ensemble_agent import EnsemblePokerAgent
from backend.domain.agent.poker_agent import PokerAgent
from backend.domain.agent.strategies.base import (
    AGENT_A_BLUFFER,
    AGENT_B_PASSIVE,
    AGENT_C_TIGHT,
    AGENT_D_INFORMED,
    AGENT_E_ENSEMBLE,
    StrategyConfig,
)
from backend.domain.agent.utils import deviation_tracker
from backend.domain.game.environment import PokerEnvironment
from backend.domain.game.equity import calculate_multiway_equity
from backend.domain.game.models import Action, ActionType, EVRecord, HandResult
from backend.domain.player.models import KnowledgeBase, create_shared_knowledge_base
from backend.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class TournamentResult:
    """Results of a completed tournament."""

    placements: list[str]  # Player IDs in order of finish (winner first)
    hand_count: int
    eliminations: list[tuple[str, int]]  # (player_id, hand_number_eliminated)
    final_stacks: dict[str, float]
    agent_d_placement: int
    agent_e_placement: int

    # EV tracking (showdown hands only)
    ev_records: list[EVRecord] = field(default_factory=list)
    ev_by_player: dict[str, dict[str, float]] = field(default_factory=dict)
    # ev_by_player format: {"agent_d": {"ev_chips": 100, "actual_chips": 50, "variance": -50}}


@dataclass
class TournamentConfig:
    """Tournament configuration."""

    starting_stack: int = 1500
    small_blind: int = 10
    big_blind: int = 20
    blind_increase_interval: int = 20  # Hands between blind increases
    blind_increase_multiplier: float = 1.5

    # Maximum hands to prevent infinite games
    max_hands: int = 500


# Default agent configurations for the 5-player POC
DEFAULT_AGENTS = [
    ("agent_a", AGENT_A_BLUFFER),
    ("agent_b", AGENT_B_PASSIVE),
    ("agent_c", AGENT_C_TIGHT),
    ("agent_d", AGENT_D_INFORMED),
    ("agent_e", AGENT_E_ENSEMBLE),  # Uses multi-agent ensemble architecture
]


class TournamentOrchestrator:
    """
    Runs a Sit & Go tournament with AI agents.

    The key experiment:
    - Agent D has pre-loaded knowledge of opponents
    - Agent E starts with no knowledge and must learn
    - We compare their performance to prove shared knowledge helps
    """

    def __init__(self, settings: Settings):
        """
        Initialize the orchestrator.

        Args:
            settings: Application settings (API keys, etc.)
        """
        self._settings = settings
        self._agents: dict[str, Union[PokerAgent, EnsemblePokerAgent]] = {}
        self._env: PokerEnvironment | None = None
        self._config: TournamentConfig | None = None
        self._eliminations: list[tuple[str, int]] = []
        self._calibration_mode: bool = False
        self._ev_records: list[EVRecord] = []  # EV tracking for showdown hands

    def setup_tournament(
        self,
        config: TournamentConfig | None = None,
        agent_configs: list[tuple[str, StrategyConfig]] | None = None,
        calibration_mode: bool = False,
    ) -> None:
        """
        Set up a new tournament.

        Args:
            config: Tournament configuration
            agent_configs: List of (player_id, strategy) tuples.
                          If None, uses default 5-player setup.
            calibration_mode: If True, Agent D starts empty to learn real behaviors
        """
        self._config = config or TournamentConfig()
        agent_configs = agent_configs or DEFAULT_AGENTS
        self._eliminations = []
        self._calibration_mode = calibration_mode
        self._ev_records = []  # Reset EV records for new tournament

        player_names = [pid for pid, _ in agent_configs]

        # Create the poker environment
        self._env = PokerEnvironment(
            player_names=player_names,
            starting_stack=self._config.starting_stack,
            small_blind=self._config.small_blind,
            big_blind=self._config.big_blind,
        )

        # Create agents with appropriate knowledge bases
        # Load shared calibrated stats ONCE (same for all informed agents)
        shared_knowledge = None
        if not calibration_mode:
            calibrated_path = os.path.join(
                self._settings.knowledge_persistence_dir, "calibrated_stats.json"
            )
            shared_knowledge = KnowledgeBase.load_from_file(calibrated_path)
            if shared_knowledge.profiles:
                logger.info(
                    f"📊 Loaded SHARED calibrated knowledge: "
                    f"{len(shared_knowledge.profiles)} opponents, "
                    f"{shared_knowledge.get_total_hands_observed()} total hands"
                )

        for player_id, strategy in agent_configs:
            # Create knowledge base
            if strategy.has_shared_knowledge and not calibration_mode:
                # Both Agent D and Agent E get the SAME calibrated stats
                if shared_knowledge and shared_knowledge.profiles:
                    # Create a copy so they don't share the same object
                    knowledge_base = KnowledgeBase.load_from_file(calibrated_path)
                    logger.info(f"  {player_id}: Loaded shared calibrated knowledge")
                else:
                    # Fall back to pre-defined stats
                    knowledge_base = create_shared_knowledge_base(exclude_player=player_id)
                    logger.info(f"  {player_id}: Using DEFAULT pre-loaded knowledge")
            else:
                # Other agents OR calibration mode: start fresh
                knowledge_base = KnowledgeBase()
                if calibration_mode and strategy.has_shared_knowledge:
                    logger.info(f"🔧 {player_id} starting EMPTY for calibration")

            # Create the agent (use ensemble architecture if configured)
            if strategy.use_ensemble:
                self._agents[player_id] = EnsemblePokerAgent(
                    player_id=player_id,
                    strategy=strategy,
                    knowledge_base=knowledge_base,
                    settings=self._settings,
                )
                logger.info(
                    f"🎭 {player_id} using ENSEMBLE architecture (GTO + Exploit + Decision)"
                )
            else:
                self._agents[player_id] = PokerAgent(
                    player_id=player_id,
                    strategy=strategy,
                    knowledge_base=knowledge_base,
                    settings=self._settings,
                )

        logger.info(
            f"Tournament setup complete: {len(self._agents)} agents, "
            f"starting stacks {self._config.starting_stack}"
        )

        # Log what each agent knows about opponents at tournament start
        for player_id, agent in self._agents.items():
            if agent.knowledge_base.profiles:
                logger.info(f"  📊 {player_id}'s knowledge:")
                for opp_id, profile in agent.knowledge_base.profiles.items():
                    stats = profile.statistics
                    logger.info(
                        f"      {opp_id}: {stats.hands_played} hands, "
                        f"VPIP {stats.vpip:.1f}%, PFR {stats.pfr:.1f}%, "
                        f"AF {stats.aggression_factor:.2f}"
                    )
            else:
                logger.info(f"  📊 {player_id}: No prior knowledge")

    async def run_tournament(self) -> TournamentResult:
        """
        Run the tournament to completion.

        Returns:
            TournamentResult with placements and statistics.
        """
        if not self._env or not self._agents or not self._config:
            raise ValueError("Tournament not set up. Call setup_tournament first.")

        hand_count = 0
        current_sb = self._config.small_blind
        current_bb = self._config.big_blind

        logger.info("Starting tournament...")

        while self._get_active_player_count() > 1:
            hand_count += 1

            if hand_count > self._config.max_hands:
                logger.warning(f"Tournament reached max hands ({self._config.max_hands})")
                break

            # Increase blinds periodically
            if hand_count > 1 and hand_count % self._config.blind_increase_interval == 0:
                current_sb = int(current_sb * self._config.blind_increase_multiplier)
                current_bb = int(current_bb * self._config.blind_increase_multiplier)
                self._env.set_blinds(current_sb, current_bb)

            # Play a hand
            try:
                should_continue = await self._play_hand(hand_count)
                if not should_continue:
                    break  # Tournament over
            except Exception as e:
                logger.error(f"Error in hand {hand_count}: {e}")
                # Continue with next hand

            # Check for eliminations
            for player_id in list(self._agents.keys()):
                stack = self._env.get_stack(self._env.player_names.index(player_id))
                if stack <= 0 and player_id not in [e[0] for e in self._eliminations]:
                    self._eliminations.append((player_id, hand_count))
                    logger.info(f"Player {player_id} eliminated in hand {hand_count}")

        # Save Agent D's accumulated knowledge
        self._save_agent_knowledge()

        # Build final results
        return self._build_results(hand_count)

    async def _play_hand(self, hand_number: int) -> bool:
        """Play a single hand. Returns False if tournament should end."""
        logger.info(f"--- Hand #{hand_number} ---")

        # Track stacks before hand for profit/loss calculation
        stacks_before = {
            name: self._env.get_stack(i) for i, name in enumerate(self._env.player_names)
        }

        # Start new hand
        try:
            self._env.start_hand()
            for agent in self._agents.values():
                agent.start_hand_tracking(self._env.player_names)
        except ValueError as e:
            logger.info(f"Tournament ending: {e}")
            return False  # Signal tournament should end

        # Play until hand is complete
        while not self._env.is_hand_complete():
            actor_index = self._env.get_current_actor_index()
            if actor_index is None:
                break

            actor_name = self._env.player_names[actor_index]
            agent = self._agents.get(actor_name)

            if agent is None:
                logger.error(f"No agent for player {actor_name}")
                break

            # Get structured state for the agent
            game_state = self._env.get_structured_state(actor_index)

            # Agent makes decision
            try:
                decision = await agent.decide(game_state)

                # Convert structured decision to executable Action
                action = decision.to_action(game_state)

                # Execute the action
                self._env.execute_action(actor_index, action)

                # All other agents observe the action (without exposing actor's hole cards)
                for other_name, other_agent in self._agents.items():
                    if other_name != actor_name:
                        other_agent.observe_action(
                            player_id=actor_name,
                            player_name=actor_name,
                            action=action,
                            game_state=game_state,
                        )

            except Exception as e:
                logger.error(f"Agent {actor_name} error: {e}")
                # Default to fold on error
                try:
                    self._env.execute_action(actor_index, Action(type=ActionType.FOLD))
                except Exception:
                    break

        # Complete the hand
        try:
            result = self._env.complete_hand()
            for agent in self._agents.values():
                agent.end_hand_tracking(result, self._env.player_names)

            # Track profit/loss for GTO deviation analysis
            for i, name in enumerate(self._env.player_names):
                stack_after = self._env.get_stack(i)
                profit = stack_after - stacks_before.get(name, 0)
                deviation_tracker.record_hand_outcome(hand_number, name, profit)

            # Calculate EV for showdown hands
            if result.showdown and len(result.shown_hands) >= 2:
                ev_records = self._calculate_showdown_ev(hand_number, result, stacks_before)
                self._ev_records.extend(ev_records)

            # Show stacks after hand
            stacks_str = " | ".join(
                f"{name}: {self._env.get_stack(i):.0f}"
                for i, name in enumerate(self._env.player_names)
                if self._env.get_stack(i) > 0
            )
            logger.info(f"  Stacks: {stacks_str}")
        except ValueError:
            pass

        return True  # Hand completed, tournament continues

    def _save_agent_knowledge(self) -> None:
        """Save knowledge for agents with shared knowledge (Agent D and E)."""
        # First, save individual agent knowledge files
        for player_id, agent in self._agents.items():
            if agent.strategy.has_shared_knowledge:
                persist_path = os.path.join(
                    self._settings.knowledge_persistence_dir, f"{player_id}_knowledge.json"
                )
                agent.knowledge_base.save_to_file(persist_path)
                logger.info(
                    f"Saved {player_id}'s knowledge to {persist_path} "
                    f"({len(agent.knowledge_base.profiles)} profiles)"
                )

        # In calibration mode, accumulate stats ONCE (not per agent)
        # Use agent_d's knowledge as the canonical source
        if self._calibration_mode:
            # Find the primary agent for calibration (agent_d)
            calibration_agent = self._agents.get("agent_d")
            if not calibration_agent:
                # Fallback: use any agent with shared knowledge
                for agent in self._agents.values():
                    if agent.strategy.has_shared_knowledge:
                        calibration_agent = agent
                        break

            if calibration_agent:
                calibrated_path = os.path.join(
                    self._settings.knowledge_persistence_dir, "calibrated_stats.json"
                )

                # Load existing calibrated stats and accumulate
                existing_calibrated = KnowledgeBase.load_from_file(calibrated_path)
                if existing_calibrated.profiles:
                    # Accumulate new observations into existing
                    existing_calibrated.accumulate_with(calibration_agent.knowledge_base)
                    existing_calibrated.save_to_file(calibrated_path)
                    logger.info(f"🔧 ACCUMULATED calibration stats to {calibrated_path}")
                    self._log_calibrated_stats(existing_calibrated)
                else:
                    # First calibration run - just save
                    calibration_agent.knowledge_base.save_to_file(calibrated_path)
                    logger.info(f"🔧 Saved initial calibrated stats to {calibrated_path}")
                    self._log_calibrated_stats(calibration_agent.knowledge_base)

    def _log_calibrated_stats(self, kb: KnowledgeBase) -> None:
        """Log the calibrated statistics for review."""
        logger.info("\n📊 CALIBRATED OPPONENT STATISTICS:")
        for opp_id, profile in kb.profiles.items():
            stats = profile.statistics
            logger.info(f"   {opp_id}: {stats.hands_played} hands observed")
            logger.info(f"      VPIP: {stats.vpip:.1f}%, PFR: {stats.pfr:.1f}%")
            logger.info(
                f"      C-bet: {stats.cbet_flop_pct:.1f}%, AF: {stats.aggression_factor:.2f}"
            )

    def _calculate_showdown_ev(
        self,
        hand_number: int,
        result: HandResult,
        stacks_before: dict[str, float],
    ) -> list[EVRecord]:
        """
        Calculate EV records for a showdown hand.

        At showdown, we know both hands and can calculate exact equity
        to determine what "should have happened" vs what actually happened.

        Args:
            hand_number: Current hand number
            result: The completed hand result with shown hands
            stacks_before: Player stacks before the hand started

        Returns:
            List of EVRecord for each player who showed cards
        """
        ev_records = []

        # Get the shown hands (seat -> cards)
        shown_seats = list(result.shown_hands.keys())
        if len(shown_seats) < 2:
            return ev_records

        # For heads-up showdown, calculate EV for both players
        # For multiway, calculate each player vs the field (simplified)
        player_names = self._env.player_names

        # Get board cards from the environment's last state
        board_cards = []
        if hasattr(self._env, "_state") and self._env._state:
            if self._env._state.board_cards:
                from backend.domain.game.models import Card

                for board in self._env._state.board_cards:
                    for card in board:
                        board_cards.append(Card(rank=str(card.rank), suit=str(card.suit)))

        num_players_shown = len(shown_seats)
        is_multiway = num_players_shown > 2

        for seat in shown_seats:
            player_id = player_names[seat]
            hero_cards = result.shown_hands[seat]

            # Get all opponent hands for multiway equity calculation
            opponent_seats = [s for s in shown_seats if s != seat]
            if not opponent_seats:
                continue

            opponent_hands = [result.shown_hands[s] for s in opponent_seats]

            # Calculate equity against all opponents (works for both heads-up and multiway)
            try:
                equity = calculate_multiway_equity(hero_cards, opponent_hands, board_cards)
            except Exception as e:
                logger.warning(f"Could not calculate showdown equity: {e}")
                equity = 1.0 / num_players_shown  # Default to even split if calculation fails

            # Calculate amounts
            pot_size = result.pot_size
            stack_before = stacks_before.get(player_id, 0)
            stack_after = self._env.get_stack(self._env.player_names.index(player_id))

            # Amount invested = what we had before - what we have after (if we lost)
            # Or: pot_size / num_players as approximation for heads-up
            actual_profit = stack_after - stack_before
            won = seat in result.winners

            # For investment, calculate what this player put in
            # In heads-up all-in: each player's investment is pot_size / 2 (approximately)
            # Better: investment = -actual_profit if lost, pot_size - actual_profit if won
            if won:
                amount_invested = pot_size - actual_profit
            else:
                amount_invested = -actual_profit

            # EV calculation: (equity × pot) - invested
            ev_chips = (equity * pot_size) - amount_invested
            actual_chips = actual_profit

            ev_record = EVRecord(
                hand_number=hand_number,
                player_id=player_id,
                equity=equity,
                pot_size=pot_size,
                amount_invested=amount_invested,
                ev_chips=ev_chips,
                actual_chips=actual_chips,
            )
            ev_records.append(ev_record)

            # Log EV calculation for transparency
            variance = ev_record.variance
            logger.info(
                f"  📊 EV: {player_id} had {equity*100:.1f}% equity | "
                f"EV: {ev_chips:+.0f} | Actual: {actual_chips:+.0f} | Variance: {variance:+.0f}"
            )

        return ev_records

    def _get_active_player_count(self) -> int:
        """Get number of players still in the tournament."""
        if not self._env:
            return 0
        return self._env.get_active_player_count()

    def _build_results(self, hand_count: int) -> TournamentResult:
        """Build the tournament results."""
        # Get final stacks
        final_stacks = {}
        for i, name in enumerate(self._env.player_names):
            final_stacks[name] = self._env.get_stack(i)

        # Build placements (winner has most chips, then elimination order reversed)
        active_players = [(name, stack) for name, stack in final_stacks.items() if stack > 0]
        active_players.sort(key=lambda x: x[1], reverse=True)

        placements = [p[0] for p in active_players]

        # Add eliminated players in reverse order (last eliminated = better placement)
        for player_id, _ in reversed(self._eliminations):
            if player_id not in placements:
                placements.append(player_id)

        # Find Agent D and E placements
        agent_d_placement = placements.index("agent_d") + 1 if "agent_d" in placements else -1
        agent_e_placement = placements.index("agent_e") + 1 if "agent_e" in placements else -1

        # Aggregate EV by player
        ev_by_player: dict[str, dict[str, float]] = {}
        for ev_record in self._ev_records:
            player_id = ev_record.player_id
            if player_id not in ev_by_player:
                ev_by_player[player_id] = {
                    "ev_chips": 0.0,
                    "actual_chips": 0.0,
                    "variance": 0.0,
                    "ev_adjusted": 0.0,  # Sum of ev_adjusted from showdowns
                    "showdown_count": 0,
                }
            ev_by_player[player_id]["ev_chips"] += ev_record.ev_chips
            ev_by_player[player_id]["actual_chips"] += ev_record.actual_chips
            ev_by_player[player_id]["variance"] += ev_record.variance
            ev_by_player[player_id]["ev_adjusted"] += ev_record.ev_adjusted
            ev_by_player[player_id]["showdown_count"] += 1

        result = TournamentResult(
            placements=placements,
            hand_count=hand_count,
            eliminations=self._eliminations,
            final_stacks=final_stacks,
            agent_d_placement=agent_d_placement,
            agent_e_placement=agent_e_placement,
            ev_records=self._ev_records,
            ev_by_player=ev_by_player,
        )

        logger.info(f"Tournament complete after {hand_count} hands. " f"Placements: {placements}")
        logger.info(
            f"Agent D (informed) placed: {agent_d_placement}, "
            f"Agent E (naive) placed: {agent_e_placement}"
        )

        # Log EV summary
        if ev_by_player:
            logger.info("📈 EV Summary (Showdown Hands):")
            for player_id in ["agent_d", "agent_e"]:
                if player_id in ev_by_player:
                    ev_data = ev_by_player[player_id]
                    logger.info(
                        f"  {player_id}: EV {ev_data['ev_chips']:+.0f} | "
                        f"Actual {ev_data['actual_chips']:+.0f} | "
                        f"Variance {ev_data['variance']:+.0f} "
                        f"({ev_data['showdown_count']} showdowns)"
                    )

        return result
