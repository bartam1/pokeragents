"""
Basic poker tools using OpenAI Agents SDK @function_tool decorator.

Keep it simple - leverage PokerKit for evaluation, let LLM reason about strategy.
"""

from typing import Callable

from agents import function_tool
from pokerkit import (
    Card,
    Deck,
    StandardHighHand,
    calculate_hand_strength,
    parse_range,
)

from backend.domain.player.models import KnowledgeBase
from backend.logging_config import get_logger

logger = get_logger(__name__)


@function_tool
def calculate_pot_odds(pot_size: float, amount_to_call: float) -> str:
    """
    Calculate pot odds - the required equity to call profitably.

    Args:
        pot_size: Current pot size in chips
        amount_to_call: Amount needed to call

    Returns:
        Required equity percentage to break even
    """
    if amount_to_call <= 0:
        return "No bet to call - check is free."

    required_equity = amount_to_call / (pot_size + amount_to_call) * 100

    return f"Pot odds: Need {required_equity:.1f}% equity to call (pot {pot_size}, to call {amount_to_call})"


@function_tool
def get_position_info(hero_seat: int, button_seat: int, num_players: int) -> str:
    """
    Get position information.

    Args:
        hero_seat: Hero's seat number
        button_seat: Button's seat number
        num_players: Total number of players

    Returns:
        Position name and whether in position postflop
    """
    positions_from_button = (hero_seat - button_seat) % num_players

    if num_players == 2:
        position = "BTN/SB" if hero_seat == button_seat else "BB"
        in_position = hero_seat == button_seat
    else:
        if positions_from_button == 0:
            position = "BTN"
            in_position = True
        elif positions_from_button == 1:
            position = "SB"
            in_position = False
        elif positions_from_button == 2:
            position = "BB"
            in_position = False
        elif positions_from_button <= num_players // 3:
            position = "EP"
            in_position = False
        elif positions_from_button <= 2 * num_players // 3:
            position = "MP"
            in_position = False
        else:
            position = "LP"
            in_position = True

    return f"Position: {position}, {'in position' if in_position else 'out of position'}"


@function_tool
def calculate_equity(
    hole_cards: str,
    board: str = "",
    num_opponents: int = 1,
) -> str:
    """
    Calculate your hand's equity vs random opponent hands.

    Compare this equity to pot odds to decide if calling is profitable.

    Args:
        hole_cards: Your hole cards, e.g., "AsKh" or "Jd9d"
        board: Community cards, e.g., "Js7s2c" or "" for preflop
        num_opponents: Number of opponents (1-4)

    Returns:
        Equity percentage
    """
    try:
        hole = parse_range(hole_cards)
        board_cards = Card.parse(board) if board else Card.parse("")

        strength = calculate_hand_strength(
            num_opponents + 1,
            hole,
            board_cards,
            2,
            5,
            Deck.STANDARD,
            (StandardHighHand,),
            sample_count=500,
        )

        equity = strength * 100
        street = "preflop" if not board else f"on {board}"

        return f"Equity: {equity:.1f}% ({hole_cards} {street} vs {num_opponents} opponent(s))"

    except Exception as e:
        logger.error(f"Equity calculation failed: {e}")
        return f"Could not calculate equity for {hole_cards}. Format: 'AsKh', board: 'Js7s2c'"


# Basic tools available to all agents
POKER_TOOLS = [
    calculate_pot_odds,
    get_position_info,
    calculate_equity,
]


def create_knowledge_tools(knowledge_base: KnowledgeBase) -> list[Callable]:
    """
    Create tools bound to a specific knowledge base.
    This allows each agent to look up opponent stats.

    Args:
        knowledge_base: The agent's knowledge base with opponent profiles

    Returns:
        List of tools for looking up opponent information
    """

    @function_tool
    def get_opponent_stats(player_name: str) -> str:
        """
        Look up statistics for an opponent.

        IMPORTANT: Statistics require at least 50 hands to be reliable.
        Do not exploit based on fewer than 50 hands - variance is too high!

        Args:
            player_name: Name of the opponent to look up

        Returns:
            Opponent statistics or message if unknown
        """
        from backend.domain.player.models import MIN_RELIABLE_SAMPLE_SIZE

        profile = knowledge_base.get_profile(player_name)

        if not profile or profile.statistics.hands_played == 0:
            return f"No data on {player_name}. Treat as unknown player - use GTO strategy."

        stats = profile.statistics
        confidence = profile.confidence

        # Add reliability warning
        if not stats.is_reliable:
            warning = f"""
⚠️ WARNING: Only {stats.hands_played} hands observed (minimum {MIN_RELIABLE_SAMPLE_SIZE} required)
These statistics are NOT reliable for exploitation!
Recommended: Play GTO strategy, do not make reads-based adjustments."""
        else:
            warning = f"✅ Sample size adequate ({stats.hands_played} hands) - stats can be used for exploitation."

        result = f"""Stats for {player_name} ({stats.hands_played} hands, {confidence} confidence):
{warning}

{stats.to_prompt_string()}

Tendencies: {", ".join(profile.tendencies) if profile.tendencies else "None identified"}"""

        return result

    @function_tool
    def list_known_opponents() -> str:
        """
        List all opponents we have data on.

        Note: At least 50 hands required for reliable exploitation.

        Returns:
            List of known opponents with sample sizes and reliability
        """
        from backend.domain.player.models import MIN_RELIABLE_SAMPLE_SIZE

        players = knowledge_base.list_players()

        if not players:
            return "No opponent data available. Playing GTO without reads."

        lines = [f"Known opponents (min {MIN_RELIABLE_SAMPLE_SIZE} hands for reliable stats):"]
        for pid in players:
            profile = knowledge_base.get_profile(pid)
            if profile:
                stats = profile.statistics
                hands = stats.hands_played
                reliable = "✅ Reliable" if stats.is_reliable else "⚠️ Unreliable"
                lines.append(f"- {pid}: {hands} hands - {reliable}")

        return "\n".join(lines)

    return [get_opponent_stats, list_known_opponents]
