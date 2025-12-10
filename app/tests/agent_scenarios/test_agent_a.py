"""
Agent A Scenario Tests - Test the aggressive bluffer agent.

These tests run Agent A (aggressive bluffer, no shared knowledge)
against JSON-defined scenarios to validate decision quality and reasoning.
"""
import pytest

from backend.config import Settings
from backend.domain.agent.poker_agent import PokerAgent
from backend.domain.agent.strategies.base import AGENT_A_BLUFFER
from backend.domain.player.models import KnowledgeBase
from tests.agent_scenarios.loader import load_scenario
from tests.agent_scenarios.utils import (
    SCENARIOS_DIR,
    get_all_scenarios,
    print_decision,
    print_scenario_header,
    print_test_header,
)

AGENT_A_STRATEGY = AGENT_A_BLUFFER


class TestAgentAScenarios:
    """Test Agent A against various poker scenarios."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("scenario_id,scenario_path", get_all_scenarios())
    async def test_scenario(
        self,
        scenario_id: str,
        scenario_path,
        settings: Settings,
    ):
        """
        Test Agent A's decision on a specific scenario.

        Agent A is an aggressive bluffer with NO shared knowledge.
        This test validates how a "personality-driven" agent behaves
        without access to opponent statistics.
        """
        scenario = load_scenario(scenario_path)
        print_scenario_header(scenario)

        # Agent A has NO shared knowledge - uses empty KnowledgeBase
        agent = PokerAgent(
            player_id="agent_a",
            strategy=AGENT_A_STRATEGY,
            knowledge_base=KnowledgeBase(),  # Empty - no opponent stats
            settings=settings,
        )

        decision = await agent.decide(scenario.game_state)
        action = decision.to_action(scenario.game_state)

        print_decision("AGENT A (Bluffer)", "🎭", decision, action)

        # Note: We don't validate against expected behavior for Agent A
        # because it doesn't have knowledge and may make different decisions
        print(f"📝 Agent A (no knowledge) chose: {action.type.value}")
        print("📝 Strategy: Aggressive bluffer - expects more raises/bets")


class TestAgentASingleScenario:
    """Test Agent A with a single scenario for quick validation."""

    @pytest.mark.asyncio
    async def test_preflop_aa(self, settings: Settings):
        """Test Agent A with premium AA preflop - should raise aggressively."""
        scenario_path = SCENARIOS_DIR / "preflop" / "premium_aa_utg.json"

        if not scenario_path.exists():
            pytest.skip(f"Scenario file not found: {scenario_path}")

        scenario = load_scenario(scenario_path)

        # Agent A has NO shared knowledge
        agent = PokerAgent(
            player_id="agent_a",
            strategy=AGENT_A_STRATEGY,
            knowledge_base=KnowledgeBase(),  # Empty
            settings=settings,
        )

        decision = await agent.decide(scenario.game_state)
        action = decision.to_action(scenario.game_state)

        print_test_header("AA Preflop Test", "Agent A (Bluffer)")
        print_decision("AGENT A (Bluffer)", "🎭", decision, action)

        # AA should raise or all-in, never fold - even for a bluffer
        assert action.type.value in ["raise", "all_in"], f"AA should raise, got {action.type.value}"

    @pytest.mark.asyncio
    async def test_river_bluff_catch(self, settings: Settings):
        """Test Agent A on river bluff catch - may choose differently without stats."""
        scenario_path = SCENARIOS_DIR / "river" / "bluff_catch_vs_aggressor.json"

        if not scenario_path.exists():
            pytest.skip(f"Scenario file not found: {scenario_path}")

        scenario = load_scenario(scenario_path)

        # Agent A has NO shared knowledge - can't exploit based on stats
        agent = PokerAgent(
            player_id="agent_a",
            strategy=AGENT_A_STRATEGY,
            knowledge_base=KnowledgeBase(),  # Empty
            settings=settings,
        )

        decision = await agent.decide(scenario.game_state)
        action = decision.to_action(scenario.game_state)

        print_test_header("River Bluff Catch Test", "Agent A (Bluffer)")
        print_decision("AGENT A (Bluffer)", "🎭", decision, action)

        # Agent A without knowledge may make a GTO-based decision
        # or may lean aggressive based on personality
        print(f"📝 Agent A (no stats) chose: {action.type.value}")
        print("📝 Without opponent stats, Agent A relies on personality + GTO")
