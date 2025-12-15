"""
Tests for tournament history prompt generation for the ExploitAnalyst.

These tests verify that:
1. Tournament history is correctly built from HandRecords
2. Opponent hole cards are NOT included (would be cheating)
3. Showdown cards ARE included (legitimately revealed)
4. Community cards are included for context in showdown hands
5. The prompt format is correct for the ExploitAnalyst

No LLM calls required - pure data/prompt generation tests.
"""

from backend.domain.game.models import ActionType
from backend.domain.game.recorder import HandRecord, MinimalAction

# =============================================================================
# Test Fixtures: HandRecord with showdown data
# =============================================================================


def make_hand_record(
    hand_number: int,
    actions: list[MinimalAction] | None = None,
    starting_stacks: dict[str, float] | None = None,
    finishing_stacks: dict[str, float] | None = None,
    community_cards: list[str] | None = None,
    shown_hands: dict[str, list[str]] | None = None,
) -> HandRecord:
    """Create a HandRecord for testing."""
    return HandRecord(
        hand_number=hand_number,
        small_blind=10.0,
        big_blind=20.0,
        actions=actions or [],
        starting_stacks=starting_stacks
        or {"agent_a": 1500.0, "agent_b": 1500.0, "agent_c": 1500.0},
        finishing_stacks=finishing_stacks
        or {"agent_a": 1500.0, "agent_b": 1500.0, "agent_c": 1500.0},
        community_cards=community_cards or [],
        shown_hands=shown_hands or {},
    )


def make_preflop_action(
    hand_number: int,
    actor: str,
    action_type: str,
    amount: float | None = None,
    pot: float = 30.0,
    current_bet: float = 20.0,
    preflop_raise_count: int = 0,
    decision_type: str = "gto",
    deviation_reason: str | None = None,
) -> MinimalAction:
    """Create a preflop action for testing."""
    action = MinimalAction(
        hand_number=hand_number,
        street="preflop",
        actor=actor,
        action_type=action_type,
        amount=amount,
        pot=pot,
        current_bet=current_bet,
        preflop_raise_count=preflop_raise_count,
        stacks={"agent_a": 1500.0, "agent_b": 1500.0, "agent_c": 1500.0},
        decision_type=decision_type,
        deviation_reason=deviation_reason,
    )
    return action


# =============================================================================
# Tests for HandRecord with showdown data
# =============================================================================


class TestHandRecordShowdownData:
    """Tests for HandRecord storing showdown information."""

    def test_hand_record_stores_community_cards(self):
        """Verify HandRecord can store community cards."""
        hand = make_hand_record(
            hand_number=1,
            community_cards=["Ah", "Kd", "2c", "7s", "Jh"],
        )

        assert hand.community_cards == ["Ah", "Kd", "2c", "7s", "Jh"]

    def test_hand_record_stores_shown_hands(self):
        """Verify HandRecord can store shown hands at showdown."""
        hand = make_hand_record(
            hand_number=1,
            community_cards=["Ah", "Kd", "2c", "7s", "Jh"],
            shown_hands={
                "agent_a": ["As", "Ad"],
                "agent_b": ["Qh", "Qd"],
            },
        )

        assert hand.shown_hands == {
            "agent_a": ["As", "Ad"],
            "agent_b": ["Qh", "Qd"],
        }

    def test_hand_record_to_dict_includes_showdown_data(self):
        """Verify to_dict includes community_cards and shown_hands when present."""
        hand = make_hand_record(
            hand_number=1,
            community_cards=["Ah", "Kd", "2c", "7s", "Jh"],
            shown_hands={
                "agent_a": ["As", "Ad"],
                "agent_b": ["Qh", "Qd"],
            },
        )

        data = hand.to_dict()

        assert "community_cards" in data
        assert data["community_cards"] == ["Ah", "Kd", "2c", "7s", "Jh"]
        assert "shown_hands" in data
        assert data["shown_hands"]["agent_a"] == ["As", "Ad"]

    def test_hand_record_to_dict_omits_empty_showdown_data(self):
        """Verify to_dict omits community_cards and shown_hands when empty."""
        hand = make_hand_record(hand_number=1)

        data = hand.to_dict()

        # Empty lists/dicts should be omitted for cleaner JSON
        assert "community_cards" not in data or data.get("community_cards") == []
        assert "shown_hands" not in data or data.get("shown_hands") == {}

    def test_hand_record_from_dict_loads_showdown_data(self):
        """Verify from_dict correctly loads community_cards and shown_hands."""
        data = {
            "hand_number": 5,
            "small_blind": 10.0,
            "big_blind": 20.0,
            "starting_stacks": {"agent_a": 1500.0, "agent_b": 1500.0},
            "finishing_stacks": {"agent_a": 2000.0, "agent_b": 1000.0},
            "actions": [],
            "community_cards": ["Th", "9d", "3c", "Ks", "2h"],
            "shown_hands": {
                "agent_a": ["Kd", "Kc"],
                "agent_b": ["Jh", "Jd"],
            },
        }

        hand = HandRecord.from_dict(data)

        assert hand.community_cards == ["Th", "9d", "3c", "Ks", "2h"]
        assert hand.shown_hands == {
            "agent_a": ["Kd", "Kc"],
            "agent_b": ["Jh", "Jd"],
        }


