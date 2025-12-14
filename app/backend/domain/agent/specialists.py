"""
Specialist Agents for Multi-Agent Ensemble Architecture.

This module provides specialized agents that each focus on one aspect of poker analysis:
- GTOAnalyst: Pure game-theory optimal analysis
- ExploitAnalyst: Opponent-specific exploitation analysis
- DecisionMaker: Final decision combining both analyses

Uses structured output (output_type) with Pydantic models for reliable parsing.
"""

from dataclasses import dataclass

from agents import Agent, ModelSettings, Runner
from pydantic import BaseModel

from backend.config import Settings
from backend.domain.agent.models import ActionDecision
from backend.domain.agent.tools.basic_tools import POKER_TOOLS
from backend.domain.agent.utils import log_tools_used
from backend.logging_config import get_logger

logger = get_logger(__name__)


# =============================================================================
# Pydantic Models for Structured Output
# =============================================================================


class GTOAnalysisModel(BaseModel):
    """Pydantic model for structured GTO analysis output."""

    hand_strength: str
    position_assessment: str
    recommended_action: str
    bet_sizing: str
    reasoning: str
    confidence: float


class ExploitAnalysisModel(BaseModel):
    """Pydantic model for structured Exploit analysis output."""

    opponent_type: str
    key_tendencies: list[str]
    exploitable_leaks: list[str]
    recommended_adjustment: str
    reasoning: str
    confidence: float


# =============================================================================
# Output Dataclasses
# =============================================================================


@dataclass
class GTOAnalysis:
    """Structured output from the GTO Analyst."""

    hand_strength: str  # "premium", "strong", "medium", "weak", "trash"
    position_assessment: str  # "early", "middle", "late", "blinds"
    recommended_action: str  # "fold", "check", "call", "bet", "raise", "all_in"
    bet_sizing: str  # e.g., "2/3 pot", "pot", "1/2 pot"
    reasoning: str
    confidence: float  # 0.0 to 1.0


@dataclass
class ExploitAnalysis:
    """Structured output from the Exploit Analyst."""

    opponent_type: str  # "LAG", "TAG", "loose-passive", "tight-passive", "unknown"
    key_tendencies: list[str]
    exploitable_leaks: list[str]
    recommended_adjustment: str
    reasoning: str
    confidence: float  # 0.0 to 1.0


# =============================================================================
# Specialist Prompts
# =============================================================================

GTO_ANALYST_PROMPT = """You are a GTO poker analyst. Analyze from pure math/theory perspective.

Use calculate_equity and calculate_pot_odds tools first, then analyze position and SPR.

Respond with: hand_strength, position_assessment, recommended_action, bet_sizing, reasoning, confidence.
"""

EXPLOIT_ANALYST_PROMPT = """You are a poker exploitation specialist. Identify deviations from GTO based on opponent stats.

**60+ hands needed for reliable exploitation.** Scale confidence by sample size.

Opponent types: LAG (VPIP>35%, high aggression), TAG (VPIP<25%, high aggression), 
Loose-Passive (VPIP>35%, low aggression), Tight-Passive (VPIP<25%, low aggression), Unknown (<60 hands).

Respond with: opponent_type, key_tendencies, exploitable_leaks, recommended_adjustment, reasoning, confidence.
"""

DECISION_MAKER_PROMPT = """You are the final decision maker combining GTO and Exploit analyses.

**GTO IS YOUR DEFAULT** - Only deviate with high exploit confidence (0.7+) and clear opportunity.

## Response Format
{
  "gto_analysis": "GTO reasoning (1 sentence)",
  "exploit_analysis": "Exploitation reasoning (1 sentence)",
  "is_following_gto": true or false,
  "gto_deviation": "Following GTO because..." or "Deviating because...",
  "action_type": "fold|check|call|bet|raise|all_in",
  "sizing": {"pot_fraction": 0.75} or {"bb_multiple": 3} or null,
  "confidence": 0.0-1.0
}
"""


# =============================================================================
# Specialist Agent Classes
# =============================================================================


class GTOAnalyst:
    """
    Specialist agent for Game Theory Optimal analysis.

    Focuses purely on mathematical and theoretical poker strategy
    without considering opponent-specific exploitation.

    Has access to tools: calculate_equity, calculate_pot_odds, get_position_info
    """

    def __init__(self, settings: Settings):
        self._settings = settings

        model_settings_kwargs = {"temperature": settings.temperature}
        if settings.reasoning_effort:
            model_settings_kwargs["reasoning"] = {"effort": settings.reasoning_effort}

        self._agent = Agent(
            name="GTOAnalyst",
            instructions=GTO_ANALYST_PROMPT,
            model=settings.model_name,
            model_settings=ModelSettings(**model_settings_kwargs),
            tools=POKER_TOOLS,  # calculate_equity, calculate_pot_odds, get_position_info
            output_type=GTOAnalysisModel,
        )
        logger.info("GTOAnalyst initialized with tools and structured output")

    async def analyze(self, game_state_prompt: str, hand_history: str) -> GTOAnalysis:
        """
        Perform GTO analysis on the current game state.

        Args:
            game_state_prompt: Formatted game state description
            hand_history: Actions taken so far in this hand

        Returns:
            GTOAnalysis with structured recommendations
        """
        prompt = f"""Analyze this poker situation from a GTO perspective:

## Current Game State
{game_state_prompt}

## Hand History
{hand_history}

Provide your GTO analysis."""

        result = await Runner.run(self._agent, prompt)

        # Log tools used during GTO analysis
        log_tools_used("GTOAnalyst", result)

        output = result.final_output

        return GTOAnalysis(
            hand_strength=output.hand_strength,
            position_assessment=output.position_assessment,
            recommended_action=output.recommended_action,
            bet_sizing=output.bet_sizing,
            reasoning=output.reasoning,
            confidence=output.confidence,
        )


