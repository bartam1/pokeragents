"""
Tests for PokerEnvironment player elimination and seat mapping.

These tests verify critical functionality:
1. Seat index mapping between original indices and PokerKit indices
2. Proper handling of eliminated players (0 stack)
3. Multi-hand tournaments continuing after eliminations
4. Correct player being prompted to act after eliminations
5. Winner indices correctly mapped to original seat indices
"""

import pytest

from backend.domain.game.environment import PokerEnvironment
from backend.domain.game.models import Action, ActionType


class TestSeatMapping:
    """Test seat index translation between original and PokerKit indices."""

    def test_initial_mapping_all_players_active(self):
        """All players active: mapping should be identity (0->0, 1->1, etc.)."""
        env = PokerEnvironment(
            player_names=["alice", "bob", "charlie", "diana", "eve"],
            starting_stack=1000,
            small_blind=10,
            big_blind=20,
        )
        env.start_hand()

        # All 5 players should be active
        assert len(env._active_original_seats) == 5
        assert env._active_original_seats == [0, 1, 2, 3, 4]

        # Mapping should be identity
        for i in range(5):
            assert env._original_to_pokerkit_seat(i) == i
            assert env._pokerkit_to_original_seat(i) == i

    def test_mapping_after_one_elimination(self):
        """After player 2 is eliminated, mapping should skip them."""
        env = PokerEnvironment(
            player_names=["alice", "bob", "charlie", "diana", "eve"],
            starting_stack=1000,
            small_blind=10,
            big_blind=20,
        )

        # Manually set stacks with one player at 0
        env._current_stacks = [1000.0, 1000.0, 0.0, 1000.0, 1000.0]

        env.start_hand()

        # Should have 4 active players
        assert len(env._active_original_seats) == 4
        assert env._active_original_seats == [0, 1, 3, 4]

        # Test mapping
        assert env._original_to_pokerkit_seat(0) == 0  # alice -> pk 0
        assert env._original_to_pokerkit_seat(1) == 1  # bob -> pk 1
        assert env._original_to_pokerkit_seat(2) is None  # charlie eliminated
        assert env._original_to_pokerkit_seat(3) == 2  # diana -> pk 2
        assert env._original_to_pokerkit_seat(4) == 3  # eve -> pk 3

        # Reverse mapping
        assert env._pokerkit_to_original_seat(0) == 0  # pk 0 -> alice
        assert env._pokerkit_to_original_seat(1) == 1  # pk 1 -> bob
        assert env._pokerkit_to_original_seat(2) == 3  # pk 2 -> diana
        assert env._pokerkit_to_original_seat(3) == 4  # pk 3 -> eve

    def test_mapping_after_multiple_eliminations(self):
        """Multiple eliminations should be handled correctly."""
        env = PokerEnvironment(
            player_names=["alice", "bob", "charlie", "diana", "eve"],
            starting_stack=1000,
            small_blind=10,
            big_blind=20,
        )

        # Players 1 (bob) and 3 (diana) eliminated
        env._current_stacks = [1000.0, 0.0, 1000.0, 0.0, 1000.0]

        env.start_hand()

        # Should have 3 active players
        assert len(env._active_original_seats) == 3
        assert env._active_original_seats == [0, 2, 4]

        # Test mapping
        assert env._original_to_pokerkit_seat(0) == 0  # alice -> pk 0
        assert env._original_to_pokerkit_seat(1) is None  # bob eliminated
        assert env._original_to_pokerkit_seat(2) == 1  # charlie -> pk 1
        assert env._original_to_pokerkit_seat(3) is None  # diana eliminated
        assert env._original_to_pokerkit_seat(4) == 2  # eve -> pk 2

    def test_heads_up_after_eliminations(self):
        """When only 2 players remain, mapping should work correctly."""
        env = PokerEnvironment(
            player_names=["alice", "bob", "charlie", "diana", "eve"],
            starting_stack=1000,
            small_blind=10,
            big_blind=20,
        )

        # Only players 0 (alice) and 4 (eve) remain
        env._current_stacks = [2500.0, 0.0, 0.0, 0.0, 2500.0]

        env.start_hand()

        assert len(env._active_original_seats) == 2
        assert env._active_original_seats == [0, 4]

        assert env._original_to_pokerkit_seat(0) == 0  # alice -> pk 0
        assert env._original_to_pokerkit_seat(4) == 1  # eve -> pk 1


