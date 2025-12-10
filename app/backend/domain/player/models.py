"""
Player statistics and profile models.

These models track poker statistics for each player, enabling
the Exploit Scout agent to identify tendencies and leaks.
"""
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path


# Minimum hands required for statistics to be considered reliable for exploitation
MIN_RELIABLE_SAMPLE_SIZE = 50


@dataclass
class PlayerStatistics:
    """
    Core poker statistics tracked for each player.
    These are the key metrics for exploitation.
    """

    # Sample size
    hands_played: int = 0

    # Preflop tendencies
    vpip: float = 0.0  # Voluntarily Put $ In Pot %
    pfr: float = 0.0  # Pre-Flop Raise %
    limp_frequency: float = 0.0  # Open limp %
    three_bet_pct: float = 0.0  # 3-bet %
    fold_to_three_bet: float = 0.0  # Fold to 3-bet %

    # Postflop tendencies
    cbet_flop_pct: float = 0.0  # C-bet on flop %
    cbet_turn_pct: float = 0.0  # Turn barrel % (c-bet turn after c-bet flop)
    cbet_river_pct: float = 0.0  # River barrel %

    # Aggression metrics
    aggression_factor: float = 0.0  # (Bet + Raise) / Call
    river_aggression: float = 0.0  # River aggression specifically

    # Showdown metrics
    wtsd: float = 0.0  # Went To ShowDown % (when saw flop)
    wsd: float = 0.0  # Won at ShowDown %

    # Sizing patterns
    avg_bet_sizing: float = 0.0  # As % of pot
    avg_raise_sizing: float = 0.0

    # Raw counters for incremental updates
    _vpip_hands: int = 0
    _pfr_hands: int = 0
    _limp_hands: int = 0
    _three_bet_opportunities: int = 0
    _three_bet_count: int = 0
    _fold_to_3bet_opportunities: int = 0
    _fold_to_3bet_count: int = 0
    _cbet_flop_opportunities: int = 0
    _cbet_flop_count: int = 0
    _cbet_turn_opportunities: int = 0
    _cbet_turn_count: int = 0
    _cbet_river_opportunities: int = 0
    _cbet_river_count: int = 0
    _bets_and_raises: int = 0
    _calls: int = 0
    _saw_flop_count: int = 0
    _wtsd_count: int = 0
    _wsd_count: int = 0
    _bet_sizing_total: float = 0.0
    _bet_sizing_count: int = 0
    _raise_sizing_total: float = 0.0
    _raise_sizing_count: int = 0
    _river_bets_and_raises: int = 0
    _river_calls: int = 0

    def recalculate(self) -> None:
        """Recalculate percentages from raw counters."""
        if self.hands_played > 0:
            self.vpip = (self._vpip_hands / self.hands_played) * 100
            self.pfr = (self._pfr_hands / self.hands_played) * 100
            self.limp_frequency = (self._limp_hands / self.hands_played) * 100

        if self._three_bet_opportunities > 0:
            self.three_bet_pct = (
                self._three_bet_count / self._three_bet_opportunities
            ) * 100

        if self._fold_to_3bet_opportunities > 0:
            self.fold_to_three_bet = (
                self._fold_to_3bet_count / self._fold_to_3bet_opportunities
            ) * 100

        if self._cbet_flop_opportunities > 0:
            self.cbet_flop_pct = (
                self._cbet_flop_count / self._cbet_flop_opportunities
            ) * 100

        if self._cbet_turn_opportunities > 0:
            self.cbet_turn_pct = (
                self._cbet_turn_count / self._cbet_turn_opportunities
            ) * 100

        if self._cbet_river_opportunities > 0:
            self.cbet_river_pct = (
                self._cbet_river_count / self._cbet_river_opportunities
            ) * 100

        # Aggression Factor = (Bets + Raises) / Calls
        # If no calls but has bets/raises, cap at 10.0 (very aggressive)
        # If no bets/raises and no calls, leave at 0.0
        if self._calls > 0:
            self.aggression_factor = self._bets_and_raises / self._calls
        elif self._bets_and_raises > 0:
            # No calls but has aggression = extremely aggressive
            self.aggression_factor = 10.0  # Cap at 10 to represent "infinitely aggressive"

        if self._saw_flop_count > 0:
            self.wtsd = (self._wtsd_count / self._saw_flop_count) * 100

        if self._wtsd_count > 0:
            self.wsd = (self._wsd_count / self._wtsd_count) * 100

        if self._bet_sizing_count > 0:
            self.avg_bet_sizing = self._bet_sizing_total / self._bet_sizing_count

        if self._raise_sizing_count > 0:
            self.avg_raise_sizing = (
                self._raise_sizing_total / self._raise_sizing_count
            )

        # River Aggression - same logic as overall aggression
        if self._river_calls > 0:
            self.river_aggression = self._river_bets_and_raises / self._river_calls
        elif self._river_bets_and_raises > 0:
            self.river_aggression = 10.0  # Cap at 10

    def accumulate(self, other: "PlayerStatistics") -> None:
        """Add raw counters from another stats object (for calibration accumulation)."""
        self.hands_played += other.hands_played
        self._vpip_hands += other._vpip_hands
        self._pfr_hands += other._pfr_hands
        self._limp_hands += other._limp_hands
        self._three_bet_opportunities += other._three_bet_opportunities
        self._three_bet_count += other._three_bet_count
        self._fold_to_3bet_opportunities += other._fold_to_3bet_opportunities
        self._fold_to_3bet_count += other._fold_to_3bet_count
        self._cbet_flop_opportunities += other._cbet_flop_opportunities
        self._cbet_flop_count += other._cbet_flop_count
        self._cbet_turn_opportunities += other._cbet_turn_opportunities
        self._cbet_turn_count += other._cbet_turn_count
        self._cbet_river_opportunities += other._cbet_river_opportunities
        self._cbet_river_count += other._cbet_river_count
        self._bets_and_raises += other._bets_and_raises
        self._calls += other._calls
        self._saw_flop_count += other._saw_flop_count
        self._wtsd_count += other._wtsd_count
        self._wsd_count += other._wsd_count
        self._bet_sizing_total += other._bet_sizing_total
        self._bet_sizing_count += other._bet_sizing_count
        self._raise_sizing_total += other._raise_sizing_total
        self._raise_sizing_count += other._raise_sizing_count
        self._river_bets_and_raises += other._river_bets_and_raises
        self._river_calls += other._river_calls
        # Recalculate percentages from accumulated totals
        self.recalculate()

    @property
    def is_reliable(self) -> bool:
        """
        Check if statistics are based on enough hands to be reliable.
        
        Poker statistics require at least 50 hands to be meaningful.
        Below this threshold, variance is too high for exploitation.
        """
        return self.hands_played >= MIN_RELIABLE_SAMPLE_SIZE

    @property
    def reliability_note(self) -> str:
        """Get a note about the reliability of these statistics."""
        if self.hands_played < 20:
            return "⚠️ VERY LOW SAMPLE - Do NOT use for exploitation"
        elif self.hands_played < MIN_RELIABLE_SAMPLE_SIZE:
            return f"⚠️ LOW SAMPLE ({self.hands_played} hands) - Stats unreliable, play GTO"
        elif self.hands_played < 100:
            return f"📊 Moderate sample ({self.hands_played} hands) - Use with caution"
        else:
            return f"✅ Good sample ({self.hands_played} hands) - Stats reliable"

    def to_prompt_string(self) -> str:
        """Format stats for LLM prompt."""
        # Don't show misleading percentages with very small samples
        if self.hands_played < 20:
            return f"""Hands: {self.hands_played}
⚠️ INSUFFICIENT DATA - Statistics not meaningful yet.
DO NOT make reads or exploits based on this player.
Play GTO (Game Theory Optimal) against them."""
        
        reliability = self.reliability_note
        
        return f"""
Hands: {self.hands_played} - {reliability}
VPIP/PFR: {self.vpip:.1f}% / {self.pfr:.1f}%
Limp: {self.limp_frequency:.1f}%
3-Bet: {self.three_bet_pct:.1f}%
Fold to 3-Bet: {self.fold_to_three_bet:.1f}%
C-Bet: Flop {self.cbet_flop_pct:.1f}% / Turn {self.cbet_turn_pct:.1f}% / River {self.cbet_river_pct:.1f}%
Aggression Factor: {self.aggression_factor:.2f} (River: {self.river_aggression:.2f})
Avg Sizing: Bet {self.avg_bet_sizing:.0f}% pot / Raise {self.avg_raise_sizing:.0f}% pot
WTSD: {self.wtsd:.1f}%
WSD: {self.wsd:.1f}%
""".strip()


