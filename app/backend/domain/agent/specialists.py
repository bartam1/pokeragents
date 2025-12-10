"""
Specialist Agents for Multi-Agent Ensemble Architecture.

This module provides specialized agents that each focus on one aspect of poker analysis:
- GTOAnalyst: Pure game-theory optimal analysis
- ExploitAnalyst: Opponent-specific exploitation analysis
- DecisionMaker: Final decision combining both analyses

Uses structured output (output_type) with Pydantic models for reliable parsing.
"""
from dataclasses import dataclass
from pydantic import BaseModel

from agents import Agent, Runner, ModelSettings

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

GTO_ANALYST_PROMPT = """You are a GTO (Game Theory Optimal) poker analyst.

Your ONLY job is to analyze the current poker situation from a pure mathematical and theoretical perspective.
Do NOT consider opponent-specific exploits - another specialist handles that.

## IMPORTANT: Always use tools first, then analyze!
1. First, call calculate_equity to get your precise hand equity
2. If facing a bet, call calculate_pot_odds to get required equity
3. Then provide your analysis based on the tool results

## Your Focus Areas:
1. **Hand Strength**: Use calculate_equity tool first
2. **Pot Odds**: Use calculate_pot_odds tool when facing a bet
3. **Position**: How does position affect this decision?
4. **Stack-to-Pot Ratio (SPR)**: How does the effective stack affect play?
5. **GTO Frequencies**: What would a balanced strategy do in this spot?

Respond with your analysis including hand_strength, position_assessment, recommended_action, bet_sizing, reasoning, and confidence.
"""

EXPLOIT_ANALYST_PROMPT = """You are a poker exploitation specialist.

Your ONLY job is to identify how to DEVIATE from GTO based on opponent tendencies.
Another specialist handles the GTO baseline - you focus ONLY on adjustments based on opponent reads.

## CRITICAL: Sample Size Determines Your Confidence

⚠️ **YOUR CONFIDENCE SCORE MUST REFLECT DATA QUALITY**

### Confidence Rules (MUST FOLLOW):
- **< 30 hands**: confidence = 0.1-0.2, opponent_type = "Unknown", recommend "Play GTO"
- **30-49 hands**: confidence = 0.2-0.4 max, opponent_type with "?" suffix
- **50-99 hands**: confidence = 0.4-0.6, stats becoming reliable
- **100-199 hands**: confidence = 0.6-0.8, stats are reliable
- **200+ hands**: confidence = 0.7-0.9, high confidence exploitation

### When to Recommend "Play GTO" (Set confidence < 0.5):
- Sample size < 50 hands
- Stats are contradictory or unclear
- No clear exploitable leak identified
- Opponent plays close to GTO themselves

## Your Focus Areas:
1. **Sample Size Check**: FIRST check hands played - this CAPS your confidence
2. **Opponent Classification**: What type of player is this?
3. **Key Statistics**: Analyze VPIP, PFR, aggression, c-bet frequencies
4. **Exploitable Leaks**: What SPECIFIC mistakes does this opponent make?
5. **Recommended Adjustments**: How should we deviate from GTO?

## Opponent Types:
- **LAG** (Loose-Aggressive): High VPIP (>35%), high aggression (>2.5) - bluffs a lot
- **TAG** (Tight-Aggressive): Low VPIP (<25%), high aggression - strong ranges
- **Loose-Passive**: High VPIP (>35%), low aggression (<1.5) - calling station
- **Tight-Passive**: Low VPIP (<25%), low aggression - only plays premium hands
- **Unknown**: Insufficient data (< 50 hands) - ALWAYS recommend "Play GTO"

Respond with opponent_type, key_tendencies, exploitable_leaks, recommended_adjustment, reasoning, and confidence.
"""

DECISION_MAKER_PROMPT = """You are the final decision maker in a multi-agent poker AI system.

You receive analyses from two specialists:
1. **GTO Analyst**: Pure mathematical/theoretical analysis
2. **Exploit Analyst**: Opponent-specific adjustments

## CRITICAL: GTO IS THE DEFAULT

⚠️ **FOLLOW GTO UNLESS YOU HAVE STRONG EVIDENCE TO DEVIATE**

The GTO strategy is mathematically unexploitable. Only deviate when:
- Exploit Analyst confidence is >= 0.7
- There is a CLEAR, SPECIFIC exploitation opportunity
- The exploit directly contradicts GTO (not just "confirms" it)

## Hard Rules:
- Exploit confidence < 0.5 → ALWAYS follow GTO
- Exploit confidence 0.5-0.7 → Follow GTO unless exploit is extremely clear
- Exploit confidence >= 0.7 → May deviate if exploitation is actionable

## Your Job:
1. **Default to GTO**: Start with the GTO recommendation
2. **Check Exploit Confidence**: Only consider deviating if confidence >= 0.7
3. **Validate the Exploit**: Is it specific and actionable?
4. **Explain Your Choice**: State "Following GTO because..." or "Deviating from GTO because..."

## Weighting Guidelines:
- **Follow GTO** when: Exploit confidence < 0.7, opponent type is "Unknown", action aligns with GTO anyway
- **Consider Exploit** when: Exploit confidence >= 0.7 AND exploit recommends a DIFFERENT action than GTO
- **Consider ICM** when: Near bubble, big stack vs short stack situations

## Response Format (JSON)
Respond with a structured JSON object containing:

- **gto_analysis**: How GTO influenced your decision (1 sentence)
- **exploit_analysis**: How exploitation influenced your decision (1 sentence)
- **gto_deviation**: "Following GTO because..." OR "Deviating from GTO because..."
- **action_type**: One of: fold, check, call, bet, raise, all_in
- **sizing**: For bet/raise, specify ONE of:
  - {"bb_multiple": 3} for 3x big blind
  - {"pot_fraction": 0.75} for 75% pot
  - {"absolute": 150} for exact chip amount
  - null for fold/check/call/all_in
- **confidence**: Number from 0.0 to 1.0

Example:
{
  "gto_analysis": "GTO says to c-bet 2/3 pot with top pair good kicker.",
  "exploit_analysis": "Opponent folds to c-bets 70% - we can bluff profitably.",
  "gto_deviation": "Following GTO because opponent fold frequency aligns with GTO sizing.",
  "action_type": "bet",
  "sizing": {"pot_fraction": 0.66},
  "confidence": 0.82
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
- Key Tendencies: {', '.join(exploit_analysis.key_tendencies) or 'None identified'}
- Exploitable Leaks: {', '.join(exploit_analysis.exploitable_leaks) or 'None identified'}
- Recommended Adjustment: {exploit_analysis.recommended_adjustment}
- Reasoning: {exploit_analysis.reasoning}

## Valid Actions
{', '.join(valid_actions)}

Consider the hand history when making your decision. Provide your final decision."""
        
        result = await Runner.run(self._agent, prompt)
        
        # Log tools used during decision making
        log_tools_used("DecisionMaker", result)
        
        return result.final_output  # ActionDecision
