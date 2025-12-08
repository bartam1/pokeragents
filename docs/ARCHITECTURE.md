# PokerAgents Architecture

## System Overview

```mermaid
flowchart TB
    subgraph CLI["CLI Entry Point"]
        main["main.py"]
    end

    subgraph Orchestration["Tournament Orchestration"]
        orchestrator["TournamentOrchestrator"]
        results["TournamentResult"]
    end

    subgraph GameEngine["Game Engine (PokerKit)"]
        env["PokerEnvironment"]
        pokerkit["PokerKit Library"]
        state["StructuredGameState"]
    end

    subgraph Agents["AI Agents"]
        agentA["Agent A (Bluffer)"]
        agentB["Agent B (Calling Station)"]
        agentC["Agent C (Rock)"]
        agentD["Agent D (Informed)<br/>Simple Architecture"]
        agentE["Agent E (Informed Ensemble)<br/>Multi-Agent Architecture"]
    end

    subgraph LLM["LLM Integration"]
        sdk["OpenAI Agents SDK"]
        tools["Function Tools"]
        model["LLM Model"]
    end

    subgraph Knowledge["Knowledge System"]
        kb["KnowledgeBase"]
        profiles["PlayerProfiles"]
        stats["PlayerStatistics"]
        persistence["JSON Persistence"]
    end

    main --> orchestrator
    orchestrator --> env
    orchestrator --> Agents
    orchestrator --> results
    
    env --> pokerkit
    env --> state
    
    Agents --> sdk
    sdk --> tools
    sdk --> model
    
    agentD --> kb
    agentE --> kb
    kb --> profiles
    profiles --> stats
    kb --> persistence
```

## Component Details

### 1. Tournament Orchestrator

The central controller that manages the poker tournament lifecycle.

```mermaid
sequenceDiagram
    participant CLI as CLI (main.py)
    participant Orch as TournamentOrchestrator
    participant Env as PokerEnvironment
    participant Agent as PokerAgent
    participant LLM as LLM Model

    CLI->>Orch: run_tournament()
    Orch->>Orch: setup_tournament()
    
    loop Each Hand
        Orch->>Env: start_hand()
        Env-->>Orch: initial state
        
        loop Until Hand Complete
            Orch->>Env: get_structured_state()
            Env-->>Orch: StructuredGameState
            Orch->>Agent: decide_action(state)
            Agent->>LLM: prompt + tools
            LLM-->>Agent: action decision
            Agent-->>Orch: PokerAction
            Orch->>Env: execute_action(action)
            
            Note over Orch,Agent: Other agents observe action
            Orch->>Agent: observe_action()
        end
        
        Orch->>Env: complete_hand()
        Env-->>Orch: HandResult
    end
    
    Orch-->>CLI: TournamentResult
```

### 2. PokerKit Integration

The `PokerEnvironment` class wraps PokerKit to provide a clean interface.

```mermaid
classDiagram
    class PokerEnvironment {
        -NoLimitTexasHoldem _game
        -State _state
        -int small_blind
        -int big_blind
        +start_hand()
        +execute_action(action)
        +get_structured_state(player_idx)
        +complete_hand() HandResult
        +set_blinds(sb, bb)
    }
    
    class StructuredGameState {
        +Street street
        +List~PlayerState~ players
        +List~Card~ community_cards
        +float pot_size
        +float current_bet
        +int active_player_idx
        +List~ActionType~ valid_actions
        +float min_raise
        +float max_raise
    }
    
    class HandResult {
        +List~int~ winner_indices
        +float pot_size
        +List~Tuple~ showdown_hands
        +Dict payoffs
    }
    
    PokerEnvironment --> StructuredGameState
    PokerEnvironment --> HandResult
```

### 3. AI Agent Architecture

The system supports two agent architectures:

#### 3a. Simple Agent (Agent D)

Single-agent architecture using OpenAI Agents SDK with combined GTO + Exploit reasoning.

