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

from backend.domain.game.models import Action, ActionType, EVRecord, StructuredGameState, Street


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

    def to_dict(self) -> dict[str, Any]:
        result = {
            "hand_number": self.hand_number,
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
        if self.deviation_reason:
            result["deviation_reason"] = self.deviation_reason
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MinimalAction":
        return cls(
            hand_number=data["hand_number"],
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
            1 for a in state.action_history
            if a.get("street") == "preflop"
            and a.get("action") in ("raise", "bet", "all_in")
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
        return [
            {"street": "preflop", "action": "raise"}
            for _ in range(self.preflop_raise_count)
        ]


@dataclass
class TournamentRecord:
    """Complete record of a tournament's actions for statistics and EV tracking."""
    tournament_id: str
    timestamp: str
    players: list[str] = field(default_factory=list)
    big_blind: float = 20.0
    actions: list[MinimalAction] = field(default_factory=list)
    ev_records: list[EVRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tournament_id": self.tournament_id,
            "timestamp": self.timestamp,
            "format_version": 2,
            "players": self.players,
            "big_blind": self.big_blind,
            "actions": [a.to_dict() for a in self.actions],
            "ev_records": [ev.to_dict() for ev in self.ev_records],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TournamentRecord":
        """Load from dict, supporting both old and new formats."""
        format_version = data.get("format_version", 1)
        
        if format_version >= 2:
            return cls._from_v2_dict(data)
        else:
            return cls._from_v1_dict(data)

    @classmethod
    def _from_v2_dict(cls, data: dict[str, Any]) -> "TournamentRecord":
        """Load from new minimal format (v2)."""
        return cls(
            tournament_id=data["tournament_id"],
            timestamp=data["timestamp"],
            players=data.get("players", []),
            big_blind=data.get("big_blind", 20.0),
            actions=[MinimalAction.from_dict(a) for a in data.get("actions", [])],
            ev_records=[EVRecord.from_dict(ev) for ev in data.get("ev_records", [])],
        )

    @classmethod
    def _from_v1_dict(cls, data: dict[str, Any]) -> "TournamentRecord":
        """Load from old full-state format (v1) and convert to minimal."""
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
                1 for a in state.action_history
                if a.get("street") == "preflop"
                and a.get("action") in ("raise", "bet", "all_in")
            )
            
            actions.append(MinimalAction(
                hand_number=state.hand_number,
                street=state.street,
                actor=actor,
                action_type=action_data["type"],
                amount=action_data.get("amount"),
                pot=state.pot,
                current_bet=state.current_bet,
                preflop_raise_count=preflop_raise_count,
            ))
        
        return cls(
            tournament_id=tournament_id,
            timestamp=timestamp,
            players=sorted(players),
            big_blind=big_blind,
            actions=actions,
        )


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

    def start_tournament(self, tournament_id: str, big_blind: float = 20.0) -> None:
        """Start recording a new tournament."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._current_tournament = TournamentRecord(
            tournament_id=tournament_id,
            timestamp=timestamp,
            big_blind=big_blind,
        )
        self._players_recorded = False

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
            self._current_tournament.big_blind = state.big_blind
            self._players_recorded = True
        
        minimal_action = MinimalAction.from_full_state(state, actor, action)
        
        if is_following_gto:
            minimal_action.decision_type = "gto"
            minimal_action.deviation_reason = None
        else:
            minimal_action.decision_type = "deviate"
            minimal_action.deviation_reason = gto_deviation
        
        self._current_tournament.actions.append(minimal_action)

    def record_ev(self, ev_records: list[EVRecord]) -> None:
        """Record EV data from showdown hands."""
        if self._current_tournament is None:
            raise ValueError("No tournament started. Call start_tournament first.")
        
        self._current_tournament.ev_records.extend(ev_records)

    def save_tournament(self, incomplete: bool = False) -> str | None:
        """Save the current tournament record to a JSON file.
        
        Args:
            incomplete: If True, prefix filename with "incomplete_" for interrupted tournaments.
        
        Returns:
            Path to the saved file, or None if no tournament to save.
        """
        if self._current_tournament is None:
            return None

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
        return str(filepath)

    @classmethod
    def load_tournament(cls, filepath: str) -> TournamentRecord:
        """Load a tournament record from a JSON file (supports v1 and v2 formats)."""
        with open(filepath, "r") as f:
            data = json.load(f)
        return TournamentRecord.from_dict(data)

    @classmethod
    def load_all_tournaments(cls, gamestates_dir: str = "data/gamestates") -> list[TournamentRecord]:
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