class TestActorIndexAfterElimination:
    """Test that get_current_actor_index returns correct ORIGINAL seat index."""

    def test_actor_index_with_all_players(self):
        """With all players, actor index should match directly."""
        env = PokerEnvironment(
            player_names=["alice", "bob", "charlie", "diana", "eve"],
            starting_stack=1000,
            small_blind=10,
            big_blind=20,
        )
        env.start_hand()

        # First actor should be an original seat index (UTG = seat 2 in 5-player)
        actor_idx = env.get_current_actor_index()
        assert actor_idx is not None
        actor_name = env.player_names[actor_idx]
        assert actor_name in ["alice", "bob", "charlie", "diana", "eve"]

    def test_actor_index_after_elimination(self):
        """After elimination, actor index should be original seat index, not PokerKit index."""
        env = PokerEnvironment(
            player_names=["alice", "bob", "charlie", "diana", "eve"],
            starting_stack=1000,
            small_blind=10,
            big_blind=20,
        )

        # Eliminate charlie (seat 2)
        env._current_stacks = [1000.0, 1000.0, 0.0, 1000.0, 1000.0]
        env.start_hand()

        actor_idx = env.get_current_actor_index()
        assert actor_idx is not None

        # Actor should NOT be charlie (eliminated)
        assert actor_idx != 2

        # Name lookup should work with original index
        actor_name = env.player_names[actor_idx]
        assert actor_name in ["alice", "bob", "diana", "eve"]
        assert actor_name != "charlie"


class TestStructuredStateAfterElimination:
    """Test that get_structured_state includes all original players with correct info."""

    def test_structured_state_includes_eliminated_players(self):
        """Eliminated players should appear in state as inactive with 0 stack."""
        env = PokerEnvironment(
            player_names=["alice", "bob", "charlie", "diana", "eve"],
            starting_stack=1000,
            small_blind=10,
            big_blind=20,
        )

        # Eliminate charlie (seat 2)
        env._current_stacks = [1000.0, 1000.0, 0.0, 1000.0, 1000.0]
        env.start_hand()

        actor_idx = env.get_current_actor_index()
        state = env.get_structured_state(actor_idx)

        # Should have 5 players (all original)
        assert len(state.players) == 5

        # Check eliminated player
        charlie = state.players[2]
        assert charlie.name == "charlie"
        assert charlie.stack == 0.0
        assert charlie.is_active is False
        assert charlie.seat == 2

        # Check active players have correct info
        for i in [0, 1, 3, 4]:
            player = state.players[i]
            assert player.is_active is True or player.stack > 0

    def test_hero_hole_cards_with_elimination(self):
        """Hero should see their hole cards even after elimination mapping."""
        env = PokerEnvironment(
            player_names=["alice", "bob", "charlie", "diana", "eve"],
            starting_stack=1000,
            small_blind=10,
            big_blind=20,
        )

        # Eliminate alice (seat 0) - affects mapping
        env._current_stacks = [0.0, 1000.0, 1000.0, 1000.0, 1000.0]
        env.start_hand()

        # Get state for diana (original seat 3, now pk seat 2)
        state = env.get_structured_state(3)

        # Diana should see her hole cards
        diana = state.players[3]
        assert diana.name == "diana"
        assert diana.hole_cards is not None
        assert len(diana.hole_cards) == 2

        # Other active players should NOT see their cards
        for i in [1, 2, 4]:
            assert state.players[i].hole_cards is None


class TestExecuteActionAfterElimination:
    """Test that execute_action works with original seat indices after elimination."""

    def test_execute_action_with_original_index(self):
        """execute_action should accept original seat index, not PokerKit index."""
        env = PokerEnvironment(
            player_names=["alice", "bob", "charlie", "diana", "eve"],
            starting_stack=1000,
            small_blind=10,
            big_blind=20,
        )

        # Eliminate charlie (seat 2)
        env._current_stacks = [1000.0, 1000.0, 0.0, 1000.0, 1000.0]
        env.start_hand()

        # Get current actor (should be original index)
        actor_idx = env.get_current_actor_index()
        assert actor_idx != 2  # Not charlie

        # Execute action with original index
        result = env.execute_action(actor_idx, Action(type=ActionType.FOLD))
        assert result["success"] is True
        assert result["player"] == actor_idx  # Should return original index

    def test_execute_action_for_eliminated_player_fails(self):
        """Executing action for eliminated player should raise error."""
        env = PokerEnvironment(
            player_names=["alice", "bob", "charlie", "diana", "eve"],
            starting_stack=1000,
            small_blind=10,
            big_blind=20,
        )

        # Eliminate charlie (seat 2)
        env._current_stacks = [1000.0, 1000.0, 0.0, 1000.0, 1000.0]
        env.start_hand()

        # Try to execute action for eliminated player
        with pytest.raises(ValueError, match="has been eliminated"):
            env.execute_action(2, Action(type=ActionType.FOLD))


