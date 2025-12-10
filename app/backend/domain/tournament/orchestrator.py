"""
Tournament Orchestrator - Runs poker tournaments between AI agents.

This is the main coordinator that:
1. Sets up the game environment (PokerKit)
2. Creates agents with their strategies and knowledge bases
3. Runs hands until tournament completion
4. Tracks results for the POC experiment
"""
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Union

from backend.config import Settings
from backend.domain.game.environment import PokerEnvironment
from backend.domain.game.models import Action, ActionType
from backend.domain.game.recorder import GameStateRecorder
from backend.domain.player.models import KnowledgeBase, create_shared_knowledge_base
from backend.domain.agent.poker_agent import PokerAgent
from backend.domain.agent.ensemble_agent import EnsemblePokerAgent
from backend.domain.agent.strategies.base import (
    AGENT_A_BLUFFER,
    AGENT_B_PASSIVE,
    AGENT_C_TIGHT,
    AGENT_D_INFORMED,
    AGENT_E_ENSEMBLE,
    StrategyConfig,
)
from backend.domain.agent.utils import deviation_tracker
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
        self._recorder = GameStateRecorder(settings.gamestates_dir)
        self._tournament_id: str = ""

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
        
        # Generate a unique tournament ID and start recording
        self._tournament_id = str(uuid.uuid4())[:8]
        self._recorder.start_tournament(self._tournament_id)

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
                self._settings.knowledge_persistence_dir,
                "calibrated_stats.json"
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
                    logger.info(
                        f"  {player_id}: Loaded shared calibrated knowledge"
                    )
                else:
                    # Fall back to pre-defined stats
                    knowledge_base = create_shared_knowledge_base(exclude_player=player_id)
                    logger.info(
                        f"  {player_id}: Using DEFAULT pre-loaded knowledge"
                    )
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
                logger.info(f"🎭 {player_id} using ENSEMBLE architecture (GTO + Exploit + Decision)")
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
                stack = self._env.get_stack(
                    self._env.player_names.index(player_id)
                )
                if stack <= 0 and player_id not in [e[0] for e in self._eliminations]:
                    self._eliminations.append((player_id, hand_count))
                    logger.info(f"Player {player_id} eliminated in hand {hand_count}")

        # Save Agent D's accumulated knowledge
        self._save_agent_knowledge()
        
        # Save recorded game states for future statistics recalculation
        saved_path = self._recorder.save_tournament()
        if saved_path:
            logger.info(f"📝 Saved game states to {saved_path}")

        # Build final results
        return self._build_results(hand_count)

    async def _play_hand(self, hand_number: int) -> bool:
        """Play a single hand. Returns False if tournament should end."""
        logger.info(f"--- Hand #{hand_number} ---")
        
        # Track stacks before hand for profit/loss calculation
        stacks_before = {
            name: self._env.get_stack(i)
            for i, name in enumerate(self._env.player_names)
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
                
                # Record the state and action for statistics recalculation
                self._recorder.record_action(game_state, actor_name, action)

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
                    self._settings.knowledge_persistence_dir,
                    f"{player_id}_knowledge.json"
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
                    self._settings.knowledge_persistence_dir,
                    "calibrated_stats.json"
                )
                
                # Load existing calibrated stats and accumulate
                existing_calibrated = KnowledgeBase.load_from_file(calibrated_path)
                if existing_calibrated.profiles:
                    # Accumulate new observations into existing
                    existing_calibrated.accumulate_with(calibration_agent.knowledge_base)
                    existing_calibrated.save_to_file(calibrated_path)
                    logger.info(
                        f"🔧 ACCUMULATED calibration stats to {calibrated_path}"
                    )
                    self._log_calibrated_stats(existing_calibrated)
                else:
                    # First calibration run - just save
                    calibration_agent.knowledge_base.save_to_file(calibrated_path)
                    logger.info(
                        f"🔧 Saved initial calibrated stats to {calibrated_path}"
                    )
                    self._log_calibrated_stats(calibration_agent.knowledge_base)
    
    def _log_calibrated_stats(self, kb: KnowledgeBase) -> None:
        """Log the calibrated statistics for review."""
        logger.info("\n📊 CALIBRATED OPPONENT STATISTICS:")
        for opp_id, profile in kb.profiles.items():
            stats = profile.statistics
            logger.info(
                f"   {opp_id}: {stats.hands_played} hands observed"
            )
            logger.info(
                f"      VPIP: {stats.vpip:.1f}%, PFR: {stats.pfr:.1f}%"
            )
            logger.info(
                f"      C-bet: {stats.cbet_flop_pct:.1f}%, AF: {stats.aggression_factor:.2f}"
            )

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
        active_players = [
            (name, stack) for name, stack in final_stacks.items() if stack > 0
        ]
        active_players.sort(key=lambda x: x[1], reverse=True)

        placements = [p[0] for p in active_players]

        # Add eliminated players in reverse order (last eliminated = better placement)
        for player_id, _ in reversed(self._eliminations):
            if player_id not in placements:
                placements.append(player_id)

        # Find Agent D and E placements
        agent_d_placement = placements.index("agent_d") + 1 if "agent_d" in placements else -1
        agent_e_placement = placements.index("agent_e") + 1 if "agent_e" in placements else -1

        result = TournamentResult(
            placements=placements,
            hand_count=hand_count,
            eliminations=self._eliminations,
            final_stacks=final_stacks,
            agent_d_placement=agent_d_placement,
            agent_e_placement=agent_e_placement,
        )

        logger.info(
            f"Tournament complete after {hand_count} hands. "
            f"Placements: {placements}"
        )
        logger.info(
            f"Agent D (informed) placed: {agent_d_placement}, "
            f"Agent E (naive) placed: {agent_e_placement}"
        )

        return result
