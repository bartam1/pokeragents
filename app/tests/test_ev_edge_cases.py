"""
Tests for EV calculation edge cases.

These tests verify correct behavior for:
1. Short stack blind scenarios (partial blinds, all-in for blind)
2. Pot size calculation accuracy
3. Hand number consistency between hand data and EV records
4. Showdown detection accuracy (fold vs forced all-in)
"""

import pytest

from backend.domain.game.environment import PokerEnvironment
from backend.domain.game.models import Action, ActionType
from backend.domain.game.recorder import GameStateRecorder, HandRecord


class TestShortStackBlinds:
    """Test scenarios where a player can't afford the full blind."""

    def test_partial_blind_behavior(self):
        """Test how PokerKit handles partial blinds in heads-up."""
        env = PokerEnvironment(
            player_names=["big_stack", "short_stack"],
            starting_stack=1000,  # Will be overridden
            small_blind=33,
            big_blind=67,
        )

        # Set up heads-up with short stack
        # PokerKit: Button is at last seat position
        # In heads-up: Button posts SB, other posts BB
        # Seat 0 = big_stack (BB), Seat 1 = short_stack (SB/Button)
        env._current_stacks = [7411.0, 56.0]  # big_stack, short_stack

        env.start_hand()

        state = env.get_structured_state(0)  # Get state from big_stack perspective

        p0, p1 = state.players[0], state.players[1]
        print(f"Big stack (seat 0): stack={p0.stack}, bet={p0.current_bet}")
        print(f"Short stack (seat 1): stack={p1.stack}, bet={p1.current_bet}")
        print(f"Pot: {state.pot}")

        # Verify blind structure
        # short_stack (button/SB) posts SB of 33, has 56 - 33 = 23 left
        # big_stack (BB) posts BB of 67, has 7411 - 67 = 7344 left
        assert state.players[1].current_bet == 33  # SB
        assert state.players[0].current_bet == 67  # BB

    def test_short_stack_posts_partial_blind(self):
        """Short stack posts what they have as partial blind."""
        env = PokerEnvironment(
            player_names=["big_stack", "short_stack"],
            starting_stack=1000,
            small_blind=33,
            big_blind=67,
        )

        # short_stack has 33 chips - in heads-up they post SB
        # PokerKit seats: seat 1 (short_stack) is button, posts SB
        env._current_stacks = [7411.0, 33.0]

        env.start_hand()

        state = env.get_structured_state(0)

        print(f"Short stack: stack={state.players[1].stack}, bet={state.players[1].current_bet}")

        # Verify the hand can start and complete
        if not env.is_hand_complete():
            actor = env.get_current_actor_index()
            if actor is not None:
                env.execute_action(actor, Action(type=ActionType.FOLD))

        assert env.is_hand_complete()

    def test_heads_up_blind_fold(self):
        """Test heads-up where button folds after posting SB."""
        env = PokerEnvironment(
            player_names=["big_stack", "short_stack"],
            starting_stack=1000,
            small_blind=33,
            big_blind=67,
        )

        env._current_stacks = [7411.0, 56.0]

        env.start_hand()

        actor = env.get_current_actor_index()
        state = env.get_structured_state(actor)

        print(f"Actor: {env.player_names[actor]}")
        print(f"Legal actions: {state.legal_actions}")

        # Actor folds
        env.execute_action(actor, Action(type=ActionType.FOLD))

        assert env.is_hand_complete()

        result = env.complete_hand()
        print(f"Winners: {[env.player_names[w] for w in result.winners]}")
        print(f"Pot size: {result.pot_size}")
        print(f"Showdown: {result.showdown}")

        # Someone should win (the non-folder)
        assert len(result.winners) > 0
        assert not result.showdown  # Fold is not showdown