class TestCompleteHandAfterElimination:
    """Test that complete_hand returns correct original indices."""

    def test_winner_uses_original_index(self):
        """Winner index should be original seat index, not PokerKit index."""
        env = PokerEnvironment(
            player_names=["alice", "bob", "charlie", "diana", "eve"],
            starting_stack=1000,
            small_blind=10,
            big_blind=20,
        )

        # Eliminate charlie (seat 2)
        env._current_stacks = [1000.0, 1000.0, 0.0, 1000.0, 1000.0]
        env.start_hand()

        # Play until hand complete - everyone folds to last player
        while not env.is_hand_complete():
            actor_idx = env.get_current_actor_index()
            if actor_idx is None:
                break

            # Everyone folds
            legal = env.get_structured_state(actor_idx).legal_actions
            if ActionType.FOLD in legal:
                env.execute_action(actor_idx, Action(type=ActionType.FOLD))
            elif ActionType.CHECK in legal:
                env.execute_action(actor_idx, Action(type=ActionType.CHECK))
            else:
                env.execute_action(actor_idx, Action(type=ActionType.CALL))

        result = env.complete_hand()

        # Winner should be original index, not PokerKit index
        for winner in result.winners:
            assert winner in [0, 1, 3, 4]  # Not 2 (charlie - eliminated)
            winner_name = env.player_names[winner]
            assert winner_name in ["alice", "bob", "diana", "eve"]

    def test_stacks_updated_correctly_after_elimination(self):
        """Current stacks should update correctly for original indices."""
        env = PokerEnvironment(
            player_names=["alice", "bob", "charlie", "diana", "eve"],
            starting_stack=1000,
            small_blind=10,
            big_blind=20,
        )

        # Eliminate charlie (seat 2)
        env._current_stacks = [1000.0, 1000.0, 0.0, 1000.0, 1000.0]
        initial_total = sum(env._current_stacks)

        env.start_hand()

        # Play the hand
        while not env.is_hand_complete():
            actor_idx = env.get_current_actor_index()
            if actor_idx is None:
                break
            legal = env.get_structured_state(actor_idx).legal_actions
            if ActionType.FOLD in legal:
                env.execute_action(actor_idx, Action(type=ActionType.FOLD))
            elif ActionType.CHECK in legal:
                env.execute_action(actor_idx, Action(type=ActionType.CHECK))
            else:
                env.execute_action(actor_idx, Action(type=ActionType.CALL))

        env.complete_hand()

        # Total chips should be conserved
        final_total = sum(env._current_stacks)
        assert final_total == initial_total

        # Charlie's stack should still be 0
        assert env.get_stack(2) == 0.0