```mermaid
flowchart LR
    subgraph PokerAgent
        direction TB
        decide["decide()"]
        observe["observe_action()"]
        prompt["_build_state_prompt()<br/>+ opponent stats injected"]
    end
    
    subgraph Tools["@function_tool"]
        pot["calculate_pot_odds()"]
        equity["calculate_equity()"]
    end
    
    subgraph Knowledge
        kb["KnowledgeBase"]
        profile["PlayerProfile"]
        stats["PlayerStatistics"]
    end
    
    subgraph Output
        gto_dev["GTO_DEVIATION reasoning"]
        action["ACTION + CONFIDENCE"]
    end
    
    decide --> prompt
    decide --> Tools
    decide --> kb
    observe --> stats
    
    prompt --> gto_dev
    gto_dev --> action
```

**Key Features:**
- Opponent stats and position info **injected directly into prompt**
- Access to pot odds and equity calculation tools
- Must provide **GTO_DEVIATION** explanation for each decision

#### 3b. Multi-Agent Ensemble (Agent E)

Three specialized agents working together for better analysis separation.

```mermaid
flowchart TB
    subgraph Input["Game State"]
        state["StructuredGameState"]
        history["Hand History"]
        stats["Opponent Statistics<br/>(injected to prompt)"]
    end
    
    subgraph GTOTools["GTO Tools"]
        pot_odds["calculate_pot_odds()"]
        equity["calculate_equity()"]
    end
    
    subgraph Specialists["Specialist Agents (Parallel Execution)"]
        gto["🎯 GTO Analyst<br/>Pure math/theory<br/>+ Tool Access"]
        exploit["🔍 Exploit Analyst<br/>Opponent tendencies<br/>VPIP/PFR analysis"]
    end
    
    subgraph Decision["Decision Maker"]
        final["🎲 Final Decision<br/>Weighs both analyses<br/>+ GTO_DEVIATION"]
    end
    
    subgraph Output["Action"]
        action["PokerAction + Reasoning"]
    end
    
    state --> gto
    state --> exploit
    history --> gto
    history --> exploit
    stats --> exploit
    GTOTools --> gto
    
    gto --> |"GTOAnalysis"| final
    exploit --> |"ExploitAnalysis"| final
    final --> action
```

**Specialist Responsibilities:**

| Specialist | Focus | Tools | Output |
|------------|-------|-------|--------|
| **GTO Analyst** | Mathematical/theoretical poker | pot_odds, equity | Hand strength, recommended sizing |
| **Exploit Analyst** | Opponent tendencies | None (stats in prompt) | Type classification, leak identification |
| **Decision Maker** | Synthesize both analyses | None | Final action + GTO_DEVIATION reasoning |

**Key Benefits:**
- Parallel execution of GTO and Exploit analysis
- Clean separation of concerns
- More transparent decision making
- Better specialization per domain

**Trade-offs:**
- 3x LLM calls per decision (2 parallelizable + 1 sequential)
- Higher latency (~2x vs single agent)
- More tokens consumed per action

### 3c. Structured Output (ActionDecision)

Both agent architectures use the same `ActionDecision` Pydantic model for structured LLM output.

```mermaid
classDiagram
    class ActionDecision {
        +str gto_analysis
        +str exploit_analysis
        +str gto_deviation
        +Literal action_type
        +BetSizing sizing
        +float confidence
        +to_action(game_state) Action
    }
    
    class BetSizing {
        +float absolute
        +float bb_multiple
        +float pot_fraction
        +resolve(game_state) float
    }
    
    ActionDecision --> BetSizing
```

**Key Features:**
- Used with OpenAI Agents SDK `output_type` for reliable JSON parsing
- Flexible bet sizing (absolute chips, BB multiple, or pot fraction)
- Automatic action validation and fallback to legal actions
- Combined `to_action()` method resolves to executable `Action` object

### 3d. Shared Prompts (Single Source of Truth)

Both agents use shared exploitation guidelines from `prompts.py`:

```python
# prompts.py - Used by both Agent D and Agent E
EXPLOITATION_GUIDELINES = """
Key Principle: More hands observed = More confidence in exploitation

Before deciding to exploit:
1. CHECK THE HAND COUNT
2. Scale confidence with sample size
3. GTO is the safe default
"""

GTO_DEFAULT = """
GTO is Your Default Strategy
Only deviate when you have:
1. Enough observed hands
2. A clear, specific leak
3. Confidence the exploit improves EV
"""
```

