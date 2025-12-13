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
        """
        self._hand_number += 1
        self._action_history = []

        # Use provided stacks or current stacks
        hand_stacks = stacks if stacks is not None else self._current_stacks

        # Filter out eliminated players (stack <= 0)
        active_players = sum(1 for s in hand_stacks if s > 0)
        if active_players < 2:
            raise ValueError("Not enough active players to start a hand")

        # Create new state with current stacks
        self._state = self._game(
            raw_starting_stacks=tuple(hand_stacks),
            player_count=self.num_players,
        )

        logger.debug(f"Started hand #{self._hand_number} with stacks {hand_stacks}")

        # Return initial state for the first actor
        return self.get_structured_state(self.get_current_actor_index())

    def get_current_actor_index(self) -> int | None:
        """Get the index of the player who needs to act, or None if no action needed."""
        if self._state is None:
            return None
        if not self._state.status:
            return None
        return self._state.actor_index

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
            hero_seat: The seat index of the player requesting the state
                      (determines which hole cards are visible)

        Returns:
            StructuredGameState with all relevant information for decision making.
        """
        if self._state is None:
            raise ValueError("No active hand. Call start_hand() first.")

        state = self._state

        # Determine current street
        street = self._get_current_street()

        # Build player states
        players = []
        for i in range(self.num_players):
            # Get hole cards (only visible for hero)
            hole_cards = None
            if i == hero_seat and state.hole_cards[i]:
                hole_cards = [Card(rank=str(c.rank), suit=str(c.suit)) for c in state.hole_cards[i]]

            players.append(
                PlayerState(
                    seat=i,
                    name=self.player_names[i],
                    stack=float(state.stacks[i]),
                    is_active=state.statuses[i],
                    is_all_in=state.statuses[i] and state.stacks[i] == 0,
                    current_bet=float(state.bets[i]),
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
            player_index: Index of the player taking the action
            action: The action to execute

        Returns:
            Dict with action result information.

        Raises:
            ValueError: If action is invalid or illegal.
        """
        if self._state is None:
            raise ValueError("No active hand")

        if self._state.actor_index != player_index:
            raise ValueError(
                f"It's not player {player_index}'s turn. Current actor: {self._state.actor_index}"
            )

        state = self._state
        result = {"player": player_index, "action": action.type.value}

        # Capture pot and stacks BEFORE executing the action
        pot_before_action = float(state.total_pot_amount)
        stacks_before = {
            self.player_names[i]: float(state.stacks[i]) for i in range(self.num_players)
        }

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
        """
        if self._state is None:
            raise ValueError("No active hand")

        state = self._state

        # Wait for hand to complete
        if state.status:
            raise ValueError("Hand is not complete yet")

        # Update current stacks for next hand
        self._current_stacks = [float(s) for s in state.stacks]

        # Determine winners (players with positive payoffs)
        winners = [i for i, p in enumerate(state.payoffs) if p > 0]

        # Get shown hands from HoleCardsShowingOrMucking operations
        # Note: We can't use state.hole_cards directly because PokerKit's
        # HandKilling automation clears them after showdown
        shown_hands = {}
        for op in state.operations:
            if type(op).__name__ == "HoleCardsShowingOrMucking":
                if op.hole_cards:  # Cards were shown (not mucked)
                    shown_hands[op.player_index] = [
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
