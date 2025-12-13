"""
Tests for EV (Expected Value) calculations.

These tests verify that equity calculations and EV tracking work correctly
for various poker scenarios. No LLM calls required - pure computation tests.
"""

from backend.domain.game.equity import (
    calculate_all_in_ev,
    calculate_multiway_equity,
    calculate_showdown_equity,
    cards_to_pokerkit,
)
from backend.domain.game.models import Card, EVRecord


# Helper to create Card objects from strings like "Ah", "Kd"
def make_cards(card_strings: list[str]) -> list[Card]:
    """Create Card objects from a list of card strings."""
    return [Card.from_string(s) for s in card_strings]


class TestCardsToPokerkit:
    """Test card conversion to PokerKit format."""

    def test_convert_single_card(self):
        """Test converting a single card."""
        cards = make_cards(["Ah"])
        pk_cards = cards_to_pokerkit(cards)
        assert len(pk_cards) == 1
        # PokerKit uses verbose string repr, just check it contains the card notation
        assert "Ah" in str(pk_cards[0])

    def test_convert_hole_cards(self):
        """Test converting a pair of hole cards."""
        cards = make_cards(["As", "Kh"])
        pk_cards = cards_to_pokerkit(cards)
        assert len(pk_cards) == 2

    def test_convert_full_board(self):
        """Test converting a full 5-card board."""
        cards = make_cards(["Js", "7s", "2c", "Qd", "3h"])
        pk_cards = cards_to_pokerkit(cards)
        assert len(pk_cards) == 5


class TestShowdownEquity:
    """Test equity calculations at showdown with known hands."""

    def test_pocket_aces_vs_pocket_kings_preflop(self):
        """AA vs KK preflop - AA should have ~82% equity."""
        hero = make_cards(["As", "Ah"])
        villain = make_cards(["Ks", "Kh"])
        board = []

        equity = calculate_showdown_equity(hero, villain, board)

        # AA vs KK is roughly 82% for AA
        assert 0.78 < equity < 0.86, f"AA vs KK equity should be ~82%, got {equity * 100:.1f}%"

    def test_pocket_pair_vs_overcards_preflop(self):
        """77 vs AK preflop - classic coin flip, 77 has ~53% equity."""
        hero = make_cards(["7s", "7h"])
        villain = make_cards(["Ac", "Kd"])
        board = []

        equity = calculate_showdown_equity(hero, villain, board)

        # 77 vs AK is roughly 53% for 77
        assert 0.48 < equity < 0.58, f"77 vs AK equity should be ~53%, got {equity * 100:.1f}%"

    def test_set_vs_top_pair_on_flop(self):
        """Set vs top pair on flop - set should have ~90%+ equity."""
        hero = make_cards(["7d", "7c"])  # Set of 7s
        villain = make_cards(["Kc", "8s"])  # Top pair
        board = make_cards(["3s", "7s", "8d"])  # 7 on flop

        equity = calculate_showdown_equity(hero, villain, board)

        # Set vs top pair is usually 85-95%
        assert equity > 0.85, f"Set vs top pair should be 85%+, got {equity * 100:.1f}%"

    def test_flush_draw_with_overcards_vs_pair_on_flop(self):
        """Flush draw + overcards vs made pair on flop - combo draw has ~50-55% equity."""
        hero = make_cards(["Qs", "Js"])  # Flush draw + two overcards
        villain = make_cards(["Ah", "8c"])  # Pair of 8s
        board = make_cards(["8s", "5s", "2d"])

        equity = calculate_showdown_equity(hero, villain, board)

        # QsJs has flush draw (9 outs) + overcard outs = combo draw ~50-55%
        assert 0.45 < equity < 0.60, f"Combo draw equity should be ~50-55%, got {equity * 100:.1f}%"

    def test_rivered_flush_wins(self):
        """Flush on river beats two pair - deterministic 100% equity."""
        hero = make_cards(["Qs", "Js"])  # Flush
        villain = make_cards(["Ah", "8c"])  # Two pair
        board = make_cards(["8s", "5s", "2d", "Ac", "9s"])  # River completes flush

        equity = calculate_showdown_equity(hero, villain, board)

        # Hero has flush, villain has two pair - hero wins
        assert equity == 1.0, f"Flush should beat two pair, got {equity * 100:.1f}%"

    def test_better_two_pair_wins(self):
        """Higher two pair beats lower two pair on river."""
        hero = make_cards(["Ah", "Kc"])  # Aces and Kings
        villain = make_cards(["Qd", "Jh"])  # Queens and Jacks
        board = make_cards(["Ad", "Kh", "Qc", "Js", "2c"])

        equity = calculate_showdown_equity(hero, villain, board)

        # AA-KK beats QQ-JJ
        assert equity == 1.0, f"Higher two pair should win, got {equity * 100:.1f}%"

    def test_chopped_pot(self):
        """Same hand on board splits the pot - 50% equity."""
        hero = make_cards(["2h", "3c"])  # Low cards
        villain = make_cards(["4d", "5s"])  # Low cards
        board = make_cards(["As", "Ad", "Ah", "Kc", "Kd"])  # Board plays

        equity = calculate_showdown_equity(hero, villain, board)

        # Both play the board (AAA-KK) - chop
        assert equity == 0.5, f"Chopped pot should be 50%, got {equity * 100:.1f}%"

    def test_dominated_ace_preflop(self):
        """AK vs A7 - AK dominates with ~72% equity."""
        hero = make_cards(["Ac", "Kd"])
        villain = make_cards(["Ah", "7s"])
        board = []

        equity = calculate_showdown_equity(hero, villain, board)

        # AK vs A7 is roughly 72% for AK
        assert 0.68 < equity < 0.78, f"AK vs A7 should be ~72%, got {equity * 100:.1f}%"