**Design Principle:** Simple guidelines let the LLM reason, rather than rigid rules that might be ignored.

### 4. Knowledge Base System

Tracks opponent statistics and enables exploitation.

```mermaid
classDiagram
    class KnowledgeBase {
        +Dict~str,PlayerProfile~ profiles
        +get_profile(player_id)
        +merge_with(other)
        +accumulate_with(other)
        +save_to_file(path)
        +load_from_file(path)
    }
    
    class PlayerProfile {
        +str player_id
        +PlayerStatistics statistics
        +List~str~ tendencies
    }
    
    class PlayerStatistics {
        +int hands_played
        +float vpip
        +float pfr
        +float limp_frequency
        +float three_bet_percentage
        +float fold_to_3bet
        +float cbet_flop
        +float cbet_turn
        +float cbet_river
        +float aggression_factor
        +float wtsd
        +float wsd
        +accumulate(other)
        +recalculate()
    }
    
    KnowledgeBase "1" --> "*" PlayerProfile
    PlayerProfile "1" --> "1" PlayerStatistics
```

### 5. Statistics Tracking Flow

```mermaid
flowchart TB
    subgraph Preflop
        vpip["VPIP: Voluntarily Put $ In Pot"]
        pfr["PFR: Pre-Flop Raise"]
        limp["Limp: Call without prior raise"]
        threebet["3-Bet Opportunities"]
    end
    
    subgraph Postflop
        cbet["C-Bet: Continuation Bet"]
        aggression["Aggression: Bets+Raises vs Calls"]
    end
    
    subgraph Showdown
        wtsd["WTSD: Went To Showdown"]
        wsd["WSD: Won At Showdown"]
    end
    
    action["observe_action()"] --> Preflop
    action --> Postflop
    hand_end["end_hand()"] --> Showdown
```

### 6. Sample Size Requirements

Statistics require sufficient sample size to be meaningful:

| Hands | Reliability | Display |
|-------|-------------|---------|
| < 20 | ⚠️ Very Low | "INSUFFICIENT DATA - Play GTO" |
| 20-49 | ⚠️ Low | Stats shown with warning |
| 50-99 | 📊 Moderate | Stats reliable for cautious exploitation |
| 100+ | ✅ Good | Stats fully reliable |

**Key Rule**: Never exploit based on < 50 hands - variance is too high!

### 7. Agent Knowledge Persistence

Both Agent D and Agent E are "informed" agents that receive the **same shared knowledge**:

```mermaid
flowchart TB
    subgraph SharedKnowledge["Shared Knowledge (Same for Both)"]
        calibrated["calibrated_stats.json"]
    end
    
    subgraph AgentD["Agent D (Simple Architecture)"]
        loadD["Load shared knowledge"]
        playD["Single LLM Decision"]
        saveD["Save to agent_d_knowledge.json"]
    end
    
    subgraph AgentE["Agent E (Ensemble Architecture)"]
        loadE["Load shared knowledge"]
        playE["GTO + Exploit + Decision"]
        saveE["Save to agent_e_knowledge.json"]
    end
    
    subgraph CalibrationMode["Calibration Mode"]
        emptyC["Both start empty"]
        observeC["Observe real behaviors"]
        saveC["Accumulate to calibrated_stats.json"]
        accumC["Uses agent_d as canonical source"]
    end
    
    calibrated --> loadD --> playD --> saveD
    calibrated --> loadE --> playE --> saveE
    emptyC --> observeC --> saveC --> accumC
```

**Knowledge Files:**

| File | Purpose |
|------|---------|
| `calibrated_stats.json` | Accumulated stats from calibration runs (shared by both agents) |
| `agent_d_knowledge.json` | Agent D's learned knowledge (saved per tournament) |
| `agent_e_knowledge.json` | Agent E's learned knowledge (saved per tournament) |

**Experiment Design**: Both agents start with **identical knowledge** from `calibrated_stats.json` - only the architecture differs.

