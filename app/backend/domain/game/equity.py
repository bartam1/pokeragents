"""
Equity calculation utilities for EV tracking.

Calculates exact equity when hands are known (for showdown analysis).
Supports both heads-up and multi-way pots.
"""
import random

from pokerkit import Card as PKCard
from pokerkit import Deck, StandardHighHand

from backend.domain.game.models import Card
from backend.logging_config import get_logger

logger = get_logger(__name__)


def cards_to_pokerkit(cards: list[Card]) -> list[PKCard]:
    """Convert our Card objects to PokerKit Card objects."""
    result = []
    for card in cards:
        card_str = f"{card.rank}{card.suit}"
        result.extend(PKCard.parse(card_str))
    return result


def calculate_showdown_equity(
    hero_cards: list[Card],
    villain_cards: list[Card],
    board_cards: list[Card],
) -> float:
    """
    Calculate exact equity at showdown when both hands are known (heads-up).

    For complete boards (5 cards), this is deterministic.
    For incomplete boards, uses Monte Carlo simulation with known cards blocked.

    Args:
        hero_cards: Hero's hole cards (2 cards)
        villain_cards: Villain's hole cards (2 cards)
        board_cards: Community cards (0-5 cards)

    Returns:
        Hero's equity as a float between 0.0 and 1.0
    """
    # Use the multiway function with a single opponent
    return calculate_multiway_equity(hero_cards, [villain_cards], board_cards)


def calculate_multiway_equity(
    hero_cards: list[Card],
    opponent_hands: list[list[Card]],
    board_cards: list[Card],
) -> float:
    """
    Calculate hero's equity against multiple opponents at showdown.

    For complete boards (5 cards), this is deterministic.
    For incomplete boards, uses Monte Carlo simulation.

    Args:
        hero_cards: Hero's hole cards (2 cards)
        opponent_hands: List of opponent hole cards (each 2 cards)
        board_cards: Community cards (0-5 cards)

    Returns:
        Hero's equity as a float between 0.0 and 1.0
    """
    hero_pk = cards_to_pokerkit(hero_cards)
    opponents_pk = [cards_to_pokerkit(h) for h in opponent_hands]
    board_pk = cards_to_pokerkit(board_cards) if board_cards else []

    # If we have all 5 board cards, calculate deterministically
    if len(board_pk) == 5:
        return _calculate_multiway_deterministic(hero_pk, opponents_pk, board_pk)

    # Otherwise, use Monte Carlo with dead cards
    return _calculate_multiway_monte_carlo(hero_pk, opponents_pk, board_pk)


def _calculate_multiway_deterministic(
    hero_pk: list[PKCard],
    opponents_pk: list[list[PKCard]],
    board_pk: list[PKCard],
) -> float:
    """Calculate equity when all cards are known (river showdown) - multiway."""
    try:
        # Evaluate hero's hand
        hero_hand = StandardHighHand.from_game(hero_pk, board_pk)

        # Evaluate all opponent hands
        opponent_hands = [
            StandardHighHand.from_game(opp, board_pk) for opp in opponents_pk
        ]

        # Find the best opponent hand
        best_opponent = max(opponent_hands)

        # Compare hero vs best opponent
        if hero_hand > best_opponent:
            return 1.0
        elif hero_hand < best_opponent:
            return 0.0
        else:
            # Tie - count how many players tie for best
            tie_count = sum(1 for h in opponent_hands if h == hero_hand) + 1
            return 1.0 / tie_count

    except Exception as e:
        logger.error(f"Multiway deterministic equity calculation failed: {e}")
        return 0.5


def _calculate_multiway_monte_carlo(
    hero_pk: list[PKCard],
    opponents_pk: list[list[PKCard]],
    board_pk: list[PKCard],
    sample_count: int = 1000,
) -> float:
    """
    Calculate equity using Monte Carlo simulation for incomplete boards - multiway.

    This runs out the remaining board cards many times to estimate equity.
    """
    try:
        # Get all known cards (dead cards)
        dead_cards = set(hero_pk + board_pk)
        for opp in opponents_pk:
            dead_cards.update(opp)

        # Create deck minus dead cards
        remaining_deck = [c for c in Deck.STANDARD if c not in dead_cards]

        cards_needed = 5 - len(board_pk)
        wins = 0
        ties = 0.0

        for _ in range(sample_count):
            # Draw remaining board cards
            runout = random.sample(remaining_deck, cards_needed)
            full_board = board_pk + runout

            # Evaluate all hands
            hero_hand = StandardHighHand.from_game(hero_pk, full_board)
            opponent_hands = [
                StandardHighHand.from_game(opp, full_board) for opp in opponents_pk
            ]

            # Find best opponent
            best_opponent = max(opponent_hands)

            if hero_hand > best_opponent:
                wins += 1
            elif hero_hand == best_opponent:
                # Count ties
                tie_count = sum(1 for h in opponent_hands if h == hero_hand) + 1
                ties += 1.0 / tie_count

        # Equity = wins + tie equity
        equity = (wins + ties) / sample_count
        return equity

    except Exception as e:
        logger.error(f"Multiway Monte Carlo equity calculation failed: {e}")
        return 0.5


# Legacy heads-up functions for backwards compatibility
def _calculate_deterministic_equity(
    hero_pk: list[PKCard],
    villain_pk: list[PKCard],
    board_pk: list[PKCard],
) -> float:
    """Calculate equity when all cards are known (river showdown) - heads-up."""
    return _calculate_multiway_deterministic(hero_pk, [villain_pk], board_pk)


def _calculate_monte_carlo_equity(
    hero_pk: list[PKCard],
    villain_pk: list[PKCard],
    board_pk: list[PKCard],
    sample_count: int = 1000,
) -> float:
    """Calculate equity using Monte Carlo for incomplete boards - heads-up."""
    return _calculate_multiway_monte_carlo(hero_pk, [villain_pk], board_pk, sample_count)


def calculate_all_in_ev(
    hero_cards: list[Card],
    villain_cards: list[Card],
    board_cards: list[Card],
    pot_size: float,
    hero_invested: float,
    hero_won: bool,
) -> tuple[float, float, float]:
    """
    Calculate EV for an all-in situation at showdown.

    Args:
        hero_cards: Hero's hole cards
        villain_cards: Villain's hole cards
        board_cards: Community cards at the time of all-in
        pot_size: Total pot at showdown
        hero_invested: Amount hero put into the pot
        hero_won: Whether hero actually won the hand

    Returns:
        Tuple of (equity, ev_chips, actual_chips)
        - equity: Hero's equity (0.0 to 1.0)
        - ev_chips: Expected chip result based on equity
        - actual_chips: Actual chip result (+pot-invested if won, -invested if lost)
    """
    equity = calculate_showdown_equity(hero_cards, villain_cards, board_cards)

    # EV = (equity × pot) - invested
    ev_chips = (equity * pot_size) - hero_invested

    # Actual result
    if hero_won:
        actual_chips = pot_size - hero_invested  # Won the pot minus what we put in
    else:
        actual_chips = -hero_invested  # Lost our investment

    return equity, ev_chips, actual_chips
