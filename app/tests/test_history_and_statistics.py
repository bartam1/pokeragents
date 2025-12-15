"""
Tests for game history recording, statistics recalculation, and hand summaries.

These tests verify that:
1. Game state recorder correctly saves tournament data
2. Statistics can be recalculated from saved game states
3. Hand summaries correctly include EV data for showdown hands
4. Tournament formats (v1, v2, v3) are properly loaded

No LLM calls required - pure data/computation tests.
"""

import json
import tempfile
from pathlib import Path

from backend.domain.game.models import (
    Action,
    ActionType,
    EVRecord,
    PlayerState,
    Street,
    StructuredGameState,
)
from backend.domain.game.recorder import (
    GameStateRecorder,
    HandRecord,
    MinimalAction,
    TournamentRecord,
)
from backend.domain.player.recalculator import recalculate_baseline_stats

# =============================================================================
# Test Fixtures and Helpers
# =============================================================================


def make_game_state(
    hand_number: int = 1,
    street: Street = Street.PREFLOP,
    pot: float = 30.0,
    current_bet: float = 20.0,
    players: list[dict] | None = None,
    action_history: list[dict] | None = None,
) -> StructuredGameState:
    """Create a minimal game state for testing."""
    if players is None:
        players = [
            {"name": "player_a", "stack": 1490.0, "seat": 0},
            {"name": "player_b", "stack": 1480.0, "seat": 1},
            {"name": "player_c", "stack": 1500.0, "seat": 2},
        ]

    player_states = [
        PlayerState(
            seat=p["seat"],
            name=p["name"],
            stack=p["stack"],
            is_active=True,
            is_all_in=False,
            current_bet=0.0,
            hole_cards=None,
        )
        for p in players
    ]

    return StructuredGameState(
        hand_number=hand_number,
        button_seat=0,
        small_blind=10.0,
        big_blind=20.0,
        street=street,
        pot=pot,
        community_cards=[],
        players=player_states,
        hero_seat=0,
        current_bet=current_bet,
        min_raise=40.0,
        max_raise=1500.0,
        legal_actions=[ActionType.FOLD, ActionType.CALL, ActionType.RAISE],
        action_history=action_history or [],
    )


def make_ev_record(
    hand_number: int,
    player_id: str,
    equity: float,
    pot_size: float,
    amount_invested: float,
    won: bool,
) -> EVRecord:
    """Create an EV record for testing."""
    ev_chips = (equity * pot_size) - amount_invested
    actual_chips = (pot_size - amount_invested) if won else -amount_invested

    return EVRecord(
        hand_number=hand_number,
        player_id=player_id,
        equity=equity,
        pot_size=pot_size,
        amount_invested=amount_invested,
        ev_chips=ev_chips,
        actual_chips=actual_chips,
    )


# =============================================================================
# GameStateRecorder Tests
# =============================================================================


