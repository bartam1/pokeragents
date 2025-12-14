"""
Game State Recorder - Records game states during tournament play.

This module provides functionality to save game actions from a tournament
to JSON files for later statistics recalculation.

Uses a minimal format that stores only data needed for statistics,
reducing file size by ~85% compared to storing full game state.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.domain.game.models import Action, ActionType, EVRecord, Street, StructuredGameState


@dataclass
class MinimalAction:
    """Minimal action record containing only data needed for statistics."""

    hand_number: int
    street: str
    actor: str
    action_type: str
    amount: float | None
    pot: float
    current_bet: float
    preflop_raise_count: int
    stacks: dict[str, float] = field(default_factory=dict)
    decision_type: str = "gto"  # "gto" or "deviate"
    deviation_reason: str | None = None  # Only set if decision_type is "deviate"

    def to_dict(self, include_hand_number: bool = True) -> dict[str, Any]:
        result = {
            "street": self.street,
            "actor": self.actor,
            "action_type": self.action_type,
            "amount": self.amount,
            "pot": self.pot,
            "current_bet": self.current_bet,
            "preflop_raise_count": self.preflop_raise_count,
            "stacks": self.stacks,
            "decision": self.decision_type,
        }
        if include_hand_number:
            result["hand_number"] = self.hand_number
        if self.deviation_reason:
            result["deviation_reason"] = self.deviation_reason
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any], hand_number: int | None = None) -> "MinimalAction":
        return cls(
            hand_number=hand_number if hand_number is not None else data.get("hand_number", 0),
            street=data["street"],
            actor=data["actor"],
            action_type=data["action_type"],
            amount=data.get("amount"),
            pot=data["pot"],
            current_bet=data["current_bet"],
            preflop_raise_count=data["preflop_raise_count"],
            stacks=data.get("stacks", {}),
            decision_type=data.get("decision", "gto"),
            deviation_reason=data.get("deviation_reason"),
        )

    @classmethod
    def from_full_state(
        cls,
        state: StructuredGameState,
        actor: str,
        action: Action,
    ) -> "MinimalAction":
        """Create a MinimalAction from full game state."""
        preflop_raise_count = sum(
            1
            for a in state.action_history
            if a.get("street") == "preflop" and a.get("action") in ("raise", "bet", "all_in")
        )

        stacks = {p.name: p.stack for p in state.players}

        return cls(
            hand_number=state.hand_number,
            street=state.street.value,
            actor=actor,
            action_type=action.type.value,
            amount=action.amount,
            pot=state.pot,
            current_bet=state.current_bet,
            preflop_raise_count=preflop_raise_count,
            stacks=stacks,
        )

    def to_action(self) -> Action:
        """Convert back to Action object."""
        return Action(
            type=ActionType(self.action_type),
            amount=self.amount,
        )

    def to_stub_game_state(self, big_blind: float) -> "StubGameState":
        """Create a minimal stub game state for statistics tracking."""
        return StubGameState(
            hand_number=self.hand_number,
            street=Street(self.street),
            pot=self.pot,
            current_bet=self.current_bet,
            big_blind=big_blind,
            preflop_raise_count=self.preflop_raise_count,
        )


@dataclass
class StubGameState:
    """Minimal game state stub for statistics recalculation."""

    hand_number: int
    street: Street
    pot: float
    current_bet: float
    big_blind: float
    preflop_raise_count: int

    @property
    def action_history(self) -> list[dict]:
        """Return synthetic action history for 3-bet detection."""
        return [{"street": "preflop", "action": "raise"} for _ in range(self.preflop_raise_count)]


@dataclass
class HandRecord:
    """Record of a single hand's actions."""

    hand_number: int
    small_blind: float = 10.0
    big_blind: float = 20.0
    actions: list[MinimalAction] = field(default_factory=list)
    starting_stacks: dict[str, float] = field(default_factory=dict)
    finishing_stacks: dict[str, float] = field(default_factory=dict)
    ev_records: list[EVRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        result = {
            "hand_number": self.hand_number,
            "small_blind": self.small_blind,
            "big_blind": self.big_blind,
            "starting_stacks": self.starting_stacks,
            "finishing_stacks": self.finishing_stacks,
            "actions": [a.to_dict(include_hand_number=False) for a in self.actions],
        }
        if self.ev_records:
            result["ev_records"] = [ev.to_dict() for ev in self.ev_records]
        return result

    def to_summary_dict(self) -> dict[str, Any]:
        """Generate a summary of the hand for the hand_summaries section."""
        # Calculate chips won/lost per player
        chips_won: dict[str, float] = {}
        for player in self.starting_stacks:
            start = self.starting_stacks.get(player, 0)
            finish = self.finishing_stacks.get(player, start)
            chips_won[player] = round(finish - start, 2)

        # Determine winners (players who gained chips)
        winners = [player for player, change in chips_won.items() if change > 0]

        # Check if hand went to showdown (has EV records)
        went_to_showdown = len(self.ev_records) > 0

        # Calculate EV-adjusted chips per player if showdown
        ev_adjusted_chips: dict[str, float] | None = None
        if went_to_showdown:
            ev_adjusted_chips = {}
            ev_by_player = {ev.player_id: ev.ev_adjusted for ev in self.ev_records}
            for player in self.starting_stacks:
                if player in ev_by_player:
                    ev_adjusted_chips[player] = round(ev_by_player[player], 2)
                else:
                    # Non-showdown players: use actual chips won
                    ev_adjusted_chips[player] = chips_won.get(player, 0)

        return {
            "hand_number": self.hand_number,
            "winners": winners,
            "chips_won": chips_won,
            "went_to_showdown": went_to_showdown,
            "ev_adjusted_chips": ev_adjusted_chips,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HandRecord":
        hand_number = data["hand_number"]
        return cls(
            hand_number=hand_number,
            small_blind=data.get("small_blind", 10.0),
            big_blind=data.get("big_blind", 20.0),
            actions=[
                MinimalAction.from_dict(a, hand_number=hand_number) for a in data.get("actions", [])
            ],
            starting_stacks=data.get("starting_stacks", {}),
            finishing_stacks=data.get("finishing_stacks", {}),
            ev_records=[EVRecord.from_dict(ev) for ev in data.get("ev_records", [])],
        )


@dataclass
class TournamentRecord:
    """Complete record of a tournament's actions for statistics and EV tracking."""

    tournament_id: str
    timestamp: str
    players: list[str] = field(default_factory=list)
    hands: list[HandRecord] = field(default_factory=list)

    @property
    def actions(self) -> list[MinimalAction]:
        """Flatten all actions from all hands (for backward compatibility)."""
        return [action for hand in self.hands for action in hand.actions]

    @property
    def big_blind(self) -> float:
        """Get big blind from first hand (for backward compatibility)."""
        if self.hands:
            return self.hands[0].big_blind
        return 20.0

    @property
    def ev_records(self) -> list[EVRecord]:
        """Flatten all EV records from all hands (for backward compatibility)."""
        return [ev for hand in self.hands for ev in hand.ev_records]

    def to_dict(self) -> dict[str, Any]:
        return {
            "tournament_id": self.tournament_id,
            "timestamp": self.timestamp,
            "format_version": 3,
            "players": self.players,
            "hands": [h.to_dict() for h in self.hands],
            "hand_summaries": [h.to_summary_dict() for h in self.hands],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TournamentRecord":
        """Load from dict, supporting v1, v2, and v3 formats."""
        format_version = data.get("format_version", 1)

        if format_version >= 3:
            return cls._from_v3_dict(data)
        elif format_version >= 2:
            return cls._from_v2_dict(data)
        else:
            return cls._from_v1_dict(data)

    @classmethod
    def _from_v3_dict(cls, data: dict[str, Any]) -> "TournamentRecord":
        """Load from v3 format (hands grouped)."""
        hands = [HandRecord.from_dict(h) for h in data.get("hands", [])]

        # Handle old v3 format with ev_records at tournament level
        tournament_ev_records = data.get("ev_records", [])
        if tournament_ev_records:
            _distribute_ev_records_to_hands(
                hands,
                [EVRecord.from_dict(ev) for ev in tournament_ev_records],
            )

        return cls(
            tournament_id=data["tournament_id"],
            timestamp=data["timestamp"],
            players=data.get("players", []),
            hands=hands,
        )

    @classmethod
    def _from_v2_dict(cls, data: dict[str, Any]) -> "TournamentRecord":
        """Load from v2 format (flat actions) and convert to v3."""
        actions = [MinimalAction.from_dict(a) for a in data.get("actions", [])]
        big_blind = data.get("big_blind", 20.0)
        hands = _group_actions_by_hand(actions, big_blind=big_blind)

        # Distribute ev_records to the correct hands
        ev_records = [EVRecord.from_dict(ev) for ev in data.get("ev_records", [])]
        _distribute_ev_records_to_hands(hands, ev_records)

        return cls(
            tournament_id=data["tournament_id"],
            timestamp=data["timestamp"],
            players=data.get("players", []),
            hands=hands,
        )

    @classmethod
    def _from_v1_dict(cls, data: dict[str, Any]) -> "TournamentRecord":
        """Load from old full-state format (v1) and convert to v3."""
        tournament_id = data["tournament_id"]
        timestamp = data["timestamp"]

        players: set[str] = set()
        big_blind = 20.0
        actions: list[MinimalAction] = []

        for state_data in data.get("states", []):
            state = _parse_v1_state(state_data["state"])
            actor = state_data["actor"]
            action_data = state_data["action"]

            if state.players:
                players.update(p["name"] for p in state.players)
            big_blind = state.big_blind

            preflop_raise_count = sum(
                1
                for a in state.action_history
                if a.get("street") == "preflop" and a.get("action") in ("raise", "bet", "all_in")
            )

            actions.append(
                MinimalAction(
                    hand_number=state.hand_number,
                    street=state.street,
                    actor=actor,
                    action_type=action_data["type"],
                    amount=action_data.get("amount"),
                    pot=state.pot,
                    current_bet=state.current_bet,
                    preflop_raise_count=preflop_raise_count,
                )
            )

        hands = _group_actions_by_hand(actions, big_blind=big_blind)

        return cls(
            tournament_id=tournament_id,
            timestamp=timestamp,
            players=sorted(players),
            hands=hands,
        )


def _group_actions_by_hand(
    actions: list[MinimalAction],
    big_blind: float = 20.0,
    small_blind: float | None = None,
) -> list[HandRecord]:
    """Group a flat list of actions by hand number."""
    if small_blind is None:
        small_blind = big_blind / 2

    hands_dict: dict[int, list[MinimalAction]] = {}
    for action in actions:
        if action.hand_number not in hands_dict:
            hands_dict[action.hand_number] = []
        hands_dict[action.hand_number].append(action)

    return [
        HandRecord(
            hand_number=hand_num,
            small_blind=small_blind,
            big_blind=big_blind,
            actions=hand_actions,
        )
        for hand_num, hand_actions in sorted(hands_dict.items())
    ]


def _distribute_ev_records_to_hands(
    hands: list[HandRecord],
    ev_records: list[EVRecord],
) -> None:
    """Distribute EV records to the correct hands based on hand_number."""
    hands_by_number = {h.hand_number: h for h in hands}
    for ev in ev_records:
        if ev.hand_number in hands_by_number:
            hands_by_number[ev.hand_number].ev_records.append(ev)


@dataclass
class _V1State:
    """Helper for parsing v1 format state data."""

    hand_number: int
    street: str
    pot: float
    current_bet: float
    big_blind: float
    players: list[dict]
    action_history: list[dict]


def _parse_v1_state(data: dict) -> _V1State:
    """Parse v1 format state dict."""
    return _V1State(
        hand_number=data["hand_number"],
        street=data["street"],
        pot=data["pot"],
        current_bet=data["current_bet"],
        big_blind=data["big_blind"],
        players=data.get("players", []),
        action_history=data.get("action_history", []),
    )


class GameStateRecorder:
    """Records game actions during tournament play for later analysis."""

    def __init__(self, gamestates_dir: str = "data/gamestates"):
        self._gamestates_dir = Path(gamestates_dir)
        self._current_tournament: TournamentRecord | None = None
        self._players_recorded: bool = False
        self._current_hand: HandRecord | None = None

    def start_tournament(self, tournament_id: str) -> None:
        """Start recording a new tournament."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._current_tournament = TournamentRecord(
            tournament_id=tournament_id,
            timestamp=timestamp,
        )
        self._players_recorded = False
        self._current_hand = None

    def record_action(
        self,
        state: StructuredGameState,
        actor: str,
        action: Action,
        is_following_gto: bool = True,
        gto_deviation: str | None = None,
    ) -> None:
        """Record an action with minimal data needed for statistics.

        Args:
            state: Current game state
            actor: Player making the action
            action: The action taken
            is_following_gto: Whether the decision followed GTO (default True)
            gto_deviation: The GTO deviation reasoning (if deviating)
        """
        if self._current_tournament is None:
            raise ValueError("No tournament started. Call start_tournament first.")

        if not self._players_recorded:
            self._current_tournament.players = [p.name for p in state.players]
            self._players_recorded = True

        # Check if we need to start a new hand
        if self._current_hand is None or self._current_hand.hand_number != state.hand_number:
            self._current_hand = HandRecord(
                hand_number=state.hand_number,
                small_blind=state.small_blind,
                big_blind=state.big_blind,
            )
            # Capture starting stacks from the first action's state
            self._current_hand.starting_stacks = {p.name: p.stack for p in state.players}
            self._current_tournament.hands.append(self._current_hand)

        minimal_action = MinimalAction.from_full_state(state, actor, action)

        if is_following_gto:
            minimal_action.decision_type = "gto"
            minimal_action.deviation_reason = None
        else:
            minimal_action.decision_type = "deviate"
            minimal_action.deviation_reason = gto_deviation

        self._current_hand.actions.append(minimal_action)

    def record_hand_result(
        self,
        finishing_stacks: dict[str, float],
        hand_number: int | None = None,
        starting_stacks: dict[str, float] | None = None,
        small_blind: float = 10.0,
        big_blind: float = 20.0,
    ) -> None:
        """Record the finishing stacks for the current hand.

        If no actions were recorded for this hand (e.g., all-in for blind),
        this will create a new HandRecord using the provided hand_number.

        Args:
            finishing_stacks: Player stacks at the end of the hand
            hand_number: Optional hand number to ensure correct hand is recorded
            starting_stacks: Optional starting stacks (before blinds) for the hand
            small_blind: Small blind amount (used if creating new hand)
            big_blind: Big blind amount (used if creating new hand)
        """
        if self._current_tournament is None:
            raise ValueError("No tournament started. Call start_tournament first.")

        # If hand_number is provided and doesn't match current hand, create new hand
        if hand_number is not None:
            if self._current_hand is None or self._current_hand.hand_number != hand_number:
                # Create a new hand record for hands without actions (e.g., all-in for blind)
                self._current_hand = HandRecord(
                    hand_number=hand_number,
                    small_blind=small_blind,
                    big_blind=big_blind,
                )
                if starting_stacks:
                    self._current_hand.starting_stacks = starting_stacks
                self._current_tournament.hands.append(self._current_hand)

        if self._current_hand is not None:
            self._current_hand.finishing_stacks = finishing_stacks
            # Update starting stacks if provided and not already set
            if starting_stacks and not self._current_hand.starting_stacks:
                self._current_hand.starting_stacks = starting_stacks

    def record_ev(self, ev_records: list[EVRecord]) -> None:
        """Record EV data from showdown hands to the current hand.

        Validates that EV records match the current hand number.
        """
        if self._current_tournament is None:
            raise ValueError("No tournament started. Call start_tournament first.")

        if self._current_hand is None:
            raise ValueError("No hand started. Record an action first.")

        # Validate EV records match current hand
        for ev in ev_records:
            if ev.hand_number != self._current_hand.hand_number:
                raise ValueError(
                    f"EV record hand_number ({ev.hand_number}) doesn't match "
                    f"current hand ({self._current_hand.hand_number}). "
                    f"Ensure record_hand_result was called with correct hand_number."
                )

        self._current_hand.ev_records.extend(ev_records)

    def save_tournament(self, incomplete: bool = False) -> str | None:
        """Save the current tournament record to a JSON file.

        Args:
            incomplete: If True, prefix filename with "incomplete_" for interrupted tournaments.

        Returns:
            Path to the saved file, or None if no tournament to save.
        """
        if self._current_tournament is None:
            return None

        # For incomplete tournaments, fill in missing finishing_stacks from last action
        if incomplete:
            self._fill_missing_finishing_stacks()

        self._gamestates_dir.mkdir(parents=True, exist_ok=True)

        prefix = "incomplete_" if incomplete else ""
        filename = (
            f"{prefix}tournament_{self._current_tournament.timestamp}"
            f"_{self._current_tournament.tournament_id}.json"
        )
        filepath = self._gamestates_dir / filename

        with open(filepath, "w") as f:
            json.dump(self._current_tournament.to_dict(), f, indent=2)

        self._current_tournament = None
        self._current_hand = None
        return str(filepath)

    def _fill_missing_finishing_stacks(self) -> None:
        """Fill in missing finishing_stacks from the last action's stacks for incomplete hands."""
        if self._current_tournament is None:
            return

        for hand in self._current_tournament.hands:
            if not hand.finishing_stacks and hand.actions:
                # Use the last action's stacks as approximate finishing stacks
                last_action = hand.actions[-1]
                hand.finishing_stacks = last_action.stacks.copy()

    @classmethod
    def load_tournament(cls, filepath: str) -> TournamentRecord:
        """Load a tournament record from a JSON file (supports v1, v2, and v3 formats)."""
        with open(filepath, "r") as f:
            data = json.load(f)
        return TournamentRecord.from_dict(data)

    @classmethod
    def load_all_tournaments(
        cls, gamestates_dir: str = "data/gamestates"
    ) -> list[TournamentRecord]:
        """Load all tournament records from the gamestates directory."""
        path = Path(gamestates_dir)
        if not path.exists():
            return []

        tournaments = []
        for filepath in sorted(path.glob("tournament_*.json")):
            try:
                tournaments.append(cls.load_tournament(str(filepath)))
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Warning: Could not load {filepath}: {e}")
                continue

        return tournaments
