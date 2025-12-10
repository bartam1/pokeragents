---
name: Game State Persistence
overview: Implement game state persistence and statistics recalculation - save all StructuredGameState objects during tournament runs to timestamped JSON files, and parse all saved game states before each run to compute fresh baseline statistics.
todos:
  - id: serialize-models
    content: Add to_dict/from_dict methods to Card, PlayerState, StructuredGameState
    status: completed
  - id: create-recorder
    content: Create GameStateRecorder class in backend/domain/game/recorder.py
    status: completed
  - id: create-recalculator
    content: Create recalculate_baseline_stats in backend/domain/player/recalculator.py
    status: completed
  - id: integrate-orchestrator
    content: Integrate GameStateRecorder into TournamentOrchestrator
    status: completed
  - id: integrate-main
    content: Call recalculator before run_experiment in main.py
    status: completed
---

# Game State Persistence and Statistics Recalculation

## Current Architecture

The tournament orchestrator runs hands via `_play_hand()`, which calls `get_structured_state()` for each decision. Statistics are tracked by `StatisticsTracker` during play but only saved per-agent after each tournament. The `calibrated_stats.json` is loaded once at startup and used as baseline knowledge.

## Proposed Changes

### 1. Add Serialization to Game Models

Modify [`backend/domain/game/models.py`](app/backend/domain/game/models.py):

- Add `to_dict()` method to `Card`, `PlayerState`, `StructuredGameState`
- Add `from_dict()` class methods for deserialization
- Include action context in saved states (actor, action taken)

### 2. Create Game State Recorder

Create new module `backend/domain/game/recorder.py`:

- `GameStateRecorder` class to collect states during a tournament
- `save_tournament()` method writes all states to timestamped JSON file
- `load_all_tournaments()` method reads all saved game state files

Saved file structure (`data/gamestates/tournament_YYYYMMDD_HHMMSS_<id>.json`):

```json
{
  "tournament_id": "...",
  "timestamp": "...",
  "states": [
    {"state": {...}, "actor": "agent_a", "action": {"type": "raise", "amount": 100}}
  ]
}
```

### 3. Create Statistics Recalculator

Create new module `backend/domain/player/recalculator.py`:

- `recalculate_baseline_stats()` function
- Loads all saved tournament files
- Replays actions through a fresh `StatisticsTracker`
- Saves fresh `calibrated_stats.json` before tournament run

### 4. Integrate into Tournament Flow

Modify [`backend/domain/tournament/orchestrator.py`](app/backend/domain/tournament/orchestrator.py):

- Add `GameStateRecorder` instance to `TournamentOrchestrator`
- Record each `(state, actor, action)` tuple in `_play_hand()`
- Save recorded states at tournament end in `run_tournament()`

Modify [`backend/main.py`](app/backend/main.py):

- Call `recalculate_baseline_stats()` before `run_experiment()`
- Pass recalculated stats path to orchestrator

```mermaid
flowchart TD
    subgraph pre_run [Before Run]
        A[Load All Saved Game States] --> B[Replay Through StatisticsTracker]
        B --> C[Save Fresh calibrated_stats.json]
    end
    
    subgraph during_run [During Tournament]
        D[Agent Requests State] --> E[get_structured_state]
        E --> F[Record State + Action]
        F --> G[Execute Action]
    end
    
    subgraph post_run [After Tournament]
        H[Save Tournament Game States] --> I[tournament_TIMESTAMP_ID.json]
    end
    
    pre_run --> during_run
    during_run --> post_run
```

## Files to Modify/Create

| File | Action |
|------|--------|
| `backend/domain/game/models.py` | Add `to_dict()`/`from_dict()` methods |
| `backend/domain/game/recorder.py` | **Create** - GameStateRecorder class |
| `backend/domain/player/recalculator.py` | **Create** - Statistics recalculation |
| `backend/domain/tournament/orchestrator.py` | Integrate recorder |
| `backend/main.py` | Call recalculator before runs |
| `backend/config.py` | Add `gamestates_dir` setting |