class TestGameStateRecorder:
    """Tests for GameStateRecorder recording and saving functionality."""

    def test_start_tournament_creates_record(self):
        """Verify starting a tournament creates a record with correct metadata."""
        recorder = GameStateRecorder(gamestates_dir="/tmp/test_gamestates")
        recorder.start_tournament("test_123")

        assert recorder._current_tournament is not None
        assert recorder._current_tournament.tournament_id == "test_123"
        assert recorder._current_tournament.timestamp is not None

    def test_record_action_captures_minimal_data(self):
        """Verify actions are recorded with minimal but sufficient data."""
        recorder = GameStateRecorder(gamestates_dir="/tmp/test_gamestates")
        recorder.start_tournament("test_action")

        state = make_game_state(hand_number=1, pot=30.0, current_bet=20.0)
        action = Action(type=ActionType.RAISE, amount=60.0)

        recorder.record_action(state, "player_a", action)

        assert len(recorder._current_tournament.hands) == 1
        hand = recorder._current_tournament.hands[0]
        assert hand.hand_number == 1
        assert len(hand.actions) == 1

        recorded_action = hand.actions[0]
        assert recorded_action.actor == "player_a"
        assert recorded_action.action_type == "raise"
        assert recorded_action.amount == 60.0
        assert recorded_action.pot == 30.0
        assert recorded_action.street == "preflop"

    def test_record_action_tracks_gto_deviation(self):
        """Verify GTO deviation tracking in recorded actions."""
        recorder = GameStateRecorder(gamestates_dir="/tmp/test_gamestates")
        recorder.start_tournament("test_gto")

        state = make_game_state()

        # GTO decision
        recorder.record_action(
            state,
            "player_a",
            Action(type=ActionType.FOLD),
            is_following_gto=True,
        )

        # Deviation decision
        recorder.record_action(
            state,
            "player_b",
            Action(type=ActionType.CALL, amount=20.0),
            is_following_gto=False,
            gto_deviation="Exploiting passive opponent",
        )

        actions = recorder._current_tournament.hands[0].actions
        assert actions[0].decision_type == "gto"
        assert actions[0].deviation_reason is None
        assert actions[1].decision_type == "deviate"
        assert actions[1].deviation_reason == "Exploiting passive opponent"

    def test_record_hand_result_captures_finishing_stacks(self):
        """Verify finishing stacks are recorded at hand completion."""
        recorder = GameStateRecorder(gamestates_dir="/tmp/test_gamestates")
        recorder.start_tournament("test_stacks")

        state = make_game_state()
        recorder.record_action(state, "player_a", Action(type=ActionType.FOLD))

        finishing_stacks = {"player_a": 1490.0, "player_b": 1510.0, "player_c": 1500.0}
        recorder.record_hand_result(finishing_stacks)

        hand = recorder._current_tournament.hands[0]
        assert hand.finishing_stacks == finishing_stacks

    def test_record_ev_adds_to_current_hand(self):
        """Verify EV records are added to the current hand."""
        recorder = GameStateRecorder(gamestates_dir="/tmp/test_gamestates")
        recorder.start_tournament("test_ev")

        state = make_game_state(hand_number=5)
        recorder.record_action(state, "player_a", Action(type=ActionType.CALL, amount=100.0))

        ev_record = make_ev_record(
            hand_number=5,
            player_id="player_a",
            equity=0.75,
            pot_size=200.0,
            amount_invested=100.0,
            won=True,
        )
        recorder.record_ev([ev_record])

        hand = recorder._current_tournament.hands[0]
        assert len(hand.ev_records) == 1
        assert hand.ev_records[0].player_id == "player_a"
        assert hand.ev_records[0].equity == 0.75

    def test_save_and_load_tournament(self):
        """Verify tournament can be saved and loaded correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = GameStateRecorder(gamestates_dir=tmpdir)
            recorder.start_tournament("round_trip_test")

            # Record some actions
            state = make_game_state(hand_number=1)
            recorder.record_action(state, "player_a", Action(type=ActionType.RAISE, amount=60.0))
            recorder.record_action(state, "player_b", Action(type=ActionType.CALL, amount=60.0))
            recorder.record_hand_result(
                {"player_a": 1560.0, "player_b": 1440.0, "player_c": 1500.0}
            )

            # Add EV record
            ev_record = make_ev_record(5, "player_a", 0.80, 200.0, 100.0, won=True)
            recorder._current_hand.ev_records.append(ev_record)

            # Save
            filepath = recorder.save_tournament()
            assert filepath is not None
            assert Path(filepath).exists()

            # Load and verify
            loaded = GameStateRecorder.load_tournament(filepath)
            assert loaded.tournament_id == "round_trip_test"
            assert len(loaded.hands) == 1
            assert len(loaded.hands[0].actions) == 2
            assert loaded.hands[0].finishing_stacks["player_a"] == 1560.0


# =============================================================================
# HandRecord and Hand Summary Tests
# =============================================================================


class TestHandRecord:
    """Tests for HandRecord and hand summary generation."""

    def test_to_summary_dict_basic(self):
        """Test basic hand summary without showdown."""
        hand = HandRecord(
            hand_number=1,
            small_blind=10.0,
            big_blind=20.0,
            starting_stacks={"player_a": 1490.0, "player_b": 1480.0, "player_c": 1500.0},
            finishing_stacks={"player_a": 1490.0, "player_b": 1510.0, "player_c": 1500.0},
            actions=[],
        )

        summary = hand.to_summary_dict()

        assert summary["hand_number"] == 1
        assert summary["winners"] == ["player_b"]  # Only player_b gained chips
        assert summary["chips_won"]["player_b"] == 30.0
        assert summary["went_to_showdown"] is False
        assert summary["ev_adjusted_chips"] is None

    def test_to_summary_dict_with_showdown_ev(self):
        """Test hand summary includes EV data when hand went to showdown."""
        ev_record_a = EVRecord(
            hand_number=1,
            player_id="player_a",
            equity=0.85,
            pot_size=1000.0,
            amount_invested=500.0,
            ev_chips=350.0,  # (0.85 * 1000) - 500
            actual_chips=500.0,  # Won
        )
        ev_record_b = EVRecord(
            hand_number=1,
            player_id="player_b",
            equity=0.15,
            pot_size=1000.0,
            amount_invested=500.0,
            ev_chips=-350.0,  # (0.15 * 1000) - 500
            actual_chips=-500.0,  # Lost
        )

        hand = HandRecord(
            hand_number=1,
            small_blind=10.0,
            big_blind=20.0,
            starting_stacks={"player_a": 1000.0, "player_b": 1000.0},
            finishing_stacks={"player_a": 1500.0, "player_b": 500.0},
            actions=[],
            ev_records=[ev_record_a, ev_record_b],
        )

        summary = hand.to_summary_dict()

        assert summary["went_to_showdown"] is True
        assert summary["ev_adjusted_chips"] is not None
        assert summary["ev_adjusted_chips"]["player_a"] == 350.0  # EV-adjusted
        assert summary["ev_adjusted_chips"]["player_b"] == -350.0  # EV-adjusted

    def test_to_summary_dict_multiway_showdown(self):
        """Test hand summary with 3+ players at showdown."""
        ev_records = [
            EVRecord(
                hand_number=1,
                player_id="player_a",
                equity=0.60,
                pot_size=1500.0,
                amount_invested=500.0,
                ev_chips=400.0,  # (0.60 * 1500) - 500
                actual_chips=1000.0,  # Won
            ),
            EVRecord(
                hand_number=1,
                player_id="player_b",
                equity=0.25,
                pot_size=1500.0,
                amount_invested=500.0,
                ev_chips=-125.0,  # (0.25 * 1500) - 500
                actual_chips=-500.0,  # Lost
            ),
            EVRecord(
                hand_number=1,
                player_id="player_c",
                equity=0.15,
                pot_size=1500.0,
                amount_invested=500.0,
                ev_chips=-275.0,  # (0.15 * 1500) - 500
                actual_chips=-500.0,  # Lost
            ),
        ]

        hand = HandRecord(
            hand_number=1,
            small_blind=10.0,
            big_blind=20.0,
            starting_stacks={"player_a": 1000.0, "player_b": 1000.0, "player_c": 1000.0},
            finishing_stacks={"player_a": 2000.0, "player_b": 500.0, "player_c": 500.0},
            actions=[],
            ev_records=ev_records,
        )

        summary = hand.to_summary_dict()

        assert summary["went_to_showdown"] is True
        assert len(summary["ev_adjusted_chips"]) == 3
        # EV should sum to approximately 0 (accounting for rounding)
        ev_sum = sum(summary["ev_adjusted_chips"].values())
        assert abs(ev_sum) < 1.0, f"EV sum should be ~0, got {ev_sum}"


# =============================================================================
# TournamentRecord Tests
# =============================================================================


class TestTournamentRecord:
    """Tests for TournamentRecord loading and format compatibility."""

    def test_v3_format_round_trip(self):
        """Test v3 format serialization and deserialization."""
        ev_record = EVRecord(
            hand_number=1,
            player_id="player_a",
            equity=0.75,
            pot_size=500.0,
            amount_invested=200.0,
            ev_chips=175.0,
            actual_chips=300.0,
        )

        hand = HandRecord(
            hand_number=1,
            small_blind=10.0,
            big_blind=20.0,
            starting_stacks={"player_a": 1500.0, "player_b": 1500.0},
            finishing_stacks={"player_a": 1800.0, "player_b": 1200.0},
            actions=[
                MinimalAction(
                    hand_number=1,
                    street="preflop",
                    actor="player_a",
                    action_type="raise",
                    amount=60.0,
                    pot=30.0,
                    current_bet=20.0,
                    preflop_raise_count=0,
                    stacks={"player_a": 1500.0, "player_b": 1500.0},
                ),
            ],
            ev_records=[ev_record],
        )

        tournament = TournamentRecord(
            tournament_id="test_v3",
            timestamp="20251213_120000",
            players=["player_a", "player_b"],
            hands=[hand],
        )

        # Serialize
        data = tournament.to_dict()
        assert data["format_version"] == 3
        assert "hand_summaries" in data

        # Deserialize
        loaded = TournamentRecord.from_dict(data)
        assert loaded.tournament_id == "test_v3"
        assert len(loaded.hands) == 1
        assert len(loaded.hands[0].ev_records) == 1
        assert loaded.hands[0].ev_records[0].equity == 0.75

    def test_v2_format_loading(self):
        """Test loading v2 format (flat actions) converts to v3."""
        v2_data = {
            "tournament_id": "test_v2",
            "timestamp": "20251213_110000",
            "format_version": 2,
            "players": ["player_a", "player_b"],
            "big_blind": 20.0,
            "actions": [
                {
                    "hand_number": 1,
                    "street": "preflop",
                    "actor": "player_a",
                    "action_type": "raise",
                    "amount": 60.0,
                    "pot": 30.0,
                    "current_bet": 20.0,
                    "preflop_raise_count": 0,
                    "stacks": {"player_a": 1500.0, "player_b": 1500.0},
                },
                {
                    "hand_number": 1,
                    "street": "preflop",
                    "actor": "player_b",
                    "action_type": "fold",
                    "amount": None,
                    "pot": 90.0,
                    "current_bet": 60.0,
                    "preflop_raise_count": 1,
                    "stacks": {"player_a": 1440.0, "player_b": 1500.0},
                },
                {
                    "hand_number": 2,
                    "street": "preflop",
                    "actor": "player_b",
                    "action_type": "raise",
                    "amount": 60.0,
                    "pot": 30.0,
                    "current_bet": 20.0,
                    "preflop_raise_count": 0,
                    "stacks": {"player_a": 1530.0, "player_b": 1470.0},
                },
            ],
            "ev_records": [],
        }

        loaded = TournamentRecord.from_dict(v2_data)

        assert loaded.tournament_id == "test_v2"
        # Actions should be grouped into hands
        assert len(loaded.hands) == 2
        assert loaded.hands[0].hand_number == 1
        assert len(loaded.hands[0].actions) == 2
        assert loaded.hands[1].hand_number == 2
        assert len(loaded.hands[1].actions) == 1

    def test_actions_property_flattens_hands(self):
        """Test that the actions property returns flattened action list."""
        tournament = TournamentRecord(
            tournament_id="test_flatten",
            timestamp="20251213_120000",
            players=["player_a", "player_b"],
            hands=[
                HandRecord(
                    hand_number=1,
                    actions=[
                        MinimalAction(1, "preflop", "player_a", "raise", 60.0, 30.0, 20.0, 0),
                        MinimalAction(1, "preflop", "player_b", "call", 60.0, 90.0, 60.0, 1),
                    ],
                ),
                HandRecord(
                    hand_number=2,
                    actions=[
                        MinimalAction(2, "preflop", "player_a", "fold", None, 30.0, 20.0, 0),
                    ],
                ),
            ],
        )

        all_actions = tournament.actions
        assert len(all_actions) == 3


# =============================================================================
# Statistics Recalculation Tests
# =============================================================================


class TestStatisticsRecalculation:
    """Tests for statistics recalculation from saved game states."""

    def test_recalculate_from_single_tournament(self):
        """Test recalculating stats from a single tournament file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a tournament with known statistics
            gamestates_dir = Path(tmpdir) / "gamestates"
            gamestates_dir.mkdir()

            tournament_data = {
                "tournament_id": "stats_test",
                "timestamp": "20251213_120000",
                "format_version": 3,
                "players": ["player_a", "player_b", "player_c"],
                "hands": [
                    {
                        "hand_number": 1,
                        "small_blind": 10.0,
                        "big_blind": 20.0,
                        "starting_stacks": {
                            "player_a": 1490.0,
                            "player_b": 1480.0,
                            "player_c": 1500.0,
                        },
                        "finishing_stacks": {
                            "player_a": 1550.0,
                            "player_b": 1450.0,
                            "player_c": 1500.0,
                        },
                        "actions": [
                            # player_a raises (PFR)
                            {
                                "street": "preflop",
                                "actor": "player_a",
                                "action_type": "raise",
                                "amount": 60.0,
                                "pot": 30.0,
                                "current_bet": 20.0,
                                "preflop_raise_count": 0,
                                "stacks": {
                                    "player_a": 1490.0,
                                    "player_b": 1480.0,
                                    "player_c": 1500.0,
                                },
                            },
                            # player_b calls (VPIP, no PFR)
                            {
                                "street": "preflop",
                                "actor": "player_b",
                                "action_type": "call",
                                "amount": 60.0,
                                "pot": 90.0,
                                "current_bet": 60.0,
                                "preflop_raise_count": 1,
                                "stacks": {
                                    "player_a": 1430.0,
                                    "player_b": 1480.0,
                                    "player_c": 1500.0,
                                },
                            },
                            # player_c folds (no VPIP)
                            {
                                "street": "preflop",
                                "actor": "player_c",
                                "action_type": "fold",
                                "amount": None,
                                "pot": 140.0,
                                "current_bet": 60.0,
                                "preflop_raise_count": 1,
                                "stacks": {
                                    "player_a": 1430.0,
                                    "player_b": 1420.0,
                                    "player_c": 1500.0,
                                },
                            },
                        ],
                    },
                    {
                        "hand_number": 2,
                        "small_blind": 10.0,
                        "big_blind": 20.0,
                        "starting_stacks": {
                            "player_a": 1540.0,
                            "player_b": 1430.0,
                            "player_c": 1500.0,
                        },
                        "finishing_stacks": {
                            "player_a": 1540.0,
                            "player_b": 1460.0,
                            "player_c": 1500.0,
                        },
                        "actions": [
                            # player_a folds (no VPIP)
                            {
                                "street": "preflop",
                                "actor": "player_a",
                                "action_type": "fold",
                                "amount": None,
                                "pot": 30.0,
                                "current_bet": 20.0,
                                "preflop_raise_count": 0,
                                "stacks": {
                                    "player_a": 1540.0,
                                    "player_b": 1430.0,
                                    "player_c": 1500.0,
                                },
                            },
                            # player_b raises (VPIP + PFR)
                            {
                                "street": "preflop",
                                "actor": "player_b",
                                "action_type": "raise",
                                "amount": 60.0,
                                "pot": 30.0,
                                "current_bet": 20.0,
                                "preflop_raise_count": 0,
                                "stacks": {
                                    "player_a": 1540.0,
                                    "player_b": 1430.0,
                                    "player_c": 1500.0,
                                },
                            },
                            # player_c folds (no VPIP)
                            {
                                "street": "preflop",
                                "actor": "player_c",
                                "action_type": "fold",
                                "amount": None,
                                "pot": 90.0,
                                "current_bet": 60.0,
                                "preflop_raise_count": 1,
                                "stacks": {
                                    "player_a": 1540.0,
                                    "player_b": 1370.0,
                                    "player_c": 1500.0,
                                },
                            },
                        ],
                    },
                ],
                "hand_summaries": [],
            }

            # Save tournament file
            tournament_file = gamestates_dir / "tournament_20251213_120000_stats_test.json"
            with open(tournament_file, "w") as f:
                json.dump(tournament_data, f)

            # Recalculate stats
            output_path = Path(tmpdir) / "calibrated_stats.json"
            kb = recalculate_baseline_stats(
                gamestates_dir=str(gamestates_dir),
                output_path=str(output_path),
            )

            # Verify statistics
            assert "player_a" in kb.profiles
            assert "player_b" in kb.profiles
            assert "player_c" in kb.profiles

            # player_a: 1 VPIP out of 2 hands = 50%, 1 PFR out of 2 = 50%
            stats_a = kb.profiles["player_a"].statistics
            assert stats_a.hands_played == 2
            assert stats_a.vpip == 50.0
            assert stats_a.pfr == 50.0

            # player_b: 2 VPIP out of 2 hands = 100%, 1 PFR out of 2 = 50%
            stats_b = kb.profiles["player_b"].statistics
            assert stats_b.hands_played == 2
            assert stats_b.vpip == 100.0
            assert stats_b.pfr == 50.0

            # player_c: 0 VPIP out of 2 hands = 0%, 0 PFR
            stats_c = kb.profiles["player_c"].statistics
            assert stats_c.hands_played == 2
            assert stats_c.vpip == 0.0
            assert stats_c.pfr == 0.0

            # Verify output file was created
            assert output_path.exists()

    def test_recalculate_empty_directory(self):
        """Test recalculation with no tournament files returns empty KnowledgeBase."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gamestates_dir = Path(tmpdir) / "gamestates"
            gamestates_dir.mkdir()

            output_path = Path(tmpdir) / "calibrated_stats.json"
            kb = recalculate_baseline_stats(
                gamestates_dir=str(gamestates_dir),
                output_path=str(output_path),
            )

            assert len(kb.profiles) == 0

    def test_ev_stats_accumulated_during_recalculation(self):
        """Test that EV statistics are properly accumulated during recalculation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gamestates_dir = Path(tmpdir) / "gamestates"
            gamestates_dir.mkdir()

            tournament_data = {
                "tournament_id": "ev_test",
                "timestamp": "20251213_130000",
                "format_version": 3,
                "players": ["player_a", "player_b"],
                "hands": [
                    {
                        "hand_number": 1,
                        "small_blind": 10.0,
                        "big_blind": 20.0,
                        "starting_stacks": {"player_a": 1500.0, "player_b": 1500.0},
                        "finishing_stacks": {"player_a": 2000.0, "player_b": 1000.0},
                        "actions": [
                            {
                                "street": "preflop",
                                "actor": "player_a",
                                "action_type": "all_in",
                                "amount": 1500.0,
                                "pot": 30.0,
                                "current_bet": 20.0,
                                "preflop_raise_count": 0,
                                "stacks": {"player_a": 1500.0, "player_b": 1500.0},
                            },
                            {
                                "street": "preflop",
                                "actor": "player_b",
                                "action_type": "call",
                                "amount": 1500.0,
                                "pot": 1530.0,
                                "current_bet": 1500.0,
                                "preflop_raise_count": 1,
                                "stacks": {"player_a": 0.0, "player_b": 1500.0},
                            },
                        ],
                        "ev_records": [
                            {
                                "hand_number": 1,
                                "player_id": "player_a",
                                "equity": 0.82,
                                "pot_size": 3000.0,
                                "amount_invested": 1500.0,
                                "ev_chips": 960.0,  # (0.82 * 3000) - 1500
                                "actual_chips": 1500.0,  # Won
                                "variance": 540.0,
                                "ev_adjusted": 960.0,
                            },
                            {
                                "hand_number": 1,
                                "player_id": "player_b",
                                "equity": 0.18,
                                "pot_size": 3000.0,
                                "amount_invested": 1500.0,
                                "ev_chips": -960.0,  # (0.18 * 3000) - 1500
                                "actual_chips": -1500.0,  # Lost
                                "variance": -540.0,
                                "ev_adjusted": -960.0,
                            },
                        ],
                    },
                ],
                "hand_summaries": [],
            }

            tournament_file = gamestates_dir / "tournament_20251213_130000_ev_test.json"
            with open(tournament_file, "w") as f:
                json.dump(tournament_data, f)

            output_path = Path(tmpdir) / "calibrated_stats.json"
            kb = recalculate_baseline_stats(
                gamestates_dir=str(gamestates_dir),
                output_path=str(output_path),
            )

            # Verify EV stats
            stats_a = kb.profiles["player_a"].statistics
            assert stats_a.showdown_count == 1
            assert abs(stats_a.ev_adjusted_total - 960.0) < 1.0

            stats_b = kb.profiles["player_b"].statistics
            assert stats_b.showdown_count == 1
            assert abs(stats_b.ev_adjusted_total - (-960.0)) < 1.0


