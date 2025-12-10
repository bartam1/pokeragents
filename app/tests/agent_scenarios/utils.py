"""
Shared utilities for agent scenario tests.

This module contains common functions for printing, validation,
and scenario handling to avoid code duplication across test files.
"""
from pathlib import Path

from backend.domain.game.models import Action, StructuredGameState
from backend.domain.agent.models import ActionDecision
from tests.agent_scenarios.loader import Scenario, get_scenario_ids


# Scenarios directory path
SCENARIOS_DIR = Path(__file__).parent / "scenarios"


def get_all_scenarios() -> list[tuple[str, Path]]:
    """Get all scenario IDs and paths for pytest parametrization."""
    if not SCENARIOS_DIR.exists():
        return []
    return get_scenario_ids(SCENARIOS_DIR)


def print_scenario_header(scenario: Scenario) -> None:
    """Print scenario information header."""
    print(f"\n{'='*70}")
    print(f"SCENARIO: {scenario.name}")
    print(f"{'='*70}")
    print(f"Description: {scenario.description}")
    print(f"Street: {scenario.game_state.street.value}")
    print(f"Hero cards: {scenario.game_state.get_hole_cards_str()}")
    print(f"Board: {scenario.game_state.get_board_str() or '(preflop)'}")
    print(f"Pot: {scenario.game_state.pot}")
    print(f"To call: {scenario.game_state.current_bet - scenario.game_state.hero.current_bet}")
    print(f"Legal actions: {[a.value for a in scenario.game_state.legal_actions]}")
    print(f"{'='*70}")


def print_decision(
    agent_name: str,
    agent_emoji: str,
    decision: ActionDecision,
    action: Action,
) -> None:
    """Print agent decision with full reasoning."""
    print(f"\n{agent_emoji} {agent_name} DECISION:")
    print(f"{'='*70}")
    print(f"Action: {action.type.value} {action.amount if action.amount else ''}")
    print(f"Confidence: {decision.confidence:.2f}")
    print(f"\n📊 GTO Analysis:")
    print(f"   {decision.gto_analysis}")
    print(f"\n🔍 Exploit Analysis:")
    print(f"   {decision.exploit_analysis}")
    print(f"\n📐 GTO Deviation:")
    print(f"   {decision.gto_deviation}")
    print(f"{'='*70}")


def print_decision_compact(
    agent_name: str,
    decision: ActionDecision,
    action: Action,
    indent: str = "   ",
) -> None:
    """Print agent decision in compact format for comparisons."""
    print(f"{indent}Action: {action.type.value} {action.amount if action.amount else ''}")
    print(f"{indent}Confidence: {decision.confidence:.2f}")
    print(f"\n{indent}GTO Analysis:")
    print(f"{indent}   {decision.gto_analysis}")
    print(f"\n{indent}Exploit Analysis:")
    print(f"{indent}   {decision.exploit_analysis}")
    print(f"\n{indent}GTO Deviation:")
    print(f"{indent}   {decision.gto_deviation}")


def validate_decision(
    action: Action,
    decision: ActionDecision,
    scenario: Scenario,
) -> None:
    """Validate decision against expected behavior and print results."""
    action_str = action.type.value
    
    if scenario.expected.valid_actions:
        assert action_str in scenario.expected.valid_actions, (
            f"Action '{action_str}' not in valid actions: {scenario.expected.valid_actions}"
        )
        print(f"✅ Action '{action_str}' is valid (expected: {scenario.expected.valid_actions})")
    
    if scenario.expected.invalid_actions:
        assert action_str not in scenario.expected.invalid_actions, (
            f"Action '{action_str}' is in invalid actions: {scenario.expected.invalid_actions}"
        )
        print(f"✅ Action '{action_str}' is not invalid (forbidden: {scenario.expected.invalid_actions})")
    
    if scenario.expected.min_confidence > 0:
        assert decision.confidence >= scenario.expected.min_confidence, (
            f"Confidence {decision.confidence:.2f} below minimum {scenario.expected.min_confidence}"
        )
        print(f"✅ Confidence {decision.confidence:.2f} >= {scenario.expected.min_confidence}")
    
    if scenario.expected.notes:
        print(f"📝 Notes: {scenario.expected.notes}")


def print_test_header(test_name: str, agent_name: str) -> None:
    """Print a header for single scenario tests."""
    print(f"\n{'='*70}")
    print(f"🎯 {test_name} - {agent_name} Decision")
    print(f"{'='*70}")

