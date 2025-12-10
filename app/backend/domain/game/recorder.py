"""
Game State Recorder - Records game states during tournament play.

This module provides functionality to save all game states from a tournament
to JSON files for later analysis and statistics recalculation.
"""
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.domain.game.models import Action, StructuredGameState


@dataclass
class RecordedAction:
    """A recorded game state with the action taken."""
    state: StructuredGameState
    actor: str
    action: Action

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.to_dict(),
            "actor": self.actor,
            "action": self.action.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RecordedAction":
        return cls(
            state=StructuredGameState.from_dict(data["state"]),
            actor=data["actor"],
            action=Action.from_dict(data["action"]),
        )


@dataclass
class TournamentRecord:
    """Complete record of a tournament's game states."""
    tournament_id: str
    timestamp: str
    recorded_actions: list[RecordedAction] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tournament_id": self.tournament_id,
            "timestamp": self.timestamp,
            "states": [ra.to_dict() for ra in self.recorded_actions],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TournamentRecord":
        return cls(
            tournament_id=data["tournament_id"],
            timestamp=data["timestamp"],
            recorded_actions=[RecordedAction.from_dict(s) for s in data["states"]],
        )


class GameStateRecorder:
    """Records game states during tournament play for later analysis."""

    def __init__(self, gamestates_dir: str = "data/gamestates"):
        self._gamestates_dir = Path(gamestates_dir)
        self._current_tournament: TournamentRecord | None = None

    def start_tournament(self, tournament_id: str) -> None:
        """Start recording a new tournament."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._current_tournament = TournamentRecord(
            tournament_id=tournament_id,
            timestamp=timestamp,
        )

    def record_action(self, state: StructuredGameState, actor: str, action: Action) -> None:
        """Record a game state and the action taken."""
        if self._current_tournament is None:
            raise ValueError("No tournament started. Call start_tournament first.")
        self._current_tournament.recorded_actions.append(
            RecordedAction(state=state, actor=actor, action=action)
        )

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
        """Load a tournament record from a JSON file."""
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

