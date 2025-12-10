"""
Shared models for poker agent decisions.

This module provides a unified ActionDecision model that is used by ALL poker agents
for structured LLM output. This eliminates the need for regex parsing and ensures
consistent decision format across different agent architectures.
"""
from typing import Literal, TYPE_CHECKING

from pydantic import BaseModel, Field

from backend.domain.game.models import Action, ActionType

if TYPE_CHECKING:
    from backend.domain.game.models import StructuredGameState


class BetSizing(BaseModel):
    """
    Flexible bet sizing that can be expressed in multiple ways.
    
    Use ONE of these fields:
    - absolute: Exact chip amount (e.g., 150)
    - bb_multiple: Big blind multiplier (e.g., 3 means 3x BB)  
    - pot_fraction: Fraction of pot (e.g., 0.75 means 75% pot)
    """
    
    absolute: float | None = Field(
        default=None, 
        description="Exact chip amount (e.g., 150)"
    )
    bb_multiple: float | None = Field(
        default=None, 
        description="Big blind multiplier (e.g., 3.0 means 3x BB)"
    )
    pot_fraction: float | None = Field(
        default=None, 
        description="Fraction of pot (e.g., 0.75 means 75% pot)"
    )
    
    def resolve(self, game_state: "StructuredGameState") -> float:
        """Convert to absolute chip amount based on game state."""
        if self.absolute is not None:
            return self.absolute
        elif self.bb_multiple is not None:
            return self.bb_multiple * game_state.big_blind
        elif self.pot_fraction is not None:
            return self.pot_fraction * game_state.pot
        else:
            # Default to 2/3 pot
            return game_state.pot * 0.66


class ActionDecision(BaseModel):
    """
    Unified decision model for ALL poker agents.
    
    This Pydantic model serves dual purposes:
    1. Used with output_type for structured LLM output
    2. Contains to_action() method to resolve to executable Action
    
    Example LLM outputs:
    
    # Standard open raise (3x BB)
    {"action_type": "raise", "sizing": {"bb_multiple": 3}, ...}
    
    # C-bet 75% pot  
    {"action_type": "bet", "sizing": {"pot_fraction": 0.75}, ...}
    
    # All-in (sizing is ignored)
    {"action_type": "all_in", "sizing": null, ...}
    """
    
    gto_analysis: str = Field(
        description="GTO-based reasoning for this decision (1-2 sentences)"
    )
    exploit_analysis: str = Field(
        description="Opponent exploitation reasoning (1-2 sentences)"
    )
    gto_deviation: str = Field(
        description="'Following GTO because...' or 'Deviating from GTO because...'"
    )
    
    action_type: Literal["fold", "check", "call", "bet", "raise", "all_in"] = Field(
        description="The poker action to take"
    )
    sizing: BetSizing | None = Field(
        default=None,
        description="Bet/raise sizing. Use ONE of: absolute (chips), bb_multiple (e.g. 3 for 3BB), pot_fraction (e.g. 0.75 for 75% pot). Null for fold/check/call/all_in."
    )
    
    confidence: float = Field(
        ge=0.0, 
        le=1.0, 
        description="Confidence level from 0.0 to 1.0"
    )
    
    def to_action(self, game_state: "StructuredGameState") -> Action:
        """
        Resolve this decision to an executable Action object.
        
        Handles:
        - Converting action_type string to ActionType enum
        - Resolving sizing to absolute chip amount
        - Clamping bet/raise to legal range
        - Falling back to legal action if chosen action is invalid
        """
        action_map = {
            "fold": ActionType.FOLD,
            "check": ActionType.CHECK,
            "call": ActionType.CALL,
            "bet": ActionType.BET,
            "raise": ActionType.RAISE,
            "all_in": ActionType.ALL_IN,
        }
        
        action_type = action_map[self.action_type]
        amount: float | None = None
        
        # Resolve amount based on action type
        if action_type == ActionType.ALL_IN:
            amount = game_state.max_raise
        elif action_type in (ActionType.BET, ActionType.RAISE):
            if self.sizing:
                amount = self.sizing.resolve(game_state)
            else:
                # Default: 2/3 pot
                amount = game_state.pot * 0.66
            # Clamp to legal range
            if game_state.min_raise > 0:
                amount = max(game_state.min_raise, min(amount, game_state.max_raise))
        elif action_type == ActionType.CALL:
            amount = game_state.current_bet
        
        # Validate action is legal, fall back if not
        if action_type not in game_state.legal_actions:
            if ActionType.CHECK in game_state.legal_actions:
                return Action(type=ActionType.CHECK, amount=None)
            elif ActionType.CALL in game_state.legal_actions:
                return Action(type=ActionType.CALL, amount=game_state.current_bet)
            elif ActionType.FOLD in game_state.legal_actions:
                return Action(type=ActionType.FOLD, amount=None)
            # Last resort - should not happen
            return Action(type=ActionType.FOLD, amount=None)
        
        return Action(type=action_type, amount=amount)
    
    @property
    def reasoning(self) -> str:
        """Combined reasoning from GTO and exploit analysis."""
        return f"{self.gto_analysis} {self.exploit_analysis}"


