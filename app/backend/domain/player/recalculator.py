"""
Statistics Recalculator - Recalculates baseline statistics from saved game states.

This module loads all saved tournament game states and replays them through
the StatisticsTracker to compute fresh baseline statistics.

Supports both old (v1) and new minimal (v2) tournament formats.
"""

from pathlib import Path
from typing import Any

from backend.domain.game.models import HandResult, Street
from backend.domain.game.recorder import GameStateRecorder, TournamentRecord
from backend.domain.player.models import KnowledgeBase
from backend.domain.player.tracker import StatisticsTracker
from backend.logging_config import get_logger

logger = get_logger(__name__)


def recalculate_baseline_stats(
    gamestates_dir: str = "data/gamestates",
    output_path: str = "data/knowledge/stats.json",
) -> KnowledgeBase:
    """
    Recalculate baseline statistics from all saved tournament game states.

    This function:
    1. Loads all saved tournament JSON files (v1, v2, or v3 format)
    2. Replays all recorded actions through a fresh StatisticsTracker
    3. Saves the resulting statistics to stats.json

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
        total_actions += len(tournament.actions)

    logger.info(f"📊 Recalculated stats from {total_actions} actions across {total_hands} hands")

    for player_id, profile in knowledge_base.profiles.items():
        stats = profile.statistics
        ev_info = f", EV-adj: {stats.ev_adjusted_total:+.0f}" if stats.showdown_count > 0 else ""
        logger.info(
            f"  {player_id}: {stats.hands_played} hands, "
            f"VPIP {stats.vpip:.1f}%, PFR {stats.pfr:.1f}%, "
            f"AF {stats.aggression_factor:.2f}{ev_info}"
        )

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
    if not tournament.hands:
        return 0

    players = tournament.players
    hands_replayed = 0

    for hand in tournament.hands:
        tracker.start_hand(players)

        for minimal_action in hand.actions:
            action = minimal_action.to_action()
            stub_state = minimal_action.to_stub_game_state(hand.big_blind)

            tracker.observe_action(
                player_id=minimal_action.actor,
                player_name=minimal_action.actor,
                action=action,
                game_state=stub_state,  # type: ignore - duck typing works here
            )

        _end_hand(tracker, players, hand.hand_number)

        # Process EV records for this hand
        for ev_record in hand.ev_records:
            _update_ev_stats(tracker.knowledge_base, ev_record)

        hands_replayed += 1

    return hands_replayed


def _update_ev_stats(knowledge_base: KnowledgeBase, ev_record: Any) -> None:
    """
    Update player statistics with EV data from a showdown.

    Args:
        knowledge_base: The knowledge base to update
        ev_record: The EV record from a showdown
    """
    profile = knowledge_base.get_or_create_profile(ev_record.player_id, ev_record.player_id)
    stats = profile.statistics
    stats.ev_adjusted_total += ev_record.ev_adjusted
    stats.showdown_count += 1


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
