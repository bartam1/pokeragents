---
name: Graceful Shutdown
overview: Add graceful shutdown handling for Ctrl+C (SIGINT) that stops running tasks and saves tournament data with an "incomplete_" prefix in the filename.
todos:
  - id: recorder-incomplete
    content: Add incomplete parameter to save_tournament() for incomplete_ prefix
    status: completed
  - id: orchestrator-shutdown
    content: Add save_incomplete() method to TournamentOrchestrator
    status: completed
  - id: main-signal
    content: Add SIGINT handler and graceful shutdown logic in main.py
    status: completed
---

# Graceful Shutdown for Tournament Runner

## Overview

When Ctrl+C is pressed, the application should:

1. Cancel ongoing async tasks gracefully
2. Save any recorded tournament data with "incomplete_" prefix
3. Exit cleanly

## Changes Required

### 1. Modify GameStateRecorder

Update [`backend/domain/game/recorder.py`](app/backend/domain/game/recorder.py):

- Add `incomplete` parameter to `save_tournament()` method
- When `incomplete=True`, prefix filename with "incomplete_"

### 2. Modify TournamentOrchestrator

Update [`backend/domain/tournament/orchestrator.py`](app/backend/domain/tournament/orchestrator.py):

- Add `save_incomplete()` method to save current state when interrupted
- Expose the recorder for external access during shutdown

### 3. Add Signal Handling in main.py

Update [`backend/main.py`](app/backend/main.py):

- Register SIGINT handler using `signal` module
- On interrupt: cancel running tasks and trigger incomplete save
- Use a shutdown flag to coordinate graceful exit
```mermaid
sequenceDiagram
    participant User
    participant Main as main.py
    participant Orchestrator
    participant Recorder

    User->>Main: Ctrl+C (SIGINT)
    Main->>Main: Set shutdown flag
    Main->>Orchestrator: Cancel current task
    Orchestrator->>Recorder: save_tournament(incomplete=True)
    Recorder->>Recorder: Save as incomplete_tournament_...json
    Main->>User: Exit with message
```


## File Changes

| File | Change |

|------|--------|

| `backend/domain/game/recorder.py` | Add `incomplete` param to `save_tournament()` |

| `backend/domain/tournament/orchestrator.py` | Add `save_incomplete()` method |

| `backend/main.py` | Add SIGINT handler and graceful shutdown logic |