class TestEVRecord:
    """Test the EVRecord dataclass and calculations."""

    def test_winning_with_positive_ev(self):
        """Winning a hand you were favorite in should have positive EV."""
        record = EVRecord(
            hand_number=1,
            player_id="agent_d",
            equity=0.85,  # 85% to win
            pot_size=1000,
            amount_invested=500,
            ev_chips=350,  # (0.85 * 1000) - 500 = 350
            actual_chips=500,  # Won pot: 1000 - 500 = 500
        )

        assert record.ev_chips == 350
        assert record.actual_chips == 500
        assert record.variance == 150  # Ran above EV

    def test_losing_with_positive_ev(self):
        """Losing a hand you were favorite in (bad beat) - negative luck factor."""
        record = EVRecord(
            hand_number=1,
            player_id="agent_d",
            equity=0.85,  # 85% to win
            pot_size=1000,
            amount_invested=500,
            ev_chips=350,  # (0.85 * 1000) - 500 = 350
            actual_chips=-500,  # Lost the hand
        )

        assert record.ev_chips == 350
        assert record.actual_chips == -500
        assert record.variance == -850  # Ran way below EV (bad beat)

    def test_winning_as_underdog(self):
        """Winning as underdog (suckout) - very positive luck factor."""
        record = EVRecord(
            hand_number=1,
            player_id="agent_e",
            equity=0.20,  # 20% underdog
            pot_size=1000,
            amount_invested=500,
            ev_chips=-300,  # (0.20 * 1000) - 500 = -300
            actual_chips=500,  # Won anyway!
        )

        assert record.ev_chips == -300
        assert record.actual_chips == 500
        assert record.variance == 800  # Major suckout

    def test_to_dict_serialization(self):
        """Test EVRecord serializes to dict correctly."""
        record = EVRecord(
            hand_number=5,
            player_id="agent_d",
            equity=0.75,
            pot_size=500,
            amount_invested=200,
            ev_chips=175,
            actual_chips=300,
        )

        d = record.to_dict()

        assert d["hand_number"] == 5
        assert d["player_id"] == "agent_d"
        assert d["equity"] == 0.75
        assert d["pot_size"] == 500
        assert d["amount_invested"] == 200
        assert d["ev_chips"] == 175
        assert d["actual_chips"] == 300
        assert d["variance"] == 125
        assert d["ev_adjusted"] == 175  # Same as ev_chips for single record

    def test_chop_pot_ev(self):
        """Test EV calculation when pot is chopped (50% equity)."""
        # Both players put in 500, pot is 1000, they chop
        record = EVRecord(
            hand_number=1,
            player_id="agent_d",
            equity=0.5,  # Chop
            pot_size=1000,
            amount_invested=500,
            ev_chips=0,  # (0.5 * 1000) - 500 = 0
            actual_chips=0,  # Got back exactly what was put in
        )

        assert record.ev_chips == 0
        assert record.actual_chips == 0
        assert record.variance == 0  # Neutral - got what was expected
        assert record.ev_adjusted == 0  # EV-adjusted equals ev_chips

    def test_zero_equity_all_in(self):
        """Test when player has 0% equity (drawing dead)."""
        record = EVRecord(
            hand_number=1,
            player_id="agent_e",
            equity=0.0,  # Drawing dead
            pot_size=1000,
            amount_invested=500,
            ev_chips=-500,  # (0.0 * 1000) - 500 = -500
            actual_chips=-500,  # Lost
        )

        assert record.ev_chips == -500
        assert record.variance == 0  # No luck involved, expected to lose
        assert record.ev_adjusted == -500  # EV-adjusted equals ev_chips


