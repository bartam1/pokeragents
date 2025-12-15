"""
Statistics Tracker - Observes gameplay and updates player profiles.

This is how Agent E learns opponent tendencies during play.
"""

from backend.domain.game.models import Action, ActionType, HandResult, Street, StructuredGameState
from backend.domain.player.models import KnowledgeBase
from backend.logging_config import get_logger

logger = get_logger(__name__)


class StatisticsTracker:
    """
    Tracks player actions and updates their statistics profiles.

    This tracker observes actions during gameplay and updates
    the relevant statistics in the knowledge base.
    """

    def __init__(self, knowledge_base: KnowledgeBase):
        """
        Initialize the tracker with a knowledge base.

        Args:
            knowledge_base: The knowledge base to update with observations.
        """
        self.knowledge_base = knowledge_base

        # Track state per hand for each player
        self._hand_state: dict[str, dict] = {}

    def start_hand(self, player_ids: list[str]) -> None:
        """
        Start tracking a new hand.

        Args:
            player_ids: List of player IDs in the hand.
        """
        for pid in player_ids:
            self._hand_state[pid] = {
                "saw_flop": False,
                "vpip": False,
                "pfr": False,
                "limped": False,
                "three_bet_opportunity": False,
                "three_bet": False,
                "fold_to_3bet_opportunity": False,
                "folded_to_3bet": False,
                "was_preflop_aggressor": False,
                "cbet_flop_opportunity": False,
                "cbet_flop": False,
                "cbet_turn_opportunity": False,
                "cbet_turn": False,
                "bets": 0,
                "raises": 0,
                "calls": 0,
            }

    def observe_action(
        self,
        player_id: str,
        player_name: str,
        action: Action,
        game_state: StructuredGameState,
    ) -> None:
        """
        Observe a player's action and update tracking.

        Args:
            player_id: ID of the acting player
            player_name: Name of the acting player
            action: The action taken
            game_state: Current game state
        """
        # Ensure profile exists
        profile = self.knowledge_base.get_or_create_profile(player_id, player_name)

        # Get or create hand state
        if player_id not in self._hand_state:
            self._hand_state[player_id] = {
                "saw_flop": False,
                "vpip": False,
                "pfr": False,
                "limped": False,
                "three_bet_opportunity": False,
                "three_bet": False,
                "fold_to_3bet_opportunity": False,
                "folded_to_3bet": False,
                "was_preflop_aggressor": False,
                "cbet_flop_opportunity": False,
                "cbet_flop": False,
                "cbet_turn_opportunity": False,
                "cbet_turn": False,
                "bets": 0,
                "raises": 0,
                "calls": 0,
            }

        hand_state = self._hand_state[player_id]
        stats = profile.statistics
        street = game_state.street

        # Track action type
        if action.type == ActionType.CALL:
            hand_state["calls"] += 1
            stats._calls += 1

        elif action.type in (ActionType.BET, ActionType.RAISE, ActionType.ALL_IN):
            hand_state["bets"] += 1
            stats._bets_and_raises += 1

            # Track bet/raise sizing as % of current pot (pre-action)
            if action.amount is not None:
                pot_for_ratio = max(game_state.pot, 1.0)
                sizing_pct = (action.amount / pot_for_ratio) * 100
                if action.type == ActionType.BET:
                    stats._bet_sizing_total += sizing_pct
                    stats._bet_sizing_count += 1
                else:
                    stats._raise_sizing_total += sizing_pct
                    stats._raise_sizing_count += 1

        # Preflop tracking
        if street == Street.PREFLOP:
            self._track_preflop(player_id, action, game_state, hand_state, stats)

        # Postflop tracking
        elif street == Street.FLOP:
            self._track_flop(player_id, action, game_state, hand_state, stats)

        elif street == Street.TURN:
            self._track_turn(player_id, action, game_state, hand_state, stats)

        elif street == Street.RIVER:
            self._track_river(player_id, action, game_state, hand_state, stats)

        # Recalculate percentages
        stats.recalculate()

    def _track_preflop(
        self,
        player_id: str,
        action: Action,
        game_state: StructuredGameState,
        hand_state: dict,
        stats,
    ) -> None:
        """Track preflop action."""
        # VPIP - any voluntary money in pot
        if action.type in (ActionType.CALL, ActionType.BET, ActionType.RAISE, ActionType.ALL_IN):
            if not hand_state["vpip"]:
                hand_state["vpip"] = True
                stats._vpip_hands += 1

        # PFR - preflop raise
        if action.type in (ActionType.RAISE, ActionType.BET, ActionType.ALL_IN):
            if not hand_state["pfr"]:
                hand_state["pfr"] = True
                stats._pfr_hands += 1
                hand_state["was_preflop_aggressor"] = True

        # Limp detection (call when action is unopened)
        # Simplified: if it's a call and current bet is just the big blind
        if action.type == ActionType.CALL:
            if game_state.current_bet <= game_state.big_blind * 1.5:
                if not hand_state["limped"]:
                    hand_state["limped"] = True
                    stats._limp_hands += 1

        # 3-bet / fold-to-3bet tracking
        preflop_raises = [
            a
            for a in game_state.action_history
            if a.get("street") == "preflop" and a.get("action") in ("raise", "bet", "all_in")
        ]
        num_raises = len(preflop_raises)

        # 3-bet opportunity: facing exactly 1 raise (the open), you can 3-bet
        if num_raises == 1 and not hand_state["three_bet_opportunity"]:
            hand_state["three_bet_opportunity"] = True
            stats._three_bet_opportunities += 1

            if action.type in (ActionType.RAISE, ActionType.BET, ActionType.ALL_IN):
                hand_state["three_bet"] = True
                stats._three_bet_count += 1

        # Fold to 3-bet: you opened (was_preflop_aggressor) and now face a re-raise
        if hand_state["was_preflop_aggressor"] and num_raises >= 2:
            if not hand_state["fold_to_3bet_opportunity"]:
                hand_state["fold_to_3bet_opportunity"] = True
                stats._fold_to_3bet_opportunities += 1

            if action.type == ActionType.FOLD:
                if not hand_state["folded_to_3bet"]:
                    hand_state["folded_to_3bet"] = True
                    stats._fold_to_3bet_count += 1

    def _track_flop(
        self,
        player_id: str,
        action: Action,
        game_state: StructuredGameState,
        hand_state: dict,
        stats,
    ) -> None:
        """Track flop action."""
        # Only count seeing flop once per hand per player
        if not hand_state["saw_flop"]:
            hand_state["saw_flop"] = True
            stats._saw_flop_count += 1

        # C-bet opportunity (was preflop aggressor, first to act on flop)
        if hand_state["was_preflop_aggressor"]:
            if not hand_state["cbet_flop_opportunity"]:
                hand_state["cbet_flop_opportunity"] = True
                stats._cbet_flop_opportunities += 1

                if action.type in (ActionType.BET, ActionType.RAISE, ActionType.ALL_IN):
                    hand_state["cbet_flop"] = True
                    stats._cbet_flop_count += 1

    def _track_turn(
        self,
        player_id: str,
        action: Action,
        game_state: StructuredGameState,
        hand_state: dict,
        stats,
    ) -> None:
        """Track turn action."""
        # C-bet turn opportunity (c-bet flop and now on turn)
        if hand_state.get("cbet_flop"):
            if not hand_state["cbet_turn_opportunity"]:
                hand_state["cbet_turn_opportunity"] = True
                stats._cbet_turn_opportunities += 1

                if action.type in (ActionType.BET, ActionType.RAISE, ActionType.ALL_IN):
                    hand_state["cbet_turn"] = True
                    stats._cbet_turn_count += 1

    def _track_river(
        self,
        player_id: str,
        action: Action,
        game_state: StructuredGameState,
        hand_state: dict,
        stats,
    ) -> None:
        """Track river action."""
        # C-bet river opportunity
        if hand_state.get("cbet_turn"):
            if not hand_state.get("cbet_river_opportunity"):
                hand_state["cbet_river_opportunity"] = True
                stats._cbet_river_opportunities += 1

                if action.type in (ActionType.BET, ActionType.RAISE, ActionType.ALL_IN):
                    hand_state["cbet_river"] = True
                    stats._cbet_river_count += 1

        # River aggression (per action, same style as overall aggression)
        if action.type in (ActionType.BET, ActionType.RAISE, ActionType.ALL_IN):
            stats._river_bets_and_raises += 1
        elif action.type == ActionType.CALL:
            stats._river_calls += 1

    def end_hand(
        self,
        player_ids: list[str],
        hand_result: HandResult,
    ) -> None:
        """
        End tracking for a hand.

        Args:
            player_ids: Players in the hand (also used as names)
            hand_result: The completed hand result from PokerKit
        """
        # Compute showdown participation from shown_hands (keyed by seat index)
        went_to_showdown = {
            player_ids[seat]: seat in hand_result.shown_hands for seat in range(len(player_ids))
        }
        won_at_showdown = {
            player_ids[seat]: seat in hand_result.shown_hands and seat in hand_result.winners
            for seat in range(len(player_ids))
        }

        for pid in player_ids:
            # Use get_or_create to ensure ALL players get hands_played incremented,
            # even if they never took an observable action (e.g., eliminated by blinds)
            profile = self.knowledge_base.get_or_create_profile(pid, pid)

            stats = profile.statistics
            stats.hands_played += 1

            # Track showdown stats
            hand_state = self._hand_state.get(pid, {})
            if hand_state.get("saw_flop") and went_to_showdown.get(pid, False):
                stats._wtsd_count += 1
                if won_at_showdown.get(pid, False):
                    stats._wsd_count += 1

            stats.recalculate()

        # Clear hand state
        self._hand_state.clear()