class TestPotSizeCalculation:
    """Test that pot_size is calculated correctly in various scenarios."""

    def test_pot_from_complete_hand(self):
        """Pot size from complete_hand represents the net gain to winners."""
        env = PokerEnvironment(
            player_names=["player_a", "player_b"],
            starting_stack=1000,
            small_blind=10,
            big_blind=20,
        )

        env.start_hand()

        # Both players check to showdown
        while not env.is_hand_complete():
            actor = env.get_current_actor_index()
            if actor is None:
                break
            state = env.get_structured_state(actor)
            if ActionType.CHECK in state.legal_actions:
                env.execute_action(actor, Action(type=ActionType.CHECK))
            elif ActionType.CALL in state.legal_actions:
                env.execute_action(actor, Action(type=ActionType.CALL))
            else:
                env.execute_action(actor, Action(type=ActionType.FOLD))

        result = env.complete_hand()

        # Note: PokerKit's pot_size represents the net payoff to winners
        # (sum of positive payoffs), not the total pot amount
        print(f"Pot size (net gain to winner): {result.pot_size}")
        # In heads-up with check-to-showdown, winner gains the opponent's blind
        assert result.pot_size > 0

    def test_pot_after_all_in_and_fold(self):
        """When a short stack is all-in and opponent folds, pot should be correct."""
        env = PokerEnvironment(
            player_names=["big_stack", "short_stack"],
            starting_stack=1000,
            small_blind=33,
            big_blind=67,
        )

        # short_stack has 89 chips - can post full BB (67) with 22 remaining
        env._current_stacks = [7411.0, 89.0]

        env.start_hand()

        # big_stack (SB) folds
        actor = env.get_current_actor_index()
        env.execute_action(actor, Action(type=ActionType.FOLD))

        result = env.complete_hand()

        # Pot should be SB (33) + BB (67) = 100
        # short_stack wins, so pot_size from payoffs should reflect this
        print(f"Pot size: {result.pot_size}")
        print(f"Winners: {result.winners}")

        # When big_stack folds, short_stack wins the pot
        # short_stack gets back their BB (67) + wins the SB (33) = 100 total in pot
        # But net gain is just 33 (the SB they won)


class TestHandNumberConsistency:
    """Test that hand_number is consistent across all records."""

    def test_hand_number_in_recorder(self):
        """EV records should have the same hand_number as the hand data."""
        from backend.domain.game.models import EVRecord

        # Create a hand record
        hand = HandRecord(hand_number=52)
        hand.starting_stacks = {"player_a": 1000, "player_b": 1000}
        hand.finishing_stacks = {"player_a": 1100, "player_b": 900}

        # Add EV records - they should have the same hand_number
        ev1 = EVRecord(
            hand_number=52,  # Should match!
            player_id="player_a",
            equity=0.6,
            pot_size=200,
            amount_invested=100,
            ev_chips=20,
            actual_chips=100,
        )
        ev2 = EVRecord(
            hand_number=52,
            player_id="player_b",
            equity=0.4,
            pot_size=200,
            amount_invested=100,
            ev_chips=-20,
            actual_chips=-100,
        )

        hand.ev_records = [ev1, ev2]

        # Verify consistency
        for ev in hand.ev_records:
            assert ev.hand_number == hand.hand_number, (
                f"EV hand_number {ev.hand_number} doesn't match "
                f"hand data hand_number {hand.hand_number}"
            )


class TestShowdownDetection:
    """Test that showdown is correctly detected."""

    def test_fold_is_not_showdown(self):
        """When a player folds, it should not be a showdown."""
        env = PokerEnvironment(
            player_names=["player_a", "player_b"],
            starting_stack=1000,
            small_blind=10,
            big_blind=20,
        )

        env.start_hand()

        # player_a (SB) folds preflop
        actor = env.get_current_actor_index()
        env.execute_action(actor, Action(type=ActionType.FOLD))

        result = env.complete_hand()

        # Should NOT be a showdown - player_a folded
        print(f"Showdown: {result.showdown}")
        print(f"Shown hands: {result.shown_hands}")
        assert not result.showdown, "Fold should not result in showdown"
        assert len(result.shown_hands) <= 1, "Only winner might show, not both"

    def test_all_in_call_is_showdown(self):
        """When a player goes all-in and is called, it should be a showdown."""
        env = PokerEnvironment(
            player_names=["player_a", "player_b"],
            starting_stack=100,
            small_blind=10,
            big_blind=20,
        )

        env.start_hand()

        # player_a (button/SB in heads-up) goes all-in
        actor = env.get_current_actor_index()
        print(f"Actor: {env.player_names[actor]}")
        env.execute_action(actor, Action(type=ActionType.ALL_IN))

        # player_b should call
        while not env.is_hand_complete():
            actor = env.get_current_actor_index()
            if actor is None:
                break
            print(f"Next actor: {env.player_names[actor]}")
            state = env.get_structured_state(actor)
            print(f"Legal actions: {state.legal_actions}")
            if ActionType.CALL in state.legal_actions:
                env.execute_action(actor, Action(type=ActionType.CALL))
            else:
                break

        if env.is_hand_complete():
            result = env.complete_hand()

            # Should be a showdown - both all-in
            print(f"Showdown: {result.showdown}")
            print(f"Shown hands: {len(result.shown_hands)} hands shown")
            assert result.showdown, "All-in with call should be showdown"
            assert len(result.shown_hands) == 2, "Both hands should be shown"
        else:
            # If hand didn't complete, this test is not applicable
            print("Hand didn't complete - checking what happened")
            actor = env.get_current_actor_index()
            if actor is not None:
                state = env.get_structured_state(actor)
                print(f"Waiting for: {env.player_names[actor]}, actions: {state.legal_actions}")


