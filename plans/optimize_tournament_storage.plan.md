---
name: Optimize Tournament Storage
overview: Reduce tournament JSON file size by storing only the minimal data needed for statistics recalculation, eliminating redundant nested data.
todos:
  - id: create-minimal-models
    content: Create MinimalAction model with only stats-relevant fields
    status: completed
  - id: update-recorder
    content: Update GameStateRecorder to use minimal format
    status: completed
  - id: update-recalculator
    content: Update recalculator to work with minimal format
    status: completed
  - id: add-backward-compat
    content: Add backward compatibility for loading old format files
    status: completed
---

# Optimize Tournament Storage

## Problem

Current tournament JSON files are ~15,000+ lines due to:
1. **Redundant `action_history`**: Each state stores ALL previous actions (O(n²) growth)
2. **Unused fields**: `community_cards`, `hole_cards`, `legal_actions`, `min_raise`, `max_raise`, etc.
3. **Full player array repeated**: 5 players × 7 fields × every action

## Solution: Minimal Recording Format

Store only what statistics calculation needs:

### Current Format (per action ~80+ lines):

```json
{
  "state": {
    "hand_number": 1,
    "button_seat": 4,
    "small_blind": 10.0,
    "big_blind": 20.0,
    "street": "preflop",
    "pot": 30.0,
    "community_cards": [...],
    "players": [{...}, {...}, {...}, {...}, {...}],
    "hero_seat": 2,
    "current_bet": 20.0,
    "min_raise": 40.0,
    "max_raise": 1500.0,
    "legal_actions": [...],
    "action_history": [... ALL previous actions ...]
  },
  "actor": "agent_c",
  "action": {"type": "fold", "amount": null}
}
```

### Optimized Format (per action ~10 lines):

```json
{
  "hand_number": 1,
  "street": "preflop",
  "actor": "agent_c",
  "action_type": "fold",
  "amount": null,
  "pot": 30.0,
  "current_bet": 20.0,
  "preflop_raise_count": 0
}
```

Fields:
- `hand_number`: hand number (for hand boundaries)
- `street`: current street (preflop/flop/turn/river)
- `actor`: player name taking the action
- `action_type`: action type (fold/check/call/bet/raise/all_in)
- `amount`: action amount (null if not applicable)
- `pot`: pot size before action (for bet sizing %)
- `current_bet`: current bet to call (for limp detection)
- `preflop_raise_count`: number of raises so far in preflop (for 3-bet detection)

### Tournament Header (once per file):

```json
{
  "tournament_id": "...",
  "timestamp": "...",
  "players": ["agent_a", "agent_b", "agent_c", "agent_d", "agent_e"],
  "big_blind": 20.0,
  "actions": [...]
}
```

## Estimated Size Reduction

- Current: ~80 lines per action × 200 actions = ~16,000 lines
- Optimized: ~10 lines per action × 200 actions + header = ~2,100 lines
- **~85% reduction**

## Implementation

### 1. Create Minimal Models

File: `backend/domain/game/recorder.py`

```python
@dataclass
class MinimalAction:
    """Minimal action record for statistics recalculation."""
    hand_number: int
    street: str
    actor: str
    action_type: str
    amount: float | None
    pot: float
    current_bet: float
    preflop_raise_count: int

    def to_dict(self) -> dict:
        return {
            "hand_number": self.hand_number,
            "street": self.street,
            "actor": self.actor,
            "action_type": self.action_type,
            "amount": self.amount,
            "pot": self.pot,
            "current_bet": self.current_bet,
            "preflop_raise_count": self.preflop_raise_count,
        }
```

### 2. Update Recording Logic

In `GameStateRecorder.record_action()`:
- Extract only needed fields
- Calculate `preflop_raise_count` from action_history
- Store minimal format

### 3. Update Recalculator

In `recalculator.py`:
- Create a minimal `StructuredGameState` stub for tracker compatibility
- Or modify tracker to accept minimal format directly

### 4. Backward Compatibility

- Detect format version from JSON structure
- Support loading both old (full state) and new (minimal) formats
- Old files: `states` array with full `state` objects
- New files: `actions` array with minimal objects

## Files to Modify

| File | Change |
|------|--------|
| `backend/domain/game/recorder.py` | Add MinimalAction, update save format |
| `backend/domain/game/models.py` | Add minimal state reconstruction helper |
| `backend/domain/player/recalculator.py` | Support minimal format |