class ExploitAnalyst:
    """
    Specialist agent for opponent exploitation analysis.

    Analyzes opponent statistics and tendencies to recommend
    deviations from GTO play.
    """

    def __init__(self, settings: Settings):
        self._settings = settings

        model_settings_kwargs = {"temperature": settings.temperature}
        if settings.reasoning_effort:
            model_settings_kwargs["reasoning"] = {"effort": settings.reasoning_effort}

        self._agent = Agent(
            name="ExploitAnalyst",
            instructions=EXPLOIT_ANALYST_PROMPT,
            model=settings.model_name,
            model_settings=ModelSettings(**model_settings_kwargs),
            output_type=ExploitAnalysisModel,
        )

    async def analyze(
        self,
        game_state_prompt: str,
        opponent_stats: str,
        hand_history: str,
    ) -> ExploitAnalysis:
        """
        Perform exploitation analysis based on opponent statistics.

        Args:
            game_state_prompt: Formatted game state description
            opponent_stats: Statistics for opponents in the hand
            hand_history: Actions taken so far in this hand

        Returns:
            ExploitAnalysis with exploitation recommendations
        """
        prompt = f"""Analyze this poker situation for exploitation opportunities:

## Current Game State
{game_state_prompt}

## Opponent Statistics
{opponent_stats}

## Hand History
{hand_history}

Provide your exploitation analysis."""

        result = await Runner.run(self._agent, prompt)

        # Log tools used during Exploit analysis
        log_tools_used("ExploitAnalyst", result)

        output = result.final_output

        return ExploitAnalysis(
            opponent_type=output.opponent_type,
            key_tendencies=output.key_tendencies,
            exploitable_leaks=output.exploitable_leaks,
            recommended_adjustment=output.recommended_adjustment,
            reasoning=output.reasoning,
            confidence=output.confidence,
        )


class DecisionMaker:
    """
    Final decision maker that combines GTO and Exploit analyses.

    Weighs both specialist analyses based on confidence levels
    and situational factors to produce the final action.
    """

    def __init__(self, settings: Settings):
        self._settings = settings

        model_settings_kwargs = {"temperature": settings.temperature}
        if settings.reasoning_effort:
            model_settings_kwargs["reasoning"] = {"effort": settings.reasoning_effort}

        self._agent = Agent(
            name="DecisionMaker",
            instructions=DECISION_MAKER_PROMPT,
            model=settings.model_name,
            model_settings=ModelSettings(**model_settings_kwargs),
            output_type=ActionDecision,  # Unified decision model
        )

    async def decide(
        self,
        game_state_prompt: str,
        hand_history: str,
        gto_analysis: GTOAnalysis,
        exploit_analysis: ExploitAnalysis,
        valid_actions: list[str],
    ) -> ActionDecision:
        """
        Make final decision combining both specialist analyses.

        Args:
            game_state_prompt: Formatted game state description
            hand_history: Actions that happened earlier in this hand (preflop, flop, etc.)
            gto_analysis: Analysis from GTO specialist
            exploit_analysis: Analysis from Exploit specialist
            valid_actions: List of valid action strings

        Returns:
            ActionDecision with structured decision output
        """
        prompt = f"""Make a final poker decision based on these specialist analyses:

## Game State
{game_state_prompt}

## Hand History (Actions This Hand)
{hand_history}

## GTO Analysis (Confidence: {gto_analysis.confidence:.2f})
- Hand Strength: {gto_analysis.hand_strength}
- Position: {gto_analysis.position_assessment}
- Recommended Action: {gto_analysis.recommended_action}
- Bet Sizing: {gto_analysis.bet_sizing}
- Reasoning: {gto_analysis.reasoning}

## Exploit Analysis (Confidence: {exploit_analysis.confidence:.2f})
- Opponent Type: {exploit_analysis.opponent_type}
- Key Tendencies: {", ".join(exploit_analysis.key_tendencies) or "None identified"}
- Exploitable Leaks: {", ".join(exploit_analysis.exploitable_leaks) or "None identified"}
- Recommended Adjustment: {exploit_analysis.recommended_adjustment}
- Reasoning: {exploit_analysis.reasoning}

## Valid Actions
{", ".join(valid_actions)}

Consider the hand history when making your decision. Provide your final decision."""

        result = await Runner.run(self._agent, prompt)

        # Log tools used during decision making
        log_tools_used("DecisionMaker", result)

        return result.final_output  # ActionDecision