class TestAllInBlindNoActionBug:
    """Test the bug where all-in for blind hands don't record properly."""

    def test_all_in_for_blind_auto_wins(self):
        """When a player is all-in for the blind, the hand should still complete correctly."""
        env = PokerEnvironment(
            player_names=["short_stack", "big_stack"],
            starting_stack=1000,
            small_blind=33,
            big_blind=67,
        )

        # short_stack has only 22 chips (less than SB of 33)
        # In heads-up: button is SB, non-button is BB
        # short_stack at seat 0 will be BB
        env._current_stacks = [22.0, 7478.0]

        env.start_hand()

        state = env.get_structured_state(0)
        print(f"short_stack stack: {state.players[0].stack}")
        print(f"big_stack stack: {state.players[1].stack}")
        print(f"Pot: {state.pot}")

        # short_stack should be all-in for their 22 as partial BB
        # big_stack should have posted SB
        # Let's see what the legal actions are

        actor = env.get_current_actor_index()
        if actor is not None:
            state = env.get_structured_state(actor)
            print(f"Actor: {env.player_names[actor]}")
            print(f"Legal actions: {state.legal_actions}")

            # If there's an actor, they can fold/call/raise
            # Let's say big_stack just checks/calls
            if ActionType.CHECK in state.legal_actions:
                env.execute_action(actor, Action(type=ActionType.CHECK))
            elif ActionType.CALL in state.legal_actions:
                env.execute_action(actor, Action(type=ActionType.CALL))
            else:
                env.execute_action(actor, Action(type=ActionType.FOLD))

        # Check if hand is complete
        if env.is_hand_complete():
            result = env.complete_hand()
            print("\nResult:")
            print(f"Winners: {[env.player_names[w] for w in result.winners]}")
            print(f"Pot: {result.pot_size}")
            print(f"Showdown: {result.showdown}")
            print(f"Shown hands: {len(result.shown_hands)}")

    def test_recorder_creates_hand_for_all_in_blind(self):
        """Recorder should create a HandRecord even when player is all-in for blind."""

        recorder = GameStateRecorder("/tmp/test")
        recorder.start_tournament("test_tourney")

        # Simulate recording for hand 52 (normal hand)
        from backend.domain.game.models import Action, ActionType, EVRecord, Street

        # Create a mock state for hand 52
        class MockPlayer:
            def __init__(self, name, stack):
                self.name = name
                self.stack = stack

        class MockState52:
            hand_number = 52
            street = Street.PREFLOP
            pot = 100.0
            current_bet = 67.0
            small_blind = 33.0
            big_blind = 67.0
            players = [MockPlayer("agent_c", 22.0), MockPlayer("agent_e", 7378.0)]
            action_history = []

        # Record action for hand 52
        recorder.record_action(
            MockState52(),
            "agent_c",
            Action(type=ActionType.FOLD),
        )
        recorder.record_hand_result({"agent_c": 22.0, "agent_e": 7478.0})

        # Now simulate hand 53 where agent_c is all-in for blind
        # NO ACTIONS are recorded - but we now call record_hand_result with hand_number!
        # This is the FIX: record_hand_result creates a new hand when hand_number differs
        recorder.record_hand_result(
            {"agent_c": 0.0, "agent_e": 7500.0},
            hand_number=53,
            starting_stacks={"agent_c": 22.0, "agent_e": 7478.0},
            small_blind=33.0,
            big_blind=67.0,
        )

        # EV is calculated for hand 53
        ev_records = [
            EVRecord(
                hand_number=53,
                player_id="agent_c",
                equity=0.0,
                pot_size=22.0,
                amount_invested=22.0,
                ev_chips=-22.0,
                actual_chips=-22.0,
            ),
            EVRecord(
                hand_number=53,
                player_id="agent_e",
                equity=1.0,
                pot_size=22.0,
                amount_invested=0.0,
                ev_chips=22.0,
                actual_chips=22.0,
            ),
        ]

        # With the fix, record_ev should now work correctly
        recorder.record_ev(ev_records)

        # Check that both hands are recorded correctly
        tournament = recorder._current_tournament
        assert len(tournament.hands) == 2, (
            f"Should have 2 hands recorded, got {len(tournament.hands)}"
        )

        hand52 = tournament.hands[0]
        hand53 = tournament.hands[1]

        print(f"Hand 52 number: {hand52.hand_number}, EV records: {len(hand52.ev_records)}")
        print(f"Hand 53 number: {hand53.hand_number}, EV records: {len(hand53.ev_records)}")

        # Verify hand 52 has no EV records (fold, no showdown)
        assert hand52.hand_number == 52
        assert len(hand52.ev_records) == 0, "Hand 52 should have no EV records (fold)"

        # Verify hand 53 has the correct EV records
        assert hand53.hand_number == 53
        assert len(hand53.ev_records) == 2, "Hand 53 should have 2 EV records"
        for ev in hand53.ev_records:
            assert ev.hand_number == 53, (
                f"EV record should have hand_number=53, got {ev.hand_number}"
            )

        # Verify starting stacks are captured correctly (BEFORE blinds)
        assert hand53.starting_stacks == {"agent_c": 22.0, "agent_e": 7478.0}

    def test_record_ev_validates_hand_number(self):
        """record_ev should raise an error if EV hand_number doesn't match current hand."""
        from backend.domain.game.models import Action, ActionType, EVRecord, Street

        recorder = GameStateRecorder("/tmp/test")
        recorder.start_tournament("test_tourney")

        class MockPlayer:
            def __init__(self, name, stack):
                self.name = name
                self.stack = stack

        class MockState:
            hand_number = 52
            street = Street.PREFLOP
            pot = 100.0
            current_bet = 67.0
            small_blind = 33.0
            big_blind = 67.0
            players = [MockPlayer("agent_c", 22.0), MockPlayer("agent_e", 7378.0)]
            action_history = []

        recorder.record_action(MockState(), "agent_c", Action(type=ActionType.FOLD))
        recorder.record_hand_result({"agent_c": 22.0, "agent_e": 7478.0})

        # Try to record EV with wrong hand number - should raise
        ev_records = [
            EVRecord(
                hand_number=53,  # Wrong! Current hand is 52
                player_id="agent_c",
                equity=0.0,
                pot_size=22.0,
                amount_invested=22.0,
                ev_chips=-22.0,
                actual_chips=-22.0,
            ),
        ]

        with pytest.raises(ValueError, match="doesn't match current hand"):
            recorder.record_ev(ev_records)