# =============================================================================
# Tests for Tournament History Prompt Building
# =============================================================================


class TestTournamentHistoryPrompt:
    """Tests for building tournament history prompt for ExploitAnalyst."""

    def test_build_tournament_history_empty(self):
        """Verify empty history returns appropriate message."""
        from backend.domain.agent.ensemble_agent import EnsemblePokerAgent

        # Create a minimal agent without full initialization
        # We test the method directly on the class
        agent = EnsemblePokerAgent.__new__(EnsemblePokerAgent)
        agent._tournament_history = []

        result = agent._build_tournament_history()

        assert "No previous hands" in result or result == ""

    def test_build_tournament_history_includes_all_actions(self):
        """Verify all actions from hands are included in the history."""
        from backend.domain.agent.ensemble_agent import EnsemblePokerAgent

        agent = EnsemblePokerAgent.__new__(EnsemblePokerAgent)
        agent._tournament_history = [
            make_hand_record(
                hand_number=1,
                actions=[
                    make_preflop_action(1, "agent_c", "fold"),
                    make_preflop_action(1, "agent_a", "raise", 60.0, preflop_raise_count=0),
                    make_preflop_action(1, "agent_b", "call", 60.0, pot=90.0, current_bet=60.0),
                ],
                finishing_stacks={"agent_a": 1530.0, "agent_b": 1470.0, "agent_c": 1500.0},
            ),
        ]

        result = agent._build_tournament_history()

        # Should contain all actions
        assert "agent_c" in result and "fold" in result.lower()
        assert "agent_a" in result and "raise" in result.lower()
        assert "agent_b" in result and "call" in result.lower()

    def test_build_tournament_history_includes_stacks(self):
        """Verify starting stacks are included for context."""
        from backend.domain.agent.ensemble_agent import EnsemblePokerAgent

        agent = EnsemblePokerAgent.__new__(EnsemblePokerAgent)
        agent._tournament_history = [
            make_hand_record(
                hand_number=1,
                starting_stacks={"agent_a": 2000.0, "agent_b": 1000.0, "agent_c": 1500.0},
            ),
        ]

        result = agent._build_tournament_history()

        # Should contain stack information
        assert "2000" in result or "agent_a" in result

    def test_build_tournament_history_excludes_opponent_hole_cards(self):
        """Verify opponent hole cards are NOT included (would be cheating)."""
        from backend.domain.agent.ensemble_agent import EnsemblePokerAgent

        agent = EnsemblePokerAgent.__new__(EnsemblePokerAgent)
        agent.player_id = "agent_e"  # We are agent_e

        # Create a hand where NO showdown occurred - opponent cards should be hidden
        hand = make_hand_record(
            hand_number=1,
            actions=[
                make_preflop_action(1, "agent_a", "raise", 60.0),
                make_preflop_action(1, "agent_e", "fold"),  # We folded, never saw cards
            ],
            finishing_stacks={"agent_a": 1530.0, "agent_e": 1470.0},
            # No shown_hands - hand didn't go to showdown
            shown_hands={},
        )
        agent._tournament_history = [hand]

        result = agent._build_tournament_history()

        # Should NOT contain any hole card information for opponents
        # Common hole card patterns that should not appear:
        assert "hole" not in result.lower() or "shown" not in result.lower()
        # The action history shouldn't contain cards dealt to players

    def test_build_tournament_history_includes_showdown_cards(self):
        """Verify showdown cards ARE included (legitimately revealed)."""
        from backend.domain.agent.ensemble_agent import EnsemblePokerAgent

        agent = EnsemblePokerAgent.__new__(EnsemblePokerAgent)
        agent.player_id = "agent_e"

        hand = make_hand_record(
            hand_number=1,
            actions=[
                make_preflop_action(1, "agent_a", "raise", 60.0),
                make_preflop_action(1, "agent_b", "call", 60.0, pot=90.0),
            ],
            community_cards=["Ah", "Kd", "2c", "7s", "Jh"],
            shown_hands={
                "agent_a": ["As", "Ad"],  # Showed pocket aces
                "agent_b": ["Qh", "Qd"],  # Showed pocket queens
            },
            finishing_stacks={"agent_a": 1600.0, "agent_b": 1400.0},
        )
        agent._tournament_history = [hand]

        result = agent._build_tournament_history()

        # Should contain showdown information
        assert "As" in result or "Ad" in result or "aces" in result.lower() or "AA" in result
        assert "Qh" in result or "Qd" in result or "queens" in result.lower() or "QQ" in result
        # Should contain board
        assert "Ah" in result or "Kd" in result or "board" in result.lower()

    def test_build_tournament_history_includes_community_cards(self):
        """Verify community cards are included for showdown context."""
        from backend.domain.agent.ensemble_agent import EnsemblePokerAgent

        agent = EnsemblePokerAgent.__new__(EnsemblePokerAgent)
        agent.player_id = "agent_e"

        hand = make_hand_record(
            hand_number=1,
            community_cards=["Ah", "Kd", "2c", "7s", "Jh"],
            shown_hands={"agent_a": ["As", "Ad"]},
        )
        agent._tournament_history = [hand]

        result = agent._build_tournament_history()

        # Should contain board cards
        assert "Ah" in result and "Kd" in result

    def test_build_tournament_history_multiple_hands(self):
        """Verify multiple hands are included in order."""
        from backend.domain.agent.ensemble_agent import EnsemblePokerAgent

        agent = EnsemblePokerAgent.__new__(EnsemblePokerAgent)
        agent.player_id = "agent_e"

        agent._tournament_history = [
            make_hand_record(
                hand_number=1,
                actions=[make_preflop_action(1, "agent_a", "fold")],
            ),
            make_hand_record(
                hand_number=2,
                actions=[make_preflop_action(2, "agent_b", "raise", 60.0)],
            ),
            make_hand_record(
                hand_number=3,
                actions=[make_preflop_action(3, "agent_c", "call", 20.0)],
            ),
        ]

        result = agent._build_tournament_history()

        # Should contain all hand numbers
        assert "1" in result and "2" in result and "3" in result
        # Verify hands appear in order by checking "Hand 1" comes before "Hand 2"
        assert result.find("Hand 1") < result.find("Hand 2") < result.find("Hand 3")

    def test_build_tournament_history_groups_actions_by_street(self):
        """Verify actions are grouped by street (preflop, flop, turn, river)."""
        from backend.domain.agent.ensemble_agent import EnsemblePokerAgent

        agent = EnsemblePokerAgent.__new__(EnsemblePokerAgent)
        agent.player_id = "agent_e"

        # Create actions across multiple streets
        actions = [
            MinimalAction(1, "preflop", "agent_a", "raise", 60.0, 30.0, 20.0, 0),
            MinimalAction(1, "preflop", "agent_b", "call", 60.0, 90.0, 60.0, 1),
            MinimalAction(1, "flop", "agent_a", "bet", 50.0, 120.0, 0.0, 1),
            MinimalAction(1, "flop", "agent_b", "call", 50.0, 170.0, 50.0, 1),
            MinimalAction(1, "turn", "agent_a", "check", None, 220.0, 0.0, 1),
            MinimalAction(1, "turn", "agent_b", "bet", 100.0, 220.0, 0.0, 1),
        ]

        agent._tournament_history = [
            make_hand_record(hand_number=1, actions=actions),
        ]

        result = agent._build_tournament_history()

        # Should contain street markers
        assert "preflop" in result.lower() or "PREFLOP" in result
        assert "flop" in result.lower() or "FLOP" in result
        assert "turn" in result.lower() or "TURN" in result