class TestCalculateAllInEV:
    """Test the all-in EV calculation helper."""

    def test_all_in_winner(self):
        """Test EV calculation when hero wins all-in."""
        hero = make_cards(["As", "Ah"])
        villain = make_cards(["Ks", "Kh"])
        board = make_cards(["2c", "5d", "7h", "Jc", "3s"])  # Blanks

        equity, ev_chips, actual_chips = calculate_all_in_ev(
            hero_cards=hero,
            villain_cards=villain,
            board_cards=board,
            pot_size=1000,
            hero_invested=500,
            hero_won=True,
        )

        # AA vs KK on blank board - AA wins
        assert equity == 1.0
        assert ev_chips == 500  # (1.0 * 1000) - 500
        assert actual_chips == 500  # Won pot minus invested

    def test_all_in_loser(self):
        """Test EV calculation when hero loses all-in."""
        hero = make_cards(["Ks", "Kh"])
        villain = make_cards(["As", "Ah"])
        board = make_cards(["2c", "5d", "7h", "Jc", "3s"])  # Blanks

        equity, ev_chips, actual_chips = calculate_all_in_ev(
            hero_cards=hero,
            villain_cards=villain,
            board_cards=board,
            pot_size=1000,
            hero_invested=500,
            hero_won=False,
        )

        # KK vs AA on blank board - KK loses
        assert equity == 0.0
        assert ev_chips == -500  # (0.0 * 1000) - 500
        assert actual_chips == -500  # Lost investment