# =============================================================================
# MinimalAction Tests
# =============================================================================


class TestMinimalAction:
    """Tests for MinimalAction conversion and stub state generation."""

    def test_from_full_state_conversion(self):
        """Test converting full game state to minimal action."""
        state = make_game_state(
            hand_number=5,
            street=Street.FLOP,
            pot=200.0,
            current_bet=50.0,
            action_history=[
                {"street": "preflop", "action": "raise"},
                {"street": "preflop", "action": "call"},
            ],
        )
        action = Action(type=ActionType.BET, amount=100.0)

        minimal = MinimalAction.from_full_state(state, "player_a", action)

        assert minimal.hand_number == 5
        assert minimal.street == "flop"
        assert minimal.actor == "player_a"
        assert minimal.action_type == "bet"
        assert minimal.amount == 100.0
        assert minimal.pot == 200.0
        assert minimal.current_bet == 50.0
        assert minimal.preflop_raise_count == 1  # One raise in action history

    def test_to_stub_game_state(self):
        """Test creating stub game state for statistics tracking."""
        minimal = MinimalAction(
            hand_number=3,
            street="turn",
            actor="player_b",
            action_type="raise",
            amount=150.0,
            pot=400.0,
            current_bet=75.0,
            preflop_raise_count=2,
        )

        stub = minimal.to_stub_game_state(big_blind=20.0)

        assert stub.hand_number == 3
        assert stub.street == Street.TURN
        assert stub.pot == 400.0
        assert stub.current_bet == 75.0
        assert stub.big_blind == 20.0
        assert stub.preflop_raise_count == 2
        # Action history should have synthetic entries for 3-bet detection
        assert len(stub.action_history) == 2

    def test_to_action_conversion(self):
        """Test converting MinimalAction back to Action."""
        minimal = MinimalAction(
            hand_number=1,
            street="preflop",
            actor="player_a",
            action_type="raise",
            amount=60.0,
            pot=30.0,
            current_bet=20.0,
            preflop_raise_count=0,
        )

        action = minimal.to_action()

        assert action.type == ActionType.RAISE
        assert action.amount == 60.0


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for the full history -> statistics -> summary pipeline."""

    def test_full_tournament_recording_and_recalculation(self):
        """Test recording a tournament, saving it, and recalculating statistics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gamestates_dir = Path(tmpdir) / "gamestates"

            # 1. Record a tournament
            recorder = GameStateRecorder(gamestates_dir=str(gamestates_dir))
            recorder.start_tournament("integration_test")

            # Hand 1: player_a raises, player_b calls, player_c folds
            state1 = make_game_state(hand_number=1)
            recorder.record_action(state1, "player_a", Action(type=ActionType.RAISE, amount=60.0))

            state1_after_raise = make_game_state(
                hand_number=1,
                pot=90.0,
                current_bet=60.0,
                action_history=[{"street": "preflop", "action": "raise"}],
            )
            recorder.record_action(
                state1_after_raise, "player_b", Action(type=ActionType.CALL, amount=60.0)
            )
            recorder.record_action(state1_after_raise, "player_c", Action(type=ActionType.FOLD))
            recorder.record_hand_result(
                {"player_a": 1560.0, "player_b": 1440.0, "player_c": 1500.0}
            )

            # Hand 2: player_b raises, others fold
            state2 = make_game_state(hand_number=2)
            recorder.record_action(state2, "player_a", Action(type=ActionType.FOLD))
            recorder.record_action(state2, "player_b", Action(type=ActionType.RAISE, amount=60.0))
            recorder.record_action(state2, "player_c", Action(type=ActionType.FOLD))
            recorder.record_hand_result(
                {"player_a": 1560.0, "player_b": 1470.0, "player_c": 1470.0}
            )

            # 2. Save tournament
            filepath = recorder.save_tournament()
            assert filepath is not None

            # 3. Load and verify tournament structure
            loaded = GameStateRecorder.load_tournament(filepath)
            assert len(loaded.hands) == 2
            assert len(loaded.hands[0].actions) == 3
            assert len(loaded.hands[1].actions) == 3

            # 4. Verify hand summaries
            data = json.loads(Path(filepath).read_text())
            assert "hand_summaries" in data
            assert len(data["hand_summaries"]) == 2

            # 5. Recalculate statistics
            output_path = Path(tmpdir) / "stats.json"
            kb = recalculate_baseline_stats(
                gamestates_dir=str(gamestates_dir),
                output_path=str(output_path),
            )

            # 6. Verify recalculated stats
            assert kb.profiles["player_a"].statistics.hands_played == 2
            assert kb.profiles["player_b"].statistics.hands_played == 2
            assert kb.profiles["player_c"].statistics.hands_played == 2

            # player_a: raised hand 1, folded hand 2 -> VPIP 50%, PFR 50%
            assert kb.profiles["player_a"].statistics.vpip == 50.0
            assert kb.profiles["player_a"].statistics.pfr == 50.0

            # player_b: called hand 1, raised hand 2 -> VPIP 100%, PFR 50%
            assert kb.profiles["player_b"].statistics.vpip == 100.0
            assert kb.profiles["player_b"].statistics.pfr == 50.0
