---
name: Enhanced Action History
overview: Enhance the action_history format in StructuredGameState to include pot size and all player stacks at each action point, providing better context for agent decision-making and analysis.
todos:
  - id: enhance-environment
    content: Add pot_before_action and stacks_before to action_history in environment.py
    status: pending
  - id: update-agent-d-prompt
    content: Update poker_agent.py prompt to display pot context in actions
    status: pending
  - id: update-agent-e-prompt
    content: Update ensemble_agent.py hand history to display pot context
    status: pending
---

# Enhanced Action History with Pot and Stack Tracking

## Goal

Enrich `action_history` entries to include:

- `pot_before_action`: Pot size when the action was taken
- `stacks_before`: All player stacks when the action was taken

This provides complete context for understanding bet sizing, commitment levels, and SPR (stack-to-pot ratio) at each decision point.

## Current vs Enhanced Format

**Current format:**

```json
{
  "player_index": 0,
  "player_name": "Agent A",
  "action": "bet",
  "amount": 100,
  "street": "flop"
}
```

**Enhanced format:**

```json
{
  "player_index": 0,
  "player_name": "Agent A",
  "action": "bet",
  "amount": 100,
  "street": "flop",
  "pot_before_action": 150,
  "stacks_before": {
    "Agent A": 800,
    "Agent B": 650,
    "Hero": 920,
    "Agent C": 1500
  }
}
```

## Files to Modify

### 1. Environment - Capture enhanced data

**File:** [`app/backend/domain/game/environment.py`](app/backend/domain/game/environment.py)

**Location:** `execute_action()` method, lines 314-320

**Change:** Before recording the action, capture pot and all stacks:

```python
# Record in action history with enhanced context
stacks_before = {
    self.player_names[i]: float(state.stacks[i])
    for i in range(self.num_players)
}

self._action_history.append({
    "player_index": player_index,
    "player_name": self.player_names[player_index],
    "action": action.type.value,
    "amount": result.get("amount"),
    "street": self._get_current_street().value,
    "pot_before_action": float(state.total_pot_amount),
    "stacks_before": stacks_before,
})
```

### 2. Agent D Prompt - Display enhanced info

**File:** [`app/backend/domain/agent/poker_agent.py`](app/backend/domain/agent/poker_agent.py)

**Location:** `_build_state_prompt()` method, lines 311-319

**Change:** Update action formatting to show pot and stack context:

```python
# Format action with pot and stack context
action_type = action.get("action", action.get("action_type", "?"))
amount = action.get("amount")
player_name = action.get("player_name", "?")
pot = action.get("pot_before_action")

if amount and pot:
    lines.append(f"  {player_name} {action_type} {amount:.0f} (pot: {pot:.0f})")
elif amount:
    lines.append(f"  {player_name} {action_type} {amount:.0f}")
else:
    lines.append(f"  {player_name} {action_type}")
```

### 3. Agent E Prompt - Display enhanced info

**File:** [`app/backend/domain/agent/ensemble_agent.py`](app/backend/domain/agent/ensemble_agent.py)

**Location:** `_build_hand_history()` method, lines 260-282

**Change:** Same enhancement to show pot context in hand history:

```python
if amount and amount > 0:
    pot = action.get("pot_before_action")
    if pot:
        lines.append(f"  {player}: {action_type} {amount:.0f} (pot: {pot:.0f})")
    else:
        lines.append(f"  {player}: {action_type} {amount:.0f}")
else:
    lines.append(f"  {player}: {action_type}")
```

## Example Output

**Before:**

```
*** FLOP *** [Kd 7c 2h]
  Agent A bet 100
  Agent B call 100
```

**After:**

```
*** FLOP *** [Kd 7c 2h]
  Agent A bet 100 (pot: 150, stacks: A=800 B=650 Hero=920 C=1500)
  Agent B call 100 (pot: 250, stacks: A=700 B=650 Hero=920 C=1500)
```

## Benefits

1. **Bet sizing context**: LLM understands if 100 is a 2/3 pot bet or a 1/4 pot bet
2. **Stack tracking**: Full reconstruction of hand state at any point
3. **SPR analysis**: Can calculate stack-to-pot ratios for commitment decisions
4. **Better exploitation**: Identify sizing tells (overbets, underbets)
5. **Test scenarios**: JSON test files will have complete hand context

## Notes

No backward compatibility needed - this is a clean update to the action_history format.