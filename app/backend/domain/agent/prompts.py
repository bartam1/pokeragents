"""
Shared prompt guidelines for poker agents.

This module provides a SINGLE SOURCE OF TRUTH for exploitation guidelines
used by both PokerAgent (Agent D) and EnsembleAgent (Agent E).

Keep it simple - let the LLM reason with clear principles.
"""

# =============================================================================
# Exploitation Guidelines (Shared)
# =============================================================================

EXPLOITATION_GUIDELINES = """
## Exploitation Guidelines

**Key Principle: More hands observed = More confidence in exploitation**

Before deciding to exploit an opponent:
1. **CHECK THE HAND COUNT** - How many hands have you observed on this opponent?
2. **Scale your confidence** - Few hands = low confidence, many hands = high confidence
3. **GTO is the safe default** - When uncertain, follow GTO

Simple rule of thumb:
- Very few hands → Stick to GTO, don't exploit
- Moderate hands → Consider small adjustments if leak is clear
- Many hands → Can exploit more confidently if clear leak exists

**When in doubt, follow GTO. It's mathematically unexploitable.**
"""


# =============================================================================
# GTO Default Principle (Shared)
# =============================================================================

GTO_DEFAULT = """
## GTO is Your Default Strategy

GTO (Game Theory Optimal) strategy cannot be exploited by opponents.
Only deviate from GTO when you have:
1. **Enough observed hands** on the opponent
2. **A clear, specific leak** to exploit (not just "they're loose")
3. **Confidence** that the exploit improves your expected value

If any of these are missing → Follow GTO.
"""


# =============================================================================
# Response Format (Shared)
# =============================================================================

RESPONSE_FORMAT = """
## Response Format (JSON)

Respond with a structured JSON object containing:

- **gto_analysis**: Your GTO-based thinking (1-2 sentences)
- **exploit_analysis**: Opponent exploitation reasoning - MENTION HAND COUNT (1-2 sentences)
- **gto_deviation**: "Following GTO because..." or "Deviating from GTO because..."
- **action_type**: One of: fold, check, call, bet, raise, all_in
- **sizing**: For bet/raise, specify ONE of:
  - {{"bb_multiple": 3}} for 3x big blind
  - {{"pot_fraction": 0.75}} for 75% pot
  - {{"absolute": 150}} for exact chip amount
  - null for fold/check/call/all_in
- **confidence**: Number from 0.0 to 1.0
"""


# =============================================================================
# Examples (Shared)
# =============================================================================

EXAMPLE_GTO_FOLLOWING = """
Example (Following GTO):
{{
  "gto_analysis": "With AKo in late position, standard play is to 3-bet for value.",
  "exploit_analysis": "Opponent has only 35 hands - not enough data to exploit reliably.",
  "gto_deviation": "Following GTO because hand count is too low for confident exploitation.",
  "action_type": "raise",
  "sizing": {{"bb_multiple": 3}},
  "confidence": 0.90
}}
"""

EXAMPLE_EXPLOITATION = """
Example (Exploiting with confidence):
{{
  "gto_analysis": "GTO suggests standard 3x sizing.",
  "exploit_analysis": "Opponent has 180 hands showing 58% VPIP - confirmed calling station.",
  "gto_deviation": "Deviating from GTO because 180 hands clearly show opponent calls too much.",
  "action_type": "raise",
  "sizing": {{"bb_multiple": 4}},
  "confidence": 0.85
}}
"""