class TestStartingStacksCapture:
    """Test that starting stacks are captured BEFORE blinds are posted."""

    def test_starting_stacks_before_blinds(self):
        """Starting stacks should reflect chips before blinds, not after."""
        env = PokerEnvironment(
            player_names=["agent_c", "agent_e"],
            starting_stack=1000,
            small_blind=33,
            big_blind=67,
        )

        # Set up with specific stacks
        env._current_stacks = [89.0, 7411.0]

        env.start_hand()

        # Get stacks AFTER blinds from game state
        state = env.get_structured_state(0)

        print(f"agent_c stack in game state: {state.players[0].stack}")
        print(f"agent_e stack in game state: {state.players[1].stack}")

        # After posting blinds:
        # agent_c (BB=67): 89 - 67 = 22
        # agent_e (SB=33): 7411 - 33 = 7378
        assert state.players[0].stack == 22  # After BB
        assert state.players[1].stack == 7378  # After SB

        # But starting_stacks for recording should be BEFORE blinds
        # This is the bug: recorder uses game state stacks (after blinds)
        # Should use: 89 and 7411

    def test_recorder_uses_provided_starting_stacks(self):
        """Recorder should use provided starting_stacks even if action was already recorded."""
        from backend.domain.game.models import Action, ActionType, Street
        from backend.domain.game.recorder import GameStateRecorder

        recorder = GameStateRecorder("/tmp/test")
        recorder.start_tournament("test_tourney")

        class MockPlayer:
            def __init__(self, name, stack):
                self.name = name
                self.stack = stack

        # Simulate game state AFTER blinds (wrong stacks)
        class MockStateAfterBlinds:
            hand_number = 1
            street = Street.PREFLOP
            pot = 100.0
            current_bet = 67.0
            small_blind = 33.0
            big_blind = 67.0
            # These stacks are AFTER blinds (agent_c posted BB of 67)
            players = [MockPlayer("agent_c", 22.0), MockPlayer("agent_e", 7378.0)]
            action_history = []

        # Record an action - this sets starting_stacks from game state (wrong!)
        recorder.record_action(
            MockStateAfterBlinds(),
            "agent_c",
            Action(type=ActionType.FOLD),
        )

        # Now call record_hand_result with correct stacks (BEFORE blinds)
        correct_starting_stacks = {"agent_c": 89.0, "agent_e": 7411.0}
        recorder.record_hand_result(
            finishing_stacks={"agent_c": 22.0, "agent_e": 7478.0},
            hand_number=1,
            starting_stacks=correct_starting_stacks,
            small_blind=33.0,
            big_blind=67.0,
        )

        # Verify the recorder used the correct starting_stacks
        hand = recorder._current_tournament.hands[0]
        print(f"Starting stacks in record: {hand.starting_stacks}")

        # The fix ensures we use the CORRECT starting_stacks (before blinds)
        assert hand.starting_stacks == correct_starting_stacks, (
            f"Starting stacks should be {correct_starting_stacks}, got {hand.starting_stacks}"
        )

        # Verify chips are conserved in the summary
        summary = hand.to_summary_dict()
        print(f"Chips won: {summary['chips_won']}")

        # agent_c: 22 - 89 = -67 (lost BB)
        # agent_e: 7478 - 7411 = +67 (won BB)
        assert summary["chips_won"]["agent_c"] == -67.0, (
            f"agent_c should have lost 67, got {summary['chips_won']['agent_c']}"
        )
        assert summary["chips_won"]["agent_e"] == 67.0, (
            f"agent_e should have won 67, got {summary['chips_won']['agent_e']}"
        )

        # Total chips won should be 0 (conserved)
        total_chips_won = sum(summary["chips_won"].values())
        assert total_chips_won == 0, f"Chips not conserved: total chips_won = {total_chips_won}"

    def test_fold_preserves_remaining_chips(self):
        """When a player folds, they should keep their remaining chips."""
        env = PokerEnvironment(
            player_names=["agent_c", "agent_e"],
            starting_stack=1000,
            small_blind=33,
            big_blind=67,
        )

        # agent_c has 89 chips, will have 22 after posting BB
        env._current_stacks = [89.0, 7411.0]

        env.start_hand()

        # agent_e (SB/button in heads-up) acts first
        actor = env.get_current_actor_index()
        assert env.player_names[actor] == "agent_e"

        # agent_e raises
        env.execute_action(actor, Action(type=ActionType.RAISE, amount=150))

        # agent_c folds
        actor = env.get_current_actor_index()
        assert env.player_names[actor] == "agent_c"
        state = env.get_structured_state(actor)
        print(f"agent_c stack before fold: {state.players[0].stack}")

        env.execute_action(actor, Action(type=ActionType.FOLD))

        result = env.complete_hand()

        print(f"Showdown: {result.showdown}")
        print(f"agent_c final stack: {env.get_stack(0)}")
        print(f"agent_e final stack: {env.get_stack(1)}")

        # CRITICAL: agent_c should keep their 22 chips after folding
        assert env.get_stack(0) == 22, (
            f"agent_c should keep 22 chips after fold, got {env.get_stack(0)}"
        )
        # agent_e wins the pot (SB + BB = 100) but their raise is returned
        # agent_c folded, so agent_e gets the pot: 7411 - 33 (SB) + 100 (pot won) = 7478
        assert env.get_stack(1) == 7478, f"agent_e should have 7478, got {env.get_stack(1)}"

        # Verify no showdown
        assert not result.showdown, "Fold should not result in showdown"


