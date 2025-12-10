"""
Game models - Structured representations of poker game state.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Street(str, Enum):
    """Current betting round."""

    PREFLOP = "preflop"
    FLOP = "flop"
    TURN = "turn"
    RIVER = "river"


class ActionType(str, Enum):
    """Legal poker actions."""

    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    BET = "bet"
    RAISE = "raise"
    ALL_IN = "all_in"


@dataclass
class Card:
    """Poker card representation."""

    rank: str  # '2'-'9', 'T', 'J', 'Q', 'K', 'A'
    suit: str  # 'h', 'd', 'c', 's'

    def __str__(self) -> str:
        return f"{self.rank}{self.suit}"

    @classmethod
    def from_string(cls, s: str) -> "Card":
        """Create a Card from a string like 'Ah' or 'Tc'."""
        if len(s) != 2:
            raise ValueError(f"Invalid card string: {s}")
        return cls(rank=s[0], suit=s[1])


@dataclass
class Action:
    """A poker action with optional sizing."""

    type: ActionType
    amount: float | None = None

    def __str__(self) -> str:
        if self.amount is not None:
            return f"{self.type.value} {self.amount}"
        return self.type.value


@dataclass
class PlayerState:
    """State of a single player in the hand."""

    seat: int
    name: str
    stack: float
    is_active: bool  # Still in the hand
    is_all_in: bool
    current_bet: float
    hole_cards: list[Card] | None  # None if hidden


@dataclass
class StructuredGameState:
    """
    Complete structured representation of game state.
    This is the interface between PokerKit and our agents.
    """

    # Hand identification
    hand_number: int

    # Table state
    button_seat: int
    small_blind: float
    big_blind: float

    # Current situation
    street: Street
    pot: float
    community_cards: list[Card]

    # Players
    players: list[PlayerState]
    hero_seat: int  # The agent making the decision

    # Action state
    current_bet: float  # Bet to call
    min_raise: float
    max_raise: float
    legal_actions: list[ActionType]

    # Hand context (for analysis)
    action_history: list[dict[str, Any]] = field(default_factory=list)

    @property
    def hero(self) -> PlayerState:
        """Get the hero's state."""
        return self.players[self.hero_seat]

    @property
    def opponents(self) -> list[PlayerState]:
        """Get active opponents."""
        return [p for p in self.players if p.seat != self.hero_seat and p.is_active]

    @property
    def pot_odds(self) -> float:
        """Calculate pot odds as a ratio."""
        to_call = self.current_bet - self.hero.current_bet
        if to_call <= 0:
            return float("inf")
        return self.pot / to_call

    def get_hole_cards_str(self) -> str:
        """Get hero's hole cards as string."""
        if not self.hero.hole_cards:
            return "??"
        return "".join(str(c) for c in self.hero.hole_cards)

    def get_board_str(self) -> str:
        """Get community cards as string."""
        if not self.community_cards:
            return ""
        return " ".join(str(c) for c in self.community_cards)


@dataclass
class HandResult:
    """Result of a completed hand."""

    hand_number: int
    winners: list[int]  # Winning seat(s)
    pot_size: float
    showdown: bool  # True if went to showdown
    shown_hands: dict[int, list[Card]]  # Seat -> cards shown
    actions_by_street: dict[Street, list[dict[str, Any]]]


@dataclass
class EVRecord:
    """
    EV (Expected Value) calculation for a showdown hand.

    Used to measure decision quality independent of card runout luck.
    EV chips show what "should have happened" given the equity at all-in.

    Example:
        - You have AA vs 72o, all-in preflop (85% equity)
        - You lose the hand (bad beat)
        - Actual chips: -100 (lost)
        - EV chips: +70 (you were 85% to win 200 pot, invested 100)
    """

    hand_number: int
    player_id: str

    # Equity at showdown/all-in point
    equity: float  # 0.0 to 1.0

    # Pot and investment
    pot_size: float  # Total pot at showdown
    amount_invested: float  # What this player put in

    # Calculated values
    ev_chips: float  # (equity × pot) - invested
    actual_chips: float  # What actually happened (+pot if won, -invested if lost)

    @property
    def variance(self) -> float:
        """
        Difference between actual and expected result (the luck component).
        Positive = ran above EV (lucky), Negative = ran below EV (unlucky)
        """
        return self.actual_chips - self.ev_chips

    @property
    def ev_adjusted(self) -> float:
        """
        EV-adjusted result for this showdown (luck removed).
        For a single showdown, this equals ev_chips.
        At tournament level: ev_adjusted_total = actual_total - sum(variance)
        """
        return self.ev_chips

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "hand_number": self.hand_number,
            "player_id": self.player_id,
            "equity": round(self.equity, 4),
            "pot_size": self.pot_size,
            "amount_invested": self.amount_invested,
            "ev_chips": round(self.ev_chips, 2),
            "actual_chips": round(self.actual_chips, 2),
            "variance": round(self.variance, 2),
            "ev_adjusted": round(self.ev_adjusted, 2),
        }