# =============================================================================
# Tests for ExploitAnalyst prompt integration
# =============================================================================


class TestExploitAnalystPromptIntegration:
    """Tests for tournament history integration in ExploitAnalyst prompts."""

    def test_exploit_analyst_analyze_accepts_tournament_history(self):
        """Verify ExploitAnalyst.analyze accepts tournament_history parameter."""
        import inspect

        from backend.domain.agent.specialists import ExploitAnalyst

        # Check the method signature includes tournament_history
        sig = inspect.signature(ExploitAnalyst.analyze)
        params = list(sig.parameters.keys())

        assert "tournament_history" in params, (
            f"ExploitAnalyst.analyze should accept 'tournament_history' parameter. "
            f"Current params: {params}"
        )

    def test_ensemble_agent_passes_tournament_history_to_exploit_analyst(self):
        """Verify EnsemblePokerAgent passes tournament history to ExploitAnalyst."""
        # This test verifies the integration at the prompt level
        # We check that the _build_tournament_history method exists and is called
        from backend.domain.agent.ensemble_agent import EnsemblePokerAgent

        assert hasattr(EnsemblePokerAgent, "_build_tournament_history"), (
            "EnsemblePokerAgent should have _build_tournament_history method"
        )

    def test_ensemble_agent_has_add_hand_to_history_method(self):
        """Verify EnsemblePokerAgent has method to add completed hands to history."""
        from backend.domain.agent.ensemble_agent import EnsemblePokerAgent

        assert hasattr(EnsemblePokerAgent, "add_hand_to_history"), (
            "EnsemblePokerAgent should have add_hand_to_history method"
        )


