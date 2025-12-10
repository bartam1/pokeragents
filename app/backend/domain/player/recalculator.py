"""
Statistics Recalculator - Recalculates baseline statistics from saved game states.

This module loads all saved tournament game states and replays them through
the StatisticsTracker to compute fresh baseline statistics.
"""
from pathlib import Path

from backend.domain.game.models import HandResult, Street
from backend.domain.game.recorder import GameStateRecorder, TournamentRecord
from backend.domain.player.models import KnowledgeBase
from backend.domain.player.tracker import StatisticsTracker
from backend.logging_config import get_logger

logger = get_logger(__name__)


def recalculate_baseline_stats(
    gamestates_dir: str = "data/gamestates",
    output_path: str = "data/knowledge/calibrated_stats.json",
) -> KnowledgeBase:
    """
    Recalculate baseline statistics from all saved tournament game states.
    
    This function:
    1. Loads all saved tournament JSON files
    2. Replays all recorded actions through a fresh StatisticsTracker
    3. Saves the resulting statistics as calibrated_stats.json
    
    Args:
        gamestates_dir: Directory containing tournament JSON files
        output_path: Path to save the recalculated statistics
        
    Returns:
        The recalculated KnowledgeBase
    """
    tournaments = GameStateRecorder.load_all_tournaments(gamestates_dir)
    
    if not tournaments:
        logger.info("No saved tournaments found, starting with empty baseline stats")
        return KnowledgeBase()
    
    logger.info(f"📊 Recalculating stats from {len(tournaments)} saved tournaments")
    
    knowledge_base = KnowledgeBase()
    tracker = StatisticsTracker(knowledge_base)
    
    total_hands = 0
    total_actions = 0
    
    for tournament in tournaments:
        hands_in_tournament = _replay_tournament(tournament, tracker)
        total_hands += hands_in_tournament
        total_actions += len(tournament.recorded_actions)
    
    logger.info(
        f"📊 Recalculated stats from {total_actions} actions across {total_hands} hands"
    )
    
    # Log summary of recalculated stats
    for player_id, profile in knowledge_base.profiles.items():
        stats = profile.statistics
        logger.info(
            f"  {player_id}: {stats.hands_played} hands, "
            f"VPIP {stats.vpip:.1f}%, PFR {stats.pfr:.1f}%, "
            f"AF {stats.aggression_factor:.2f}"
        )
    
    # Save the recalculated stats
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    knowledge_base.save_to_file(output_path)
    logger.info(f"📊 Saved recalculated stats to {output_path}")
    
    return knowledge_base


def _replay_tournament(tournament: TournamentRecord, tracker: StatisticsTracker) -> int:
    """
    Replay a single tournament's recorded actions through the tracker.
    
    Args:
        tournament: The tournament record to replay
        tracker: The StatisticsTracker to update
        
    Returns:
        Number of hands replayed
    """
    if not tournament.recorded_actions:
        return 0
    
    current_hand_number = None
    player_ids_in_hand: set[str] = set()
    hands_replayed = 0
    
    for recorded_action in tournament.recorded_actions:
        state = recorded_action.state
        actor = recorded_action.actor
        action = recorded_action.action
        
        # Detect hand boundary
        if current_hand_number != state.hand_number:
            # End previous hand if there was one
            if current_hand_number is not None and player_ids_in_hand:
                _end_hand(tracker, list(player_ids_in_hand), current_hand_number)
                hands_replayed += 1
            
            # Start new hand
            current_hand_number = state.hand_number
            player_ids_in_hand = {p.name for p in state.players}
            tracker.start_hand(list(player_ids_in_hand))
        
        # Record the action
        tracker.observe_action(
            player_id=actor,
            player_name=actor,
            action=action,
            game_state=state,
        )
    
    # End the last hand
    if current_hand_number is not None and player_ids_in_hand:
        _end_hand(tracker, list(player_ids_in_hand), current_hand_number)
        hands_replayed += 1
    
    return hands_replayed


def _end_hand(tracker: StatisticsTracker, player_ids: list[str], hand_number: int) -> None:
    """
    End a hand in the tracker with a minimal HandResult.
    
    Since we don't have full showdown data in the recordings, we create
    a minimal HandResult that just allows hands_played to be incremented.
    """
    minimal_result = HandResult(
        hand_number=hand_number,
        winners=[],
        pot_size=0,
        showdown=False,
        shown_hands={},
        actions_by_street={street: [] for street in Street},
    )
    tracker.end_hand(player_ids, minimal_result)