class TestMultiHandTournament:
    """Test multi-hand tournaments with eliminations between hands."""

    def test_continue_after_elimination(self):
        """Tournament should continue after a player is eliminated."""
        env = PokerEnvironment(
            player_names=["alice", "bob", "charlie"],
            starting_stack=100,
            small_blind=10,
            big_blind=20,
        )

        # Hand 1: charlie goes all-in and loses
        env.start_hand()

        # Simulate charlie losing all chips
        env._current_stacks = [150.0, 150.0, 0.0]

        # Hand 2 should work with only 2 players
        env._hand_number = 1  # Reset for clean start
        env.start_hand()

        assert env.get_active_player_count() == 2
        assert len(env._active_original_seats) == 2
        assert env._active_original_seats == [0, 1]

        # Should be able to play the hand
        actor_idx = env.get_current_actor_index()
        assert actor_idx in [0, 1]

    def test_progressive_eliminations(self):
        """Multiple players eliminated over several hands."""
        env = PokerEnvironment(
            player_names=["alice", "bob", "charlie", "diana", "eve"],
            starting_stack=100,
            small_blind=10,
            big_blind=20,
        )

        # Hand 1: All players active
        env.start_hand()
        assert len(env._active_original_seats) == 5

        # Play through hand 1 (simplified - just fold around)
        while not env.is_hand_complete():
            actor = env.get_current_actor_index()
            if actor is None:
                break
            legal = env.get_structured_state(actor).legal_actions
            if ActionType.CHECK in legal:
                env.execute_action(actor, Action(type=ActionType.CHECK))
            elif ActionType.FOLD in legal:
                env.execute_action(actor, Action(type=ActionType.FOLD))
            else:
                env.execute_action(actor, Action(type=ActionType.CALL))
        env.complete_hand()

        # Simulate eve (seat 4) elimination
        env._current_stacks[4] = 0.0

        # Hand 2: 4 players
        env.start_hand()
        assert len(env._active_original_seats) == 4
        assert 4 not in env._active_original_seats

        # Play through hand 2
        while not env.is_hand_complete():
            actor = env.get_current_actor_index()
            if actor is None:
                break
            legal = env.get_structured_state(actor).legal_actions
            if ActionType.CHECK in legal:
                env.execute_action(actor, Action(type=ActionType.CHECK))
            elif ActionType.FOLD in legal:
                env.execute_action(actor, Action(type=ActionType.FOLD))
            else:
                env.execute_action(actor, Action(type=ActionType.CALL))
        env.complete_hand()

        # Simulate bob (seat 1) elimination
        env._current_stacks[1] = 0.0

        # Hand 3: 3 players (alice, charlie, diana)
        env.start_hand()
        assert len(env._active_original_seats) == 3
        assert env._active_original_seats == [0, 2, 3]

        # Verify correct mapping
        assert env._original_to_pokerkit_seat(0) == 0  # alice
        assert env._original_to_pokerkit_seat(1) is None  # bob eliminated
        assert env._original_to_pokerkit_seat(2) == 1  # charlie
        assert env._original_to_pokerkit_seat(3) == 2  # diana
        assert env._original_to_pokerkit_seat(4) is None  # eve eliminated

    def test_tournament_ends_with_one_player(self):
        """Tournament should not start hand with < 2 players."""
        env = PokerEnvironment(
            player_names=["alice", "bob", "charlie"],
            starting_stack=100,
            small_blind=10,
            big_blind=20,
        )

        # All but one player eliminated
        env._current_stacks = [300.0, 0.0, 0.0]

        with pytest.raises(ValueError, match="Not enough active players"):
            env.start_hand()


class TestEdgeCases:
    """Edge cases and potential failure modes."""

    def test_first_player_eliminated(self):
        """First player (seat 0) eliminated should work correctly."""
        env = PokerEnvironment(
            player_names=["alice", "bob", "charlie"],
            starting_stack=100,
            small_blind=10,
            big_blind=20,
        )

        env._current_stacks = [0.0, 150.0, 150.0]
        env.start_hand()

        assert env._active_original_seats == [1, 2]
        assert env._original_to_pokerkit_seat(0) is None
        assert env._original_to_pokerkit_seat(1) == 0
        assert env._original_to_pokerkit_seat(2) == 1

    def test_last_player_eliminated(self):
        """Last player (highest seat) eliminated should work correctly."""
        env = PokerEnvironment(
            player_names=["alice", "bob", "charlie"],
            starting_stack=100,
            small_blind=10,
            big_blind=20,
        )

        env._current_stacks = [150.0, 150.0, 0.0]
        env.start_hand()

        assert env._active_original_seats == [0, 1]
        assert env._original_to_pokerkit_seat(0) == 0
        assert env._original_to_pokerkit_seat(1) == 1
        assert env._original_to_pokerkit_seat(2) is None

    def test_alternating_eliminations(self):
        """Alternating seats eliminated (0, 2, 4) should work."""
        env = PokerEnvironment(
            player_names=["a", "b", "c", "d", "e"],
            starting_stack=100,
            small_blind=10,
            big_blind=20,
        )

        # Eliminate seats 0, 2, 4
        env._current_stacks = [0.0, 200.0, 0.0, 200.0, 0.0]
        env.start_hand()

        assert env._active_original_seats == [1, 3]
        assert env._pokerkit_to_original_seat(0) == 1
        assert env._pokerkit_to_original_seat(1) == 3

    def test_action_history_uses_original_indices(self):
        """Action history should record original player indices."""
        env = PokerEnvironment(
            player_names=["alice", "bob", "charlie", "diana"],
            starting_stack=100,
            small_blind=10,
            big_blind=20,
        )

        # Eliminate bob (seat 1)
        env._current_stacks = [100.0, 0.0, 100.0, 100.0]
        env.start_hand()

        # Execute some actions
        while not env.is_hand_complete():
            actor = env.get_current_actor_index()
            if actor is None:
                break

            env.execute_action(actor, Action(type=ActionType.FOLD))

            # Check last action in history
            last_action = env._action_history[-1]
            assert last_action["player_index"] == actor
            assert last_action["player_name"] == env.player_names[actor]
            assert last_action["player_index"] != 1  # Not bob

            if len(env._action_history) >= 2:
                break  # Just test a couple actions