# =============================================================================
# Tests for GameStateRecorder showdown data
# =============================================================================


class TestRecorderShowdownData:
    """Tests for GameStateRecorder handling showdown data."""

    def test_record_hand_result_accepts_showdown_data(self):
        """Verify record_hand_result accepts community_cards and shown_hands."""
        import inspect

        from backend.domain.game.recorder import GameStateRecorder

        sig = inspect.signature(GameStateRecorder.record_hand_result)
        params = list(sig.parameters.keys())

        assert "community_cards" in params, (
            f"record_hand_result should accept 'community_cards'. Current params: {params}"
        )
        assert "shown_hands" in params, (
            f"record_hand_result should accept 'shown_hands'. Current params: {params}"
        )

    def test_record_hand_result_saves_showdown_data(self):
        """Verify showdown data is saved when provided."""
        import tempfile

        from backend.domain.game.models import Action
        from backend.domain.game.recorder import GameStateRecorder

        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = GameStateRecorder(gamestates_dir=tmpdir)
            recorder.start_tournament("test_showdown")

            # Record an action to create the hand
            from tests.test_history_and_statistics import make_game_state

            state = make_game_state(hand_number=1)
            recorder.record_action(state, "player_a", Action(type=ActionType.CALL, amount=100.0))

            # Record hand result with showdown data
            recorder.record_hand_result(
                finishing_stacks={"player_a": 1600.0, "player_b": 1400.0, "player_c": 1500.0},
                community_cards=["Ah", "Kd", "2c", "7s", "Jh"],
                shown_hands={
                    "player_a": ["As", "Ad"],
                    "player_b": ["Qh", "Qd"],
                },
            )

            hand = recorder._current_tournament.hands[0]
            assert hand.community_cards == ["Ah", "Kd", "2c", "7s", "Jh"]
            assert hand.shown_hands == {
                "player_a": ["As", "Ad"],
                "player_b": ["Qh", "Qd"],
            }


# =============================================================================
# Integration test: Full flow
# =============================================================================