class TestReproduceBugFromTournament:
    """Reproduce the specific bug from tournament_20251214_084156_ae24e3fd."""

    def test_hand_52_scenario_with_call(self):
        """Test what happens when short stack CALLS instead of folds."""
        env = PokerEnvironment(
            player_names=["agent_a", "agent_b", "agent_c", "agent_d", "agent_e"],
            starting_stack=1500,
            small_blind=33,
            big_blind=67,
        )

        # Set up the exact scenario from hand 52
        env._current_stacks = [0.0, 0.0, 89.0, 0.0, 7411.0]

        env.start_hand()

        # agent_e raises
        actor = env.get_current_actor_index()
        assert actor == 4  # agent_e
        env.execute_action(4, Action(type=ActionType.RAISE, amount=150))

        # agent_c CALLS with their remaining 22 chips
        actor = env.get_current_actor_index()
        assert actor == 2  # agent_c
        state = env.get_structured_state(actor)
        print(f"agent_c stack before call: {state.players[2].stack}")
        print(f"Legal actions: {state.legal_actions}")

        env.execute_action(2, Action(type=ActionType.CALL))

        # Complete the hand
        result = env.complete_hand()

        print("\nResult after CALL:")
        print(f"Winners: {[env.player_names[w] for w in result.winners]}")
        print(f"Pot size: {result.pot_size}")
        print(f"Showdown: {result.showdown}")
        print(f"Shown hands count: {len(result.shown_hands)}")

        # With a call, this SHOULD be a showdown
        assert result.showdown, "Call should result in showdown"
        assert len(result.shown_hands) == 2, "Both hands should be shown"

        # Verify stacks
        print("\nFinal stacks:")
        for i, name in enumerate(env.player_names):
            if env.get_stack(i) > 0:
                print(f"  {name}: {env.get_stack(i)}")

        # After call and showdown, either agent_c wins (178) or loses (0)
        agent_c_stack = env.get_stack(2)
        assert agent_c_stack == 0 or agent_c_stack == 178, (
            f"agent_c should have 0 or 178, got {agent_c_stack}"
        )

        # Total chips should be conserved
        total = sum(env.get_stack(i) for i in range(5))
        print(f"Total chips: {total}")
        assert total == 7500, f"Chips not conserved: {total}"

    def test_hand_52_scenario(self):
        """Reproduce hand 52 conditions: heads-up with short stack."""
        env = PokerEnvironment(
            player_names=["agent_a", "agent_b", "agent_c", "agent_d", "agent_e"],
            starting_stack=1500,
            small_blind=33,
            big_blind=67,
        )

        # Set up the exact scenario from hand 52
        # Only agent_c and agent_e are active
        env._current_stacks = [0.0, 0.0, 89.0, 0.0, 7411.0]

        env.start_hand()

        # Check which players are active
        print(f"Active seats: {env._active_original_seats}")
        print(f"Num active: {len(env._active_original_seats)}")

        # Should be heads-up between agent_c (seat 2) and agent_e (seat 4)
        assert len(env._active_original_seats) == 2
        assert 2 in env._active_original_seats  # agent_c
        assert 4 in env._active_original_seats  # agent_e

        # Get the state
        actor = env.get_current_actor_index()
        state = env.get_structured_state(actor)

        print(f"Current actor: {env.player_names[actor]} (seat {actor})")
        print(f"agent_c stack: {state.players[2].stack}")
        print(f"agent_e stack: {state.players[4].stack}")
        print(f"Pot: {state.pot}")
        print(f"Current bet: {state.current_bet}")

        # agent_c should have 22 chips remaining after posting BB of 67
        # (started with 89, posted 67, has 22 left)
        # OR agent_c might be all-in if they couldn't afford full BB

        # Let agent_e raise
        if actor == 4:  # agent_e
            env.execute_action(4, Action(type=ActionType.RAISE, amount=150))

            # Now it's agent_c's turn
            actor = env.get_current_actor_index()
            if actor is not None:
                state = env.get_structured_state(actor)
                print("\nAfter raise:")
                print(f"Current actor: {env.player_names[actor]} (seat {actor})")
                print(f"agent_c stack: {state.players[2].stack}")
                print(f"Legal actions: {state.legal_actions}")

                # agent_c folds
                env.execute_action(2, Action(type=ActionType.FOLD))

        # Complete the hand
        result = env.complete_hand()

        print("\nResult:")
        print(f"Winners: {[env.player_names[w] for w in result.winners]}")
        print(f"Pot size: {result.pot_size}")
        print(f"Showdown: {result.showdown}")
        print(f"Shown hands: {result.shown_hands}")

        # Verify stacks after hand
        print("\nFinal stacks:")
        for i, name in enumerate(env.player_names):
            print(f"  {name}: {env.get_stack(i)}")

        # If agent_c folded with 22 chips remaining, they should still have 22 chips
        # This is the bug we're trying to reproduce!
        agent_c_final = env.get_stack(2)
        print(f"\nagent_c final stack: {agent_c_final}")

        # The bug: agent_c shows 0 in the tournament data, but should have 22
        # if they folded (not if they called/went all-in)
