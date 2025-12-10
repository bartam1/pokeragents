"""
Agent E Scenario Tests - Test the ensemble architecture agent.

These tests run Agent E (multi-agent ensemble: GTO + Exploit + Decision)
against JSON-defined scenarios to validate decision quality and reasoning.
"""
import pytest

from backend.config import Settings
from backend.domain.agent.ensemble_agent import EnsemblePokerAgent
from backend.domain.agent.poker_agent import PokerAgent
from backend.domain.agent.strategies.base import AGENT_D_INFORMED, AGENT_E_ENSEMBLE
from tests.agent_scenarios.loader import load_scenario
from tests.agent_scenarios.utils import (
    SCENARIOS_DIR,
    get_all_scenarios,
    print_decision,
    print_decision_compact,
    print_scenario_header,
    print_test_header,
    validate_decision,
)

AGENT_E_STRATEGY = AGENT_E_ENSEMBLE
AGENT_D_STRATEGY = AGENT_D_INFORMED


class TestAgentEScenarios:
    """Test Agent E against various poker scenarios."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("scenario_id,scenario_path", get_all_scenarios())
    async def test_scenario(
        self,
        scenario_id: str,
        scenario_path,
        settings: Settings,
    ):
        """
        Test Agent E's decision on a specific scenario.

        This test:
        1. Loads the scenario from JSON
        2. Creates Agent E with the scenario's knowledge base
        3. Runs decide() with real LLM calls (3 calls: GTO, Exploit, Decision)
        4. Prints full decision output
        5. Validates against expected behavior
        """
        scenario = load_scenario(scenario_path)
        print_scenario_header(scenario)

        agent = EnsemblePokerAgent(
            player_id="agent_e",
            strategy=AGENT_E_STRATEGY,
            knowledge_base=scenario.knowledge_base,
            settings=settings,
        )

        decision = await agent.decide(scenario.game_state)
        action = decision.to_action(scenario.game_state)

        print_decision("AGENT E (ENSEMBLE)", "🎭", decision, action)
        validate_decision(action, decision, scenario)


class TestAgentEComparison:
    """Compare Agent E and Agent D on the same scenarios."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("scenario_id,scenario_path", get_all_scenarios())
    async def test_compare_agents(
        self,
        scenario_id: str,
        scenario_path,
        settings: Settings,
    ):
        """
        Compare Agent D and Agent E decisions on the same scenario.

        This test runs both agents on the same scenario and compares:
        - Action taken
        - Confidence level
        - Reasoning quality
        """
        scenario = load_scenario(scenario_path)

        print(f"\n{'='*70}")
        print(f"COMPARISON: {scenario.name}")
        print(f"{'='*70}")
        print(f"Hero cards: {scenario.game_state.get_hole_cards_str()}")
        print(f"Board: {scenario.game_state.get_board_str() or '(preflop)'}")
        print(f"{'='*70}")

        # Create both agents with same knowledge
        agent_d = PokerAgent(
            player_id="agent_d",
            strategy=AGENT_D_STRATEGY,
            knowledge_base=scenario.knowledge_base,
            settings=settings,
        )

        agent_e = EnsemblePokerAgent(
            player_id="agent_e",
            strategy=AGENT_E_STRATEGY,
            knowledge_base=scenario.knowledge_base,
            settings=settings,
        )

        # Run both agents
        decision_d = await agent_d.decide(scenario.game_state)
        decision_e = await agent_e.decide(scenario.game_state)

        action_d = decision_d.to_action(scenario.game_state)
        action_e = decision_e.to_action(scenario.game_state)

        # Print comparison with full reasoning
        print("\n📊 AGENT D (Simple - 1 LLM call):")
        print_decision_compact("Agent D", decision_d, action_d)

        print(f"\n{'='*70}")

        print("\n🎭 AGENT E (Ensemble - 3 LLM calls):")
        print_decision_compact("Agent E", decision_e, action_e)

        # Compare
        same_action = action_d.type.value == action_e.type.value
        print(f"\n{'='*70}")
        print(f"{'✅' if same_action else '⚠️'} Same action type: {same_action}")
        print(f"{'='*70}")


class TestAgentESingleScenario:
    """Test Agent E with a single scenario for quick validation."""

    @pytest.mark.asyncio
    async def test_preflop_aa(self, settings: Settings):
        """Test Agent E with premium AA preflop - should raise."""
        scenario_path = SCENARIOS_DIR / "preflop" / "premium_aa_utg.json"

        if not scenario_path.exists():
            pytest.skip(f"Scenario file not found: {scenario_path}")

        scenario = load_scenario(scenario_path)

        agent = EnsemblePokerAgent(
            player_id="agent_e",
            strategy=AGENT_E_STRATEGY,
            knowledge_base=scenario.knowledge_base,
            settings=settings,
        )

        decision = await agent.decide(scenario.game_state)
        action = decision.to_action(scenario.game_state)

        print_test_header("AA Preflop Test", "Agent E (Ensemble)")
        print_decision("AGENT E (ENSEMBLE)", "🎭", decision, action)

        assert action.type.value in ["raise", "all_in"], f"AA should raise, got {action.type.value}"
