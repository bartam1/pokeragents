"""
Strategy configurations for agent personalities.

Each strategy defines:
- Behavioral tendencies (aggression, bluffing, folding)
- Qualitative tendencies (for prompt injection)
- Whether the agent has pre-loaded opponent knowledge
"""

from dataclasses import dataclass, field


@dataclass
class StrategyConfig:
    """
    Configuration that shapes agent behavior.
    These are instructions injected into agent prompts.
    """

    name: str
    description: str

    # Style weights (0.0 to 1.0)
    aggression: float = 0.5  # How often to bet/raise vs check/call
    bluff_frequency: float = 0.3  # How often to bluff
    fold_threshold: float = 0.5  # How easily they fold (higher = folds more)

    # Specific behavioral tendencies
    tendencies: list[str] = field(default_factory=list)

    # KEY DIFFERENTIATOR: Whether this agent has pre-loaded opponent knowledge
    has_shared_knowledge: bool = False

    # Whether to use multi-agent ensemble architecture (GTO + Exploit + Decision)
    use_ensemble: bool = False

    def to_prompt_instructions(self) -> str:
        """Convert strategy to LLM instructions for the decision maker."""
        instructions = [
            f"You are playing as {self.name}.",
            f"Your playing style: {self.description}",
            "",
        ]

        # Aggression guidance
        if self.aggression > 0.7:
            instructions.append(
                "AGGRESSION: You prefer aggressive play - bet and raise frequently. "
                "Apply pressure whenever you sense weakness."
            )
        elif self.aggression < 0.3:
            instructions.append(
                "AGGRESSION: You prefer passive play - check and call more than bet. "
                "Let opponents make mistakes by calling them down."
            )
        else:
            instructions.append(
                "AGGRESSION: You play a balanced style - mix aggression with "
                "passive plays based on the situation."
            )

        # Bluffing guidance
        if self.bluff_frequency > 0.5:
            instructions.append(
                "BLUFFING: You enjoy bluffing and applying pressure with weak hands. "
                "Look for opportunities to represent strength."
            )
        elif self.bluff_frequency < 0.2:
            instructions.append(
                "BLUFFING: You rarely bluff - only bet with strong hands. Your bets mean strength."
            )
        else:
            instructions.append(
                "BLUFFING: You bluff at a balanced frequency - mixing value bets "
                "with occasional bluffs."
            )

        # Fold threshold guidance
        if self.fold_threshold > 0.7:
            instructions.append(
                "FOLDING: You fold easily when facing aggression. "
                "Preserve your chips for strong hands."
            )
        elif self.fold_threshold < 0.3:
            instructions.append(
                "FOLDING: You are a calling station - you rarely fold. You like to see showdowns."
            )
        else:
            instructions.append(
                "FOLDING: You fold at appropriate times - not too tight, not too loose."
            )

        # Specific tendencies
        if self.tendencies:
            instructions.append("")
            instructions.append("Your specific tendencies:")
            for tendency in self.tendencies:
                instructions.append(f"  - {tendency}")

        return "\n".join(instructions)


# =============================================================================
# Pre-defined agent strategies for the POC experiment
# =============================================================================

AGENT_A_BLUFFER = StrategyConfig(
    name="Agent A (The Bluffer)",
    description="Aggressive bluffer who loves to apply pressure and steal pots",
    aggression=0.8,
    bluff_frequency=0.6,
    fold_threshold=0.4,
    tendencies=[
        "Frequently bluffs on scare cards (aces, flush/straight completers)",
        "3-bets light preflop to steal blinds",
        "Uses large sizing to pressure opponents",
        "Double and triple barrels as bluffs",
        "Rarely gives up on a bluff once started",
    ],
    has_shared_knowledge=False,
)

AGENT_B_PASSIVE = StrategyConfig(
    name="Agent B (The Calling Station)",
    description="Passive player who prefers to call and see showdowns",
    aggression=0.2,
    bluff_frequency=0.1,
    fold_threshold=0.35,
    tendencies=[
        "Rarely bets without a strong hand",
        "Likes to slowplay big hands",
        "Calls down with medium-strength hands",
        "Limps preflop with marginal hands",
        "Will call large bets with weak holdings",
    ],
    has_shared_knowledge=False,
)

AGENT_C_TIGHT = StrategyConfig(
    name="Agent C (The Rock)",
    description="Tight player who only plays premium hands and folds easily",
    aggression=0.5,
    bluff_frequency=0.15,
    fold_threshold=0.8,
    tendencies=[
        "Only plays premium starting hands (AA, KK, QQ, AK, etc.)",
        "Folds to aggression without strong hands",
        "Very predictable - their bets mean they have it",
        "Gives up easily on the river",
        "Respects raises and re-raises",
    ],
    has_shared_knowledge=False,
)

AGENT_D_INFORMED = StrategyConfig(
    name="Agent D (The Informed Veteran)",
    description="Experienced player with historical knowledge of all opponents",
    aggression=0.5,
    bluff_frequency=0.35,
    fold_threshold=0.5,
    tendencies=[
        "Exploits opponent tendencies when identified",
        "Adjusts strategy dynamically based on opponent profiles",
        "Balanced default approach, exploitation when confident",
        "Bluffs more vs tight players, values bets more vs calling stations",
        "Uses position and opponent data to make optimal decisions",
    ],
    has_shared_knowledge=True,  # KEY: Has pre-loaded opponent stats
)

AGENT_E_ENSEMBLE = StrategyConfig(
    name="Agent E (The Informed Ensemble)",
    description="Informed player using multi-agent ensemble architecture",
    aggression=0.5,
    bluff_frequency=0.35,
    fold_threshold=0.5,
    tendencies=[
        "Has same pre-loaded historical knowledge as Agent D",
        "Uses multi-agent ensemble: GTO Analyst + Exploit Analyst + Decision Maker",
        "GTO Analyst provides game-theory optimal baseline",
        "Exploit Analyst identifies opponent-specific adjustments",
        "Decision Maker weighs both analyses for final action",
    ],
    has_shared_knowledge=True,  # KEY: Same knowledge as Agent D (INFORMED)
    use_ensemble=True,  # KEY: Uses multi-agent architecture (ENSEMBLE)
)


# All strategies for easy iteration
ALL_STRATEGIES = {
    "agent_a": AGENT_A_BLUFFER,
    "agent_b": AGENT_B_PASSIVE,
    "agent_c": AGENT_C_TIGHT,
    "agent_d": AGENT_D_INFORMED,
    "agent_e": AGENT_E_ENSEMBLE,
}


def get_strategy(player_id: str) -> StrategyConfig:
    """Get the strategy for a player ID."""
    return ALL_STRATEGIES.get(player_id, AGENT_E_ENSEMBLE)
