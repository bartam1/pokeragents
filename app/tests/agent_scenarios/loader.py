"""
Scenario Loader - Load JSON scenarios into game state objects.

This module converts JSON scenario files into StructuredGameState and
KnowledgeBase objects for testing poker agents.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.domain.game.models import (
    ActionType,
    Card,
    PlayerState,
    Street,
    StructuredGameState,
)
from backend.domain.player.models import (
    KnowledgeBase,
    PlayerProfile,
    PlayerStatistics,
)


@dataclass
class ExpectedBehavior:
    """Expected behavior for scenario validation."""

    valid_actions: list[str] = field(default_factory=list)
    invalid_actions: list[str] = field(default_factory=list)
    min_confidence: float = 0.0
    notes: str = ""


@dataclass
class Scenario:
    """A complete test scenario with game state and expected behavior."""

    id: str
    name: str
    description: str
    game_state: StructuredGameState
    knowledge_base: KnowledgeBase
    expected: ExpectedBehavior


def _parse_cards(card_strings: list[str] | None) -> list[Card] | None:
    """Convert list of card strings to Card objects."""
    if card_strings is None:
        return None
    return [Card.from_string(s) for s in card_strings]


def _parse_action_type(action_str: str) -> ActionType:
    """Convert action string to ActionType enum."""
    return ActionType(action_str.lower())


def _parse_street(street_str: str) -> Street:
    """Convert street string to Street enum."""
    return Street(street_str.lower())


def _parse_player_state(data: dict[str, Any]) -> PlayerState:
    """Parse a player state from JSON data."""
    return PlayerState(
        seat=data["seat"],
        name=data["name"],
        stack=float(data["stack"]),
        is_active=data["is_active"],
        is_all_in=data["is_all_in"],
        current_bet=float(data["current_bet"]),
        hole_cards=_parse_cards(data.get("hole_cards")),
    )


def _parse_game_state(data: dict[str, Any]) -> StructuredGameState:
    """Parse StructuredGameState from JSON data."""
    return StructuredGameState(
        hand_number=data["hand_number"],
        button_seat=data["button_seat"],
        small_blind=float(data["small_blind"]),
        big_blind=float(data["big_blind"]),
        street=_parse_street(data["street"]),
        pot=float(data["pot"]),
        community_cards=_parse_cards(data.get("community_cards", [])) or [],
        players=[_parse_player_state(p) for p in data["players"]],
        hero_seat=data["hero_seat"],
        current_bet=float(data["current_bet"]),
        min_raise=float(data["min_raise"]),
        max_raise=float(data["max_raise"]),
        legal_actions=[_parse_action_type(a) for a in data["legal_actions"]],
        action_history=data.get("action_history", []),
    )


def _parse_statistics(data: dict[str, Any]) -> PlayerStatistics:
    """Parse PlayerStatistics from JSON data."""
    stats = PlayerStatistics()

    # Set all the public fields
    stats.hands_played = data.get("hands_played", 0)
    stats.vpip = data.get("vpip", 0.0)
    stats.pfr = data.get("pfr", 0.0)
    stats.limp_frequency = data.get("limp_frequency", 0.0)
    stats.three_bet_pct = data.get("three_bet_pct", 0.0)
    stats.fold_to_three_bet = data.get("fold_to_three_bet", 0.0)
    stats.cbet_flop_pct = data.get("cbet_flop_pct", 0.0)
    stats.cbet_turn_pct = data.get("cbet_turn_pct", 0.0)
    stats.cbet_river_pct = data.get("cbet_river_pct", 0.0)
    stats.aggression_factor = data.get("aggression_factor", 0.0)
    stats.river_aggression = data.get("river_aggression", 0.0)
    stats.wtsd = data.get("wtsd", 0.0)
    stats.wsd = data.get("wsd", 0.0)
    stats.avg_bet_sizing = data.get("avg_bet_sizing", 0.0)
    stats.avg_raise_sizing = data.get("avg_raise_sizing", 0.0)

    return stats


def _parse_knowledge_base(data: dict[str, Any]) -> KnowledgeBase:
    """Parse KnowledgeBase from JSON data."""
    kb = KnowledgeBase()

    profiles_data = data.get("profiles", {})
    for player_id, profile_data in profiles_data.items():
        stats = _parse_statistics(profile_data.get("statistics", {}))
        profile = PlayerProfile(
            player_id=profile_data.get("player_id", player_id),
            name=profile_data.get("name", player_id),
            statistics=stats,
            tendencies=profile_data.get("tendencies", []),
        )
        kb.profiles[player_id] = profile

    return kb


def _parse_expected(data: dict[str, Any]) -> ExpectedBehavior:
    """Parse ExpectedBehavior from JSON data."""
    return ExpectedBehavior(
        valid_actions=data.get("valid_actions", []),
        invalid_actions=data.get("invalid_actions", []),
        min_confidence=data.get("min_confidence", 0.0),
        notes=data.get("notes", ""),
    )


def load_scenario(filepath: str | Path) -> Scenario:
    """
    Load a scenario from a JSON file.

    Args:
        filepath: Path to the JSON scenario file

    Returns:
        Scenario object with game state, knowledge base, and expected behavior
    """
    path = Path(filepath)

    with open(path, "r") as f:
        data = json.load(f)

    game_state = _parse_game_state(data["structured_game_state"])
    knowledge_base = _parse_knowledge_base(data.get("knowledge_base", {}))
    expected = _parse_expected(data.get("expected", {}))

    return Scenario(
        id=data.get("id", path.stem),
        name=data.get("name", path.stem),
        description=data.get("description", ""),
        game_state=game_state,
        knowledge_base=knowledge_base,
        expected=expected,
    )


def load_scenarios_from_dir(directory: str | Path) -> list[Scenario]:
    """
    Load all scenarios from a directory recursively.

    Args:
        directory: Path to directory containing JSON scenario files

    Returns:
        List of Scenario objects
    """
    path = Path(directory)
    scenarios = []

    for json_file in path.rglob("*.json"):
        try:
            scenario = load_scenario(json_file)
            scenarios.append(scenario)
        except Exception as e:
            print(f"Warning: Failed to load {json_file}: {e}")

    return scenarios


def get_scenario_ids(directory: str | Path) -> list[tuple[str, Path]]:
    """
    Get list of scenario IDs and paths for pytest parametrization.

    Args:
        directory: Path to directory containing JSON scenario files

    Returns:
        List of (scenario_id, filepath) tuples
    """
    path = Path(directory)
    result = []

    for json_file in sorted(path.rglob("*.json")):
        # Use relative path from scenarios dir as ID
        rel_path = json_file.relative_to(path)
        scenario_id = str(rel_path.with_suffix("")).replace("/", "_")
        result.append((scenario_id, json_file))

    return result
