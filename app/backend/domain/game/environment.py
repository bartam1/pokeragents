"""
PokerKit Environment Wrapper - Integrates PokerKit with our agent system.

This module provides a clean interface between PokerKit's state management
and our AI agents, converting between PokerKit's native API and our
StructuredGameState format.

Reference: https://github.com/uoftcprg/pokerkit
"""

from typing import Any

from pokerkit import Automation, NoLimitTexasHoldem

from backend.domain.game.models import (
    Action,
    ActionType,
    Card,
    HandResult,
    PlayerState,
    Street,
    StructuredGameState,
)
from backend.logging_config import get_logger

logger = get_logger(__name__)


# Automations for AI agent development - automate everything except player actions
AI_AUTOMATIONS = (
    Automation.ANTE_POSTING,
    Automation.BET_COLLECTION,
    Automation.BLIND_OR_STRADDLE_POSTING,
    Automation.CARD_BURNING,
    Automation.HOLE_DEALING,
    Automation.BOARD_DEALING,
    Automation.HOLE_CARDS_SHOWING_OR_MUCKING,
    Automation.HAND_KILLING,
    Automation.CHIPS_PUSHING,
    Automation.CHIPS_PULLING,
)


class PokerEnvironment:
    """
    Wrapper around PokerKit for poker game simulation.

    Provides a clean interface for:
    - Creating and managing poker games
    - Converting between PokerKit state and StructuredGameState
    - Executing agent actions
    - Tracking hand history

    Supports dynamic player elimination: when a player's stack reaches 0,
    they are removed from subsequent hands while maintaining consistent
    seat indices for the orchestrator.
    """

    def __init__(
        self,
        player_names: list[str],
        starting_stack: int = 1500,
        small_blind: int = 10,
        big_blind: int = 20,
        ante: int = 0,
    ):
        """
        Initialize the poker environment.

        Args:
            player_names: Names of players in seat order
            starting_stack: Starting chip stack for each player
            small_blind: Small blind amount
            big_blind: Big blind amount
            ante: Ante amount (0 for no ante)
        """
        self.player_names = player_names
        self.num_players = len(player_names)
        self.starting_stack = starting_stack
        self.small_blind = small_blind
        self.big_blind = big_blind
        self.ante = ante

        # Create the game template
        self._game = NoLimitTexasHoldem(
            automations=AI_AUTOMATIONS,
            ante_trimming_status=True,
            raw_antes=ante,
            raw_blinds_or_straddles=(small_blind, big_blind),
            min_bet=big_blind,
        )

        # Current state
        self._state = None
        self._hand_number = 0
        self._action_history: list[dict[str, Any]] = []

        # Track stacks across hands (for tournament mode)
        self._current_stacks = [float(starting_stack)] * self.num_players

        # Dynamic player tracking: maps between original seat indices and current PokerKit indices
        # _active_original_seats: list of original seat indices that are still in play
        # When a player busts, they're removed from this list
        self._active_original_seats: list[int] = list(range(self.num_players))

    def set_blinds(self, small_blind: int, big_blind: int) -> None:
        """
        Update blind levels (for tournament blind increases).

        This recreates the game definition with new blinds.
        """
        self.small_blind = small_blind
        self.big_blind = big_blind

        # Recreate game template with new blinds
        self._game = NoLimitTexasHoldem(
            automations=AI_AUTOMATIONS,
            ante_trimming_status=True,
            raw_antes=self.ante,
            raw_blinds_or_straddles=(small_blind, big_blind),
            min_bet=big_blind,
        )

        logger.info(f"Blinds updated to {small_blind}/{big_blind}")

    def start_hand(self, stacks: list[float] | None = None) -> StructuredGameState:
        """
        Start a new hand.

        Args:
            stacks: Optional custom starting stacks. If None, uses current stacks.

        Returns:
            The initial game state for agents to observe.

        Note:
            Eliminated players (stack <= 0) are automatically excluded from the hand.
            The environment maintains a mapping between original seat indices and
            current PokerKit indices to handle dynamic player elimination.
        """
        self._hand_number += 1
        self._action_history = []

        # Use provided stacks or current stacks
        hand_stacks = stacks if stacks is not None else self._current_stacks

        # Update active seats: remove any players who have been eliminated (stack <= 0)
        self._active_original_seats = [i for i in range(self.num_players) if hand_stacks[i] > 0]

        if len(self._active_original_seats) < 2:
            raise ValueError("Not enough active players to start a hand")

        # Get only the stacks of active players for PokerKit
        active_stacks = tuple(hand_stacks[i] for i in self._active_original_seats)
        active_count = len(self._active_original_seats)

        # Recreate the game with the correct number of players if needed
        if (
            active_count != len(self._game.raw_blinds_or_straddles)
            or active_count < self.num_players
        ):
            # Adjust blinds for fewer players (ensure we don't have more blinds than players)
            blinds = (self.small_blind, self.big_blind) if active_count >= 2 else (self.big_blind,)
            self._game = NoLimitTexasHoldem(
                automations=AI_AUTOMATIONS,
                ante_trimming_status=True,
                raw_antes=self.ante,
                raw_blinds_or_straddles=blinds[:active_count],
                min_bet=self.big_blind,
            )

        # Create new state with only active players
        self._state = self._game(
            raw_starting_stacks=active_stacks,
            player_count=active_count,
        )

        active_names = [self.player_names[i] for i in self._active_original_seats]
        logger.debug(
            f"Started hand #{self._hand_number} with {active_count} players: "
            f"{active_names} stacks {active_stacks}"
        )

        # Return initial state for the first actor
        return self.get_structured_state(self.get_current_actor_index())

    def _pokerkit_to_original_seat(self, pk_index: int) -> int:
        """Convert a PokerKit seat index to the original seat index."""
        return self._active_original_seats[pk_index]

    def _original_to_pokerkit_seat(self, original_index: int) -> int | None:
        """Convert an original seat index to the current PokerKit seat index.

        Returns None if the player has been eliminated.
        """
        try:
            return self._active_original_seats.index(original_index)
        except ValueError:
            return None  # Player has been eliminated

    def get_current_actor_index(self) -> int | None:
        """Get the ORIGINAL index of the player who needs to act, or None if no action needed.

        Returns the original seat index (consistent with player_names), not the PokerKit index.
        """
        if self._state is None:
            return None
        if not self._state.status:
            return None
        # Convert PokerKit index back to original index
        pk_index = self._state.actor_index
        return self._pokerkit_to_original_seat(pk_index)

    def get_current_actor_name(self) -> str | None:
        """Get the name of the player who needs to act."""
        idx = self.get_current_actor_index()
        if idx is None:
            return None
        return self.player_names[idx]

    def is_hand_complete(self) -> bool:
        """Check if the current hand is complete."""
        if self._state is None:
            return True
        return not self._state.status

    def get_structured_state(self, hero_seat: int) -> StructuredGameState:
        """
        Convert current PokerKit state to our StructuredGameState format.

        Args:
            hero_seat: The ORIGINAL seat index of the player requesting the state
                      (determines which hole cards are visible)

        Returns:
            StructuredGameState with all relevant information for decision making.

        Note:
            The returned state includes ALL original players, with eliminated players
            marked as inactive with stack=0. This maintains consistent seat indices
            for the orchestrator.
        """
        if self._state is None:
            raise ValueError("No active hand. Call start_hand() first.")

        state = self._state

        # Determine current street
        street = self._get_current_street()

        # Build player states for ALL original players
        players = []
        for orig_seat in range(self.num_players):
            pk_seat = self._original_to_pokerkit_seat(orig_seat)

            if pk_seat is None:
                # Player has been eliminated - show as inactive with 0 stack
                players.append(
                    PlayerState(
                        seat=orig_seat,
                        name=self.player_names[orig_seat],
                        stack=0.0,
                        is_active=False,
                        is_all_in=False,
                        current_bet=0.0,
                        hole_cards=None,
                    )
                )
            else:
                # Player is still active
                hole_cards = None
                if orig_seat == hero_seat and state.hole_cards[pk_seat]:
                    hole_cards = [
                        Card(rank=str(c.rank), suit=str(c.suit)) for c in state.hole_cards[pk_seat]
                    ]

                players.append(
                    PlayerState(
                        seat=orig_seat,
                        name=self.player_names[orig_seat],
                        stack=float(state.stacks[pk_seat]),
                        is_active=state.statuses[pk_seat],
                        is_all_in=state.statuses[pk_seat] and state.stacks[pk_seat] == 0,
                        current_bet=float(state.bets[pk_seat]),
                        hole_cards=hole_cards,
                    )
                )

        # Get community cards
        community_cards = []
        if state.board_cards:
            for board in state.board_cards:
                for card in board:
                    community_cards.append(Card(rank=str(card.rank), suit=str(card.suit)))

        # Calculate pot
        pot = float(state.total_pot_amount)

        # Get legal actions and sizing
        legal_actions = self._get_legal_actions()
        current_bet = float(max(state.bets)) if state.bets else 0.0
        min_raise = float(state.min_completion_betting_or_raising_to_amount or 0)
        max_raise = float(state.max_completion_betting_or_raising_to_amount or 0)

        # Button is always at position num_players - 1 in PokerKit's positional setup
        button_seat = self.num_players - 1

        return StructuredGameState(
            hand_number=self._hand_number,
            button_seat=button_seat,
            small_blind=float(self.small_blind),
            big_blind=float(self.big_blind),
            street=street,
            pot=pot,
            community_cards=community_cards,
            players=players,
            hero_seat=hero_seat,
            current_bet=current_bet,
            min_raise=min_raise,
            max_raise=max_raise,
            legal_actions=legal_actions,
            action_history=self._action_history.copy(),
        )

    def execute_action(self, player_index: int, action: Action) -> dict[str, Any]:
        """
        Execute a player action in the environment.

        Args:
            player_index: The ORIGINAL seat index of the player taking the action
            action: The action to execute

        Returns:
            Dict with action result information.

        Raises:
            ValueError: If action is invalid or illegal.
        """
        if self._state is None:
            raise ValueError("No active hand")

        # Convert original seat index to PokerKit index
        pk_index = self._original_to_pokerkit_seat(player_index)
        if pk_index is None:
            raise ValueError(f"Player {player_index} has been eliminated")

        if self._state.actor_index != pk_index:
            current_actor_original = self._pokerkit_to_original_seat(self._state.actor_index)
            raise ValueError(
                f"It's not player {player_index}'s turn. Current actor: {current_actor_original}"
            )

        state = self._state
        result = {"player": player_index, "action": action.type.value}

        # Capture pot and stacks BEFORE executing the action (using original indices)
        pot_before_action = float(state.total_pot_amount)
        stacks_before = {}
        for orig_seat in range(self.num_players):
            pk_seat = self._original_to_pokerkit_seat(orig_seat)
            if pk_seat is not None:
                stacks_before[self.player_names[orig_seat]] = float(state.stacks[pk_seat])
            else:
                stacks_before[self.player_names[orig_seat]] = 0.0

        try:
            if action.type == ActionType.FOLD:
                state.fold()
                result["success"] = True

            elif action.type in (ActionType.CHECK, ActionType.CALL):
                call_amount = state.checking_or_calling_amount
                state.check_or_call()
                result["success"] = True
                result["amount"] = float(call_amount)

            elif action.type in (ActionType.BET, ActionType.RAISE, ActionType.ALL_IN):
                if action.amount is None:
                    # Default to min bet/raise
                    amount = state.min_completion_betting_or_raising_to_amount or 0
                else:
                    amount = action.amount

                # Clamp to legal range (handle None values)
                min_amount = state.min_completion_betting_or_raising_to_amount or 0
                max_amount = state.max_completion_betting_or_raising_to_amount or float("inf")

                if amount < min_amount:
                    amount = min_amount
                if amount > max_amount:
                    amount = max_amount

                state.complete_bet_or_raise_to(amount)
                result["success"] = True
                result["amount"] = float(amount)

            else:
                raise ValueError(f"Unknown action type: {action.type}")

        except ValueError as e:
            logger.error(f"Invalid action: {e}")
            result["success"] = False
            result["error"] = str(e)
            raise

        # Record in action history with enhanced context
        self._action_history.append(
            {
                "player_index": player_index,
                "player_name": self.player_names[player_index],
                "action": action.type.value,
                "amount": result.get("amount"),
                "street": self._get_current_street().value,
                "pot_before_action": pot_before_action,
                "stacks_before": stacks_before,
            }
        )

        return result

    def complete_hand(self) -> HandResult:
        """
        Complete the current hand and return results.

        Returns:
            HandResult with winners, pot size, and shown hands.

        Note:
            Winner indices and shown_hands indices are converted back to
            original seat indices for consistency with the orchestrator.
        """
        if self._state is None:
            raise ValueError("No active hand")

        state = self._state

        # Wait for hand to complete
        if state.status:
            raise ValueError("Hand is not complete yet")

        # Update current stacks for next hand (map PokerKit stacks back to original indices)
        for pk_seat, orig_seat in enumerate(self._active_original_seats):
            self._current_stacks[orig_seat] = float(state.stacks[pk_seat])

        # Determine winners (convert PokerKit indices to original indices)
        winners = [
            self._pokerkit_to_original_seat(pk_idx)
            for pk_idx, p in enumerate(state.payoffs)
            if p > 0
        ]

        # Get shown hands from HoleCardsShowingOrMucking operations
        # Note: We can't use state.hole_cards directly because PokerKit's
        # HandKilling automation clears them after showdown
        # Convert PokerKit indices to original indices
        shown_hands = {}
        for op in state.operations:
            if type(op).__name__ == "HoleCardsShowingOrMucking":
                if op.hole_cards:  # Cards were shown (not mucked)
                    orig_seat = self._pokerkit_to_original_seat(op.player_index)
                    shown_hands[orig_seat] = [
                        Card(rank=str(c.rank), suit=str(c.suit)) for c in op.hole_cards
                    ]

        # Build actions by street
        actions_by_street = {street: [] for street in Street}
        for action in self._action_history:
            street = Street(action["street"])
            actions_by_street[street].append(action)

        # Calculate pot from payoffs (total_pot_amount is 0 after distribution)
        pot_size = sum(max(0, p) for p in state.payoffs)

        result = HandResult(
            hand_number=self._hand_number,
            winners=winners,
            pot_size=float(pot_size),
            showdown=len(shown_hands) > 1,
            shown_hands=shown_hands,
            actions_by_street=actions_by_street,
        )

        logger.info(
            f"  Winner(s): {[self.player_names[w] for w in winners]} | Pot: {result.pot_size}"
        )

        return result

    def get_stack(self, player_index: int) -> float:
        """Get current stack for a player."""
        return self._current_stacks[player_index]

    def get_stacks(self) -> list[float]:
        """Get all current stacks."""
        return self._current_stacks.copy()

    def get_active_player_count(self) -> int:
        """Get number of players still in the tournament (stack > 0)."""
        return sum(1 for s in self._current_stacks if s > 0)

    def _get_current_street(self) -> Street:
        """Map PokerKit street index to our Street enum."""
        if self._state is None:
            return Street.PREFLOP

        street_idx = self._state.street_index
        if street_idx is None:
            return Street.PREFLOP

        # PokerKit: 0=preflop, 1=flop, 2=turn, 3=river
        mapping = {
            0: Street.PREFLOP,
            1: Street.FLOP,
            2: Street.TURN,
            3: Street.RIVER,
        }
        return mapping.get(street_idx, Street.PREFLOP)

    def _get_legal_actions(self) -> list[ActionType]:
        """Get list of legal actions for current actor."""
        if self._state is None:
            return []

        state = self._state
        actions = []

        if state.can_fold():
            actions.append(ActionType.FOLD)

        if state.can_check_or_call():
            if state.checking_or_calling_amount == 0:
                actions.append(ActionType.CHECK)
            else:
                actions.append(ActionType.CALL)

        # Check if betting/raising is possible
        min_raise = state.min_completion_betting_or_raising_to_amount
        if min_raise and state.can_complete_bet_or_raise_to(min_raise):
            # Determine if it's a bet or raise
            if max(state.bets) == 0:
                actions.append(ActionType.BET)
            else:
                actions.append(ActionType.RAISE)

            # Check for all-in possibility
            max_raise = state.max_completion_betting_or_raising_to_amount
            if max_raise and max_raise > min_raise:
                actions.append(ActionType.ALL_IN)

        return actions