## Data Flow

### Normal Tournament Mode

```mermaid
flowchart LR
    calibrated["calibrated_stats.json"]
    
    calibrated --> |"Same knowledge"| AgentD["Agent D (Simple)"]
    calibrated --> |"Same knowledge"| AgentE["Agent E (Ensemble)"]
    
    AgentD --> |"1 LLM call"| DecisionD["Combined GTO+Exploit"]
    AgentE --> |"3 LLM calls"| DecisionE["GTO → Exploit → Decision"]
```

### Calibration Mode

```mermaid
flowchart LR
    Tournament1["Tournament 1"] --> Stats1["Observed Stats"]
    Tournament2["Tournament 2"] --> Stats2["Observed Stats"]
    TournamentN["Tournament N"] --> StatsN["Observed Stats"]
    
    Stats1 --> Accumulate["accumulate_with()"]
    Stats2 --> Accumulate
    StatsN --> Accumulate
    
    Accumulate --> Calibrated["calibrated_stats.json"]
```

## Technology Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Game Engine | PokerKit | Poker rules, hand evaluation, state management |
| AI Framework | OpenAI Agents SDK | LLM-based decision making with tools |
| LLM | GPT-4o / Azure OpenAI | Agent reasoning and action selection |
| Serialization | Pydantic | Data models and JSON serialization |
| Configuration | Pydantic Settings | Environment variable management |
| Package Manager | uv | Fast Python dependency management |

## Agent Tools

All agents (A, B, C, D, E) are LLM-based and have access to the same toolset:

| Tool | Description |
|------|-------------|
| `calculate_pot_odds(pot, to_call)` | Calculate required equity to call profitably |
| `calculate_equity(hole_cards, board, opponents)` | Monte Carlo hand strength simulation using PokerKit |

**Architecture differences**:
- **Agent D (single LLM)**: Tools available directly to the agent
- **Agent E (ensemble)**: Only the GTOAnalyst specialist has tools; ExploitAnalyst and DecisionMaker receive data via prompts

**Note**: Position info and opponent statistics are injected directly into prompts - no tools needed.

## Tracking & Analysis Systems

### GTO Deviation Tracker

Monitors when agents follow vs deviate from GTO and correlates with profit/loss.

```mermaid
flowchart TB
    subgraph Decision["Agent Decision"]
        decide["decide()"]
        gto_check["is_following_gto?"]
    end
    
    subgraph Tracker["GTODeviationTracker"]
        record["record_decision()"]
        outcome["record_hand_outcome()"]
    end
    
    subgraph Analysis["End of Tournament"]
        stats["get_agent_stats()"]
        report["Profit analysis"]
    end
    
    decide --> gto_check --> record
    hand_complete["Hand Complete"] --> outcome
    stats --> report
```

**Tracked per decision:**
- `hand_num`, `action`, `is_following_gto`, `deviation_reason`

**Calculated at end:**
- GTO decisions count & profit
- Deviation decisions count & profit
- Average profit per decision type

### Structured Logging

All game events captured with structured fields for JSON export.

```mermaid
flowchart LR
    subgraph Agents
        agent_log["log_agent_decision()"]
    end
    
    subgraph LogCollector
        collect["CollectorHandler"]
        entries["entries[]"]
    end
    
    subgraph Export
        json["experiment_*.json"]
    end
    
    agent_log --> collect --> entries --> json
```

**Structured fields per decision:**
- Core: `agent_id`, `hand_num`, `action`, `amount`, `confidence`
- Analysis: `gto_analysis`, `exploit_analysis`, `gto_deviation`, `is_following_gto`
- Context: `cards`, `board`, `pot`, `stack`, `street`
- Tools: `tools_used[]`

### Tool Usage Tracker

Records which tools agents invoke during decisions.

**Purpose**: Verify agents are using tools appropriately for mathematical analysis.

**Tracked:**
- Tool name, arguments, hand number
- Per-agent summary counts

---

## Related Documentation

- **[EXPERIMENT.md](EXPERIMENT.md)** - Project goals, hypotheses, and challenges
- **[PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)** - Team delegation and module responsibilities