@dataclass
class PlayerProfile:
    """
    Complete profile for a player including stats and tendencies.
    """

    player_id: str
    name: str
    statistics: PlayerStatistics = field(default_factory=PlayerStatistics)

    # Qualitative observations (can be seeded or learned)
    tendencies: list[str] = field(default_factory=list)
    # e.g., ["folds to river aggression", "overbets bluffs", "limp-raises with premiums"]

    @property
    def confidence(self) -> str:
        """Confidence level based on sample size."""
        if self.statistics.hands_played < 20:
            return "low"
        elif self.statistics.hands_played < 100:
            return "medium"
        elif self.statistics.hands_played < 500:
            return "high"
        return "very_high"

    @property
    def sample_size(self) -> int:
        """Number of hands in the sample."""
        return self.statistics.hands_played


@dataclass
class KnowledgeBase:
    """
    Knowledge base containing profiles of all known players.

    - Agent D has this pre-populated with historical data
    - Agent E starts empty and learns during play
    """

    profiles: dict[str, PlayerProfile] = field(default_factory=dict)

    def get_profile(self, player_id: str) -> PlayerProfile | None:
        """Get profile for a player, or None if unknown."""
        return self.profiles.get(player_id)

    def get_or_create_profile(self, player_id: str, name: str = "") -> PlayerProfile:
        """Get existing profile or create a new empty one."""
        if player_id not in self.profiles:
            self.profiles[player_id] = PlayerProfile(
                player_id=player_id,
                name=name or player_id,
            )
        return self.profiles[player_id]

    def update_profile(self, profile: PlayerProfile) -> None:
        """Update or add a profile."""
        self.profiles[profile.player_id] = profile

    def has_profile(self, player_id: str) -> bool:
        """Check if we have data on a player."""
        return player_id in self.profiles

    def get_total_hands_observed(self) -> int:
        """Get total hands observed across all players."""
        return sum(p.statistics.hands_played for p in self.profiles.values())

    def list_players(self) -> list[str]:
        """Get list of all known player IDs."""
        return list(self.profiles.keys())

    def save_to_file(self, filepath: str) -> None:
        """Save knowledge base to JSON file."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "profiles": {
                player_id: {
                    "player_id": profile.player_id,
                    "name": profile.name,
                    "statistics": asdict(profile.statistics),
                    "tendencies": profile.tendencies,
                }
                for player_id, profile in self.profiles.items()
            }
        }
        
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load_from_file(cls, filepath: str) -> "KnowledgeBase":
        """Load knowledge base from JSON file, or return empty if not exists."""
        path = Path(filepath)
        if not path.exists():
            return cls()
        
        with open(path, "r") as f:
            data = json.load(f)
        
        kb = cls()
        for player_id, profile_data in data.get("profiles", {}).items():
            stats = PlayerStatistics(**profile_data["statistics"])
            profile = PlayerProfile(
                player_id=profile_data["player_id"],
                name=profile_data["name"],
                statistics=stats,
                tendencies=profile_data.get("tendencies", []),
            )
            kb.profiles[player_id] = profile
        
        return kb

    def merge_with(self, other: "KnowledgeBase") -> None:
        """Merge another knowledge base into this one, updating existing profiles."""
        for player_id, profile in other.profiles.items():
            if player_id in self.profiles:
                # Update existing - keep the one with more hands
                existing = self.profiles[player_id]
                if profile.statistics.hands_played > existing.statistics.hands_played:
                    self.profiles[player_id] = profile
            else:
                self.profiles[player_id] = profile

    def accumulate_with(self, other: "KnowledgeBase") -> None:
        """Accumulate stats from another knowledge base (adds counters instead of replacing)."""
        for player_id, profile in other.profiles.items():
            if player_id in self.profiles:
                # Accumulate stats into existing profile
                self.profiles[player_id].statistics.accumulate(profile.statistics)
                # Merge tendencies
                for tendency in profile.tendencies:
                    if tendency not in self.profiles[player_id].tendencies:
                        self.profiles[player_id].tendencies.append(tendency)
            else:
                # New player - just add the profile
                self.profiles[player_id] = profile


# Pre-built statistics for the POC experiment
# These represent historical data that Agent D will have access to

SHARED_KNOWLEDGE_STATS = {
    "agent_a": PlayerStatistics(
        hands_played=500,
        vpip=35.0,
        pfr=28.0,
        limp_frequency=5.0,
        three_bet_pct=12.0,
        fold_to_three_bet=45.0,
        cbet_flop_pct=75.0,
        cbet_turn_pct=60.0,
        cbet_river_pct=50.0,
        aggression_factor=2.5,
        wtsd=28.0,
        wsd=52.0,
    ),
    "agent_b": PlayerStatistics(
        hands_played=500,
        vpip=28.0,
        pfr=8.0,  # Very passive!
        limp_frequency=18.0,
        three_bet_pct=3.0,
        fold_to_three_bet=70.0,
        cbet_flop_pct=40.0,
        cbet_turn_pct=30.0,
        cbet_river_pct=25.0,
        aggression_factor=0.8,
        wtsd=35.0,
        wsd=48.0,
    ),
    "agent_c": PlayerStatistics(
        hands_played=500,
        vpip=18.0,
        pfr=15.0,
        limp_frequency=2.0,
        three_bet_pct=6.0,
        fold_to_three_bet=80.0,  # Folds a lot to 3-bets!
        cbet_flop_pct=70.0,
        cbet_turn_pct=55.0,
        cbet_river_pct=40.0,
        aggression_factor=1.5,
        wtsd=22.0,
        wsd=55.0,
    ),
    "agent_e": PlayerStatistics(
        hands_played=500,
        vpip=25.0,
        pfr=18.0,
        limp_frequency=5.0,
        three_bet_pct=8.0,
        fold_to_three_bet=55.0,
        cbet_flop_pct=65.0,
        cbet_turn_pct=50.0,
        cbet_river_pct=45.0,
        aggression_factor=1.8,
        wtsd=26.0,
        wsd=50.0,
    ),
}


def create_shared_knowledge_base(exclude_player: str | None = None) -> KnowledgeBase:
    """
    Create a knowledge base with pre-populated player profiles.

    This is used to give Agent D historical knowledge of opponents.

    Args:
        exclude_player: Player ID to exclude (don't include self in knowledge)

    Returns:
        KnowledgeBase with historical opponent profiles.
    """
    kb = KnowledgeBase()

    for player_id, stats in SHARED_KNOWLEDGE_STATS.items():
        if player_id != exclude_player:
            profile = PlayerProfile(
                player_id=player_id,
                name=player_id,
                statistics=stats,
            )

            # Add qualitative tendencies based on stats
            if stats.vpip > 30:
                profile.tendencies.append("Plays too many hands (loose)")
            if stats.pfr < 12:
                profile.tendencies.append("Passive preflop")
            if stats.fold_to_three_bet > 70:
                profile.tendencies.append("Folds to 3-bets too often")
            if stats.cbet_flop_pct > 70:
                profile.tendencies.append("C-bets flop frequently")
            if stats.aggression_factor < 1.0:
                profile.tendencies.append("Very passive postflop")
            if stats.wtsd > 30:
                profile.tendencies.append("Calls down too much")

            kb.update_profile(profile)

    return kb