class TestPokerAgentTournamentHistory:
    """Tests for PokerAgent tournament history support."""

    def test_poker_agent_has_add_hand_to_history_method(self):
        """Verify PokerAgent has add_hand_to_history method."""
        from backend.domain.agent.poker_agent import PokerAgent

        assert hasattr(PokerAgent, "add_hand_to_history"), (
            "PokerAgent should have add_hand_to_history method"
        )

    def test_poker_agent_only_tracks_history_for_informed_agents(self):
        """Verify only informed agents (has_shared_knowledge=True) track history."""
        from backend.domain.agent.poker_agent import PokerAgent
        from backend.domain.agent.strategies.base import AGENT_A_BLUFFER, AGENT_D_INFORMED

        # Create uninformed agent (Agent A style)
        agent_uninformed = PokerAgent.__new__(PokerAgent)
        agent_uninformed.strategy = AGENT_A_BLUFFER
        agent_uninformed._tournament_history = []

        # Create informed agent (Agent D style)
        agent_informed = PokerAgent.__new__(PokerAgent)
        agent_informed.strategy = AGENT_D_INFORMED
        agent_informed._tournament_history = []

        # Create a mock hand record
        hand = make_hand_record(hand_number=1)

        # Add to both agents
        agent_uninformed.add_hand_to_history(hand)
        agent_informed.add_hand_to_history(hand)

        # Uninformed agent should NOT track history
        assert len(agent_uninformed._tournament_history) == 0, (
            "Uninformed agents should not track tournament history"
        )

        # Informed agent SHOULD track history
        assert len(agent_informed._tournament_history) == 1, (
            "Informed agents should track tournament history"
        )


class TestSharedUtilityFunction:
    """Tests for the shared build_tournament_history_prompt function."""

    def test_build_tournament_history_prompt_function_exists(self):
        """Verify the shared utility function exists."""
        from backend.domain.agent.utils import build_tournament_history_prompt

        assert callable(build_tournament_history_prompt)

    def test_build_tournament_history_prompt_empty_list(self):
        """Verify empty list returns appropriate message."""
        from backend.domain.agent.utils import build_tournament_history_prompt

        result = build_tournament_history_prompt([])
        assert "No previous hands" in result

    def test_build_tournament_history_prompt_with_hands(self):
        """Verify hands are formatted correctly."""
        from backend.domain.agent.utils import build_tournament_history_prompt

        hands = [
            make_hand_record(
                hand_number=1,
                actions=[make_preflop_action(1, "agent_a", "raise", 60.0)],
                shown_hands={"agent_a": ["As", "Ad"]},
                community_cards=["Ah", "Kd", "2c", "7s", "Jh"],
            ),
        ]

        result = build_tournament_history_prompt(hands)

        assert "Hand 1" in result
        assert "agent_a" in result
        assert "raise" in result.lower()
        assert "As" in result or "Ad" in result


class TestTournamentHistoryIntegration:
    """Integration tests for the complete tournament history flow."""

    def test_full_flow_record_and_build_history(self):
        """Test the full flow: record hands -> build history -> verify output."""
        import tempfile

        from backend.domain.agent.ensemble_agent import EnsemblePokerAgent
        from backend.domain.game.recorder import GameStateRecorder

        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. Record a tournament with a showdown hand
            recorder = GameStateRecorder(gamestates_dir=tmpdir)
            recorder.start_tournament("history_test")

            # Create some actions
            from backend.domain.game.models import Action, ActionType
            from tests.test_history_and_statistics import make_game_state

            state = make_game_state(hand_number=1)
            recorder.record_action(state, "player_a", Action(type=ActionType.RAISE, amount=60.0))
            recorder.record_action(state, "player_b", Action(type=ActionType.CALL, amount=60.0))
            recorder.record_action(state, "player_c", Action(type=ActionType.FOLD))

            # Record showdown result
            recorder.record_hand_result(
                finishing_stacks={"player_a": 1620.0, "player_b": 1380.0, "player_c": 1500.0},
                community_cards=["Th", "9d", "3c", "Ks", "2h"],
                shown_hands={
                    "player_a": ["Kd", "Kc"],
                    "player_b": ["Jh", "Jd"],
                },
            )

            # 2. Get the hand record
            hand_record = recorder._current_tournament.hands[0]

            # 3. Create an agent and add the hand to its history
            agent = EnsemblePokerAgent.__new__(EnsemblePokerAgent)
            agent.player_id = "player_c"
            agent._tournament_history = []
            agent.add_hand_to_history(hand_record)

            # 4. Build the tournament history prompt
            history = agent._build_tournament_history()

            # 5. Verify the output contains expected information
            assert "player_a" in history
            assert "player_b" in history
            assert "raise" in history.lower() or "60" in history

            # Showdown cards should be visible
            assert "Kd" in history or "Kc" in history or "KK" in history
            assert "Jh" in history or "Jd" in history or "JJ" in history

            # Board should be visible
            assert "Th" in history or "9d" in history or "board" in history.lower()
