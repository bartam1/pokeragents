"""
Agent D Scenario Tests - Test the simple architecture agent.

These tests run Agent D (single LLM) against JSON-defined scenarios
to validate decision quality and reasoning.
"""
import pytest

from backend.config import Settings
from backend.domain.agent.poker_agent import PokerAgent
from backend.domain.agent.strategies.base import AGENT_D_INFORMED
from tests.agent_scenarios.loader import load_scenario
from tests.agent_scenarios.utils import (
    SCENARIOS_DIR,
    get_all_scenarios,
    print_decision,
    print_scenario_header,
    print_test_header,
    validate_decision,
)

AGENT_D_STRATEGY = AGENT_D_INFORMED


class TestAgentDScenarios:
    """Test Agent D against various poker scenarios."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("scenario_id,scenario_path", get_all_scenarios())
    async def test_scenario(
        self,
        scenario_id: str,
        scenario_path,
        settings: Settings,
    ):
        """
        Test Agent D's decision on a specific scenario.

        This test:
        1. Loads the scenario from JSON
        2. Creates Agent D with the scenario's knowledge base
        3. Runs decide() with real LLM call
        4. Prints full decision output
        5. Validates against expected behavior
        """
        scenario = load_scenario(scenario_path)
        print_scenario_header(scenario)

        agent = PokerAgent(
            player_id="agent_d",
            strategy=AGENT_D_STRATEGY,
            knowledge_base=scenario.knowledge_base,
            settings=settings,
        )

        decision = await agent.decide(scenario.game_state)
        action = decision.to_action(scenario.game_state)

        print_decision("AGENT D", "📊", decision, action)
        validate_decision(action, decision, scenario)


class TestAgentDSingleScenario:
    """Test Agent D with a single scenario for quick validation."""

    @pytest.mark.asyncio
    async def test_preflop_aa(self, settings: Settings):
        """Test Agent D with premium AA preflop - should raise."""
        scenario_path = SCENARIOS_DIR / "preflop" / "premium_aa_utg.json"

        if not scenario_path.exists():
            pytest.skip(f"Scenario file not found: {scenario_path}")

        scenario = load_scenario(scenario_path)

        agent = PokerAgent(
            player_id="agent_d",
            strategy=AGENT_D_STRATEGY,
            knowledge_base=scenario.knowledge_base,
            settings=settings,
        )

        decision = await agent.decide(scenario.game_state)
        action = decision.to_action(scenario.game_state)

        print_test_header("AA Preflop Test", "Agent D")
        print_decision("AGENT D", "📊", decision, action)

        assert action.type.value in ["raise", "all_in"], f"AA should raise, got {action.type.value}"