class TestMultiwayEquity:
    """Test equity calculations with 3+ players."""

    def test_three_way_aces_vs_kings_vs_queens_river(self):
        """AA vs KK vs QQ on blank river - AA wins 100%."""
        hero = make_cards(["As", "Ah"])
        opponent1 = make_cards(["Ks", "Kh"])
        opponent2 = make_cards(["Qs", "Qh"])
        board = make_cards(["2c", "5d", "7h", "Jc", "3s"])

        equity = calculate_multiway_equity(hero, [opponent1, opponent2], board)

        # AA beats both KK and QQ
        assert equity == 1.0, f"AA should win 100% vs KK and QQ, got {equity * 100:.1f}%"

    def test_three_way_middle_pair_loses(self):
        """KK vs AA vs QQ on blank river - KK loses."""
        hero = make_cards(["Ks", "Kh"])  # Middle pair
        opponent1 = make_cards(["As", "Ah"])  # Best
        opponent2 = make_cards(["Qs", "Qh"])  # Worst
        board = make_cards(["2c", "5d", "7h", "Jc", "3s"])

        equity = calculate_multiway_equity(hero, [opponent1, opponent2], board)

        # KK loses to AA
        assert equity == 0.0, f"KK should lose to AA, got {equity * 100:.1f}%"

    def test_three_way_preflop_aces_dominate(self):
        """AA vs KK vs QQ preflop - AA should have ~73% equity."""
        hero = make_cards(["As", "Ah"])
        opponent1 = make_cards(["Ks", "Kh"])
        opponent2 = make_cards(["Qs", "Qh"])
        board = []

        equity = calculate_multiway_equity(hero, [opponent1, opponent2], board)

        # AA vs KK vs QQ preflop - AA has roughly 65-75% equity (Monte Carlo variance)
        assert 0.60 < equity < 0.80, f"AA vs KK vs QQ should be ~65-75%, got {equity * 100:.1f}%"

    def test_three_way_chop(self):
        """All three players tie - each gets 1/3."""
        hero = make_cards(["2h", "3c"])
        opponent1 = make_cards(["4d", "5s"])
        opponent2 = make_cards(["6h", "7c"])
        board = make_cards(["As", "Ad", "Ah", "Kc", "Kd"])  # Board plays

        equity = calculate_multiway_equity(hero, [opponent1, opponent2], board)

        # All play the board - 3-way chop
        assert abs(equity - 1 / 3) < 0.01, f"3-way chop should be 33.3%, got {equity * 100:.1f}%"

    def test_four_way_pot_winner(self):
        """4-way pot, one clear winner."""
        hero = make_cards(["As", "Ah"])  # Best
        opponent1 = make_cards(["Ks", "Kh"])
        opponent2 = make_cards(["Qs", "Qh"])
        opponent3 = make_cards(["Js", "Jh"])
        board = make_cards(["2c", "5d", "7h", "Tc", "3s"])

        equity = calculate_multiway_equity(hero, [opponent1, opponent2, opponent3], board)

        # AA beats everyone
        assert equity == 1.0, f"AA should win 4-way pot, got {equity * 100:.1f}%"


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_same_hand_different_suits(self):
        """Two players with identical hands (different suits) should chop."""
        hero = make_cards(["Ac", "Kc"])
        villain = make_cards(["Ad", "Kd"])
        board = make_cards(["2h", "5s", "7c", "Jh", "Qs"])

        equity = calculate_showdown_equity(hero, villain, board)

        # Same hand - chop
        assert equity == 0.5

    def test_preflop_all_in_empty_board(self):
        """Preflop all-in with empty board list should work."""
        hero = make_cards(["As", "Ah"])
        villain = make_cards(["Ks", "Kh"])
        board = []  # Empty board

        equity = calculate_showdown_equity(hero, villain, board)

        # AA vs KK preflop ~82%
        assert 0.78 < equity < 0.86

    def test_flop_all_in_three_cards(self):
        """All-in on flop with 3 board cards."""
        hero = make_cards(["As", "Kh"])
        villain = make_cards(["Qd", "Qc"])
        board = make_cards(["Qs", "7c", "2h"])  # Villain flopped set

        equity = calculate_showdown_equity(hero, villain, board)

        # AK vs set of Q's - AK needs runner-runner or a lucky runout
        assert equity < 0.15, f"AK vs set should be <15%, got {equity * 100:.1f}%"

    def test_turn_all_in_four_cards(self):
        """All-in on turn with 4 board cards - flush draw vs trips."""
        hero = make_cards(["Ah", "Kh"])  # Flush draw (only 2 hearts on board)
        villain = make_cards(["Jd", "Jc"])  # Set of jacks
        board = make_cards(["2h", "7s", "Jh", "3c"])  # Only 2 hearts, hero needs river

        equity = calculate_showdown_equity(hero, villain, board)

        # Hero has 9 flush outs + maybe some straight outs ~20-25%
        # But can also hit A or K for two pair... actually more complex
        # Let's just verify it's reasonable (hero is behind but has outs)
        assert 0.15 < equity < 0.35, (
            f"Flush draw vs trips should be 15-35%, got {equity * 100:.1f}%"
        )

    def test_multiway_with_empty_board(self):
        """3-way preflop all-in with no board cards."""
        hero = make_cards(["Ah", "Ac"])
        opponent1 = make_cards(["Kh", "Kc"])
        opponent2 = make_cards(["Qh", "Qc"])
        board = []

        equity = calculate_multiway_equity(hero, [opponent1, opponent2], board)

        # AA vs KK vs QQ - AA should have ~70-75%
        assert 0.65 < equity < 0.80

    def test_straight_vs_flush(self):
        """Flush beats straight."""
        hero = make_cards(["9h", "Th"])  # Flush
        villain = make_cards(["Jc", "Ts"])  # Straight
        board = make_cards(["2h", "5h", "7h", "8d", "9c"])

        equity = calculate_showdown_equity(hero, villain, board)

        # Flush beats straight
        assert equity == 1.0

    def test_full_house_vs_flush(self):
        """Full house beats flush."""
        hero = make_cards(["7d", "7c"])  # Full house 7s full of 5s
        villain = make_cards(["Ah", "2h"])  # Flush
        board = make_cards(["5h", "5d", "7h", "Kh", "3h"])

        equity = calculate_showdown_equity(hero, villain, board)

        # Full house beats flush
        assert equity == 1.0
