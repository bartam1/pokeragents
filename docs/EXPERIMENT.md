# PokerAgents: Shared Knowledge & Agent Architecture Experiment

## Executive Summary

This proof-of-concept explores how AI agents can benefit from **shared knowledge** and whether different **agent architectures** affect decision quality. Using poker as a testbed, we investigate if agents with access to accumulated opponent intelligence outperform those without, and whether specialized multi-agent systems make better decisions than simpler single-agent approaches.

---

## The Core Idea

### Shared Knowledge Fabric

Imagine a system where multiple AI agents contribute to and benefit from a **common knowledge base**. As agents interact with users, systems, or opponents, they accumulate insights that become available to all agents in the organization.

**Key Question**: Can agents with access to shared historical knowledge outperform agents operating in isolation?

In our poker experiment:
- Some agents have access to **accumulated opponent statistics** (play styles, tendencies, weaknesses)
- Other agents start fresh with **no prior knowledge**
- We measure which group performs better over many games

### Architecture Comparison

Beyond shared knowledge, we also explore whether the **structure** of an AI agent matters:

| Approach | Description |
|----------|-------------|
| **Single Agent** | One LLM prompt handles all reasoning (strategy + exploitation) |
| **Multi-Agent Ensemble** | Specialized agents collaborate (one for math, one for opponent analysis, one for final decision) |

**Key Question**: Does separating concerns into specialized agents improve decision quality, or does the added complexity hurt more than it helps?

---

## What We're Trying to Prove

### Hypothesis 1: Shared Knowledge Improves Performance

> Agents with access to accumulated knowledge about their environment (opponents, in this case) will significantly outperform agents without such knowledge.

**Why This Matters**: If true, organizations should invest in "knowledge fabric" systems that capture and share learnings across AI agents, rather than deploying isolated agents that must learn everything from scratch.

### Hypothesis 2: Architecture May Matter Less Than Knowledge

> The benefit of shared knowledge likely outweighs architectural differences between single-agent and multi-agent approaches.

**Why This Matters**: Simpler architectures are easier to maintain, debug, and deploy. If a single well-informed agent performs as well as a complex multi-agent system, the simpler approach wins.

### Hypothesis 3: GTO Deviations Should Be Tracked

> When agents deviate from mathematically optimal play, we need to measure whether those deviations are actually profitable.

**Why This Matters**: LLMs often "think" they're making smart exploitative plays when they're actually just making errors. Without tracking, we can't distinguish good deviations from bad ones.

---

## Why Poker?

Poker serves as an ideal testbed for AI agent research:

| Property | Benefit for Research |
|----------|---------------------|
| **Clear success metric** | Win/loss is unambiguous |
| **Information asymmetry** | Agents must reason with incomplete information |
| **Opponent modeling matters** | Knowledge about others provides measurable advantage |
| **Mathematical baseline exists** | Game Theory Optimal (GTO) play provides a benchmark |
| **Repeated interactions** | Statistical significance emerges over many games |

---

## Key Challenges

### 1. Sample Size Requirements

**The Problem**: Poker has high variance. A bad player can beat a good player in any single hand or even tournament. Meaningful results require hundreds or thousands of games.

**Implication**: Running enough experiments to draw conclusions requires significant compute time and API costs. Quick demos don't prove anything statistically.

### 2. Prompt Engineering Complexity

**The Problem**: Getting an LLM to make good poker decisions requires carefully crafted prompts. Too vague and decisions are random. Too rigid and the LLM ignores context.

**Approach**: Simple guidelines that let the LLM reason, rather than rigid rules it might ignore.

### 3. Fair Comparison Design

**The Problem**: To compare architectures fairly, we must control for other variables. If one agent has better knowledge than another, we're not testing architecture - we're testing knowledge.

**Solution**: Both experimental agents receive identical shared knowledge. Only the decision-making structure differs.

### 4. Measuring "Good" Deviations

**The Problem**: When an agent deviates from optimal play, is it a smart exploit or a mistake? We can only tell by tracking outcomes over many decisions.

**Approach**: Track every deviation, record whether it was profitable, and analyze patterns. Are deviations when opponent has 100+ hands of history more profitable than early deviations?

### 5. Knowledge Quality

**The Problem**: Shared knowledge is only valuable if it's accurate. If the accumulated statistics are based on too few observations, they mislead rather than help.

**Solution**: Build in sample size awareness. Don't exploit based on fewer than 50 observations. Display confidence levels with all statistics.

### 6. Latency vs Quality Trade-off

**The Problem**: Multi-agent systems require multiple LLM calls per decision. Is the quality improvement worth the added latency and cost?

**Measurement**: Track decision quality (measured by outcomes) against API calls per decision.

### 7. Reducing Variance: EV Chips

**The Problem**: Poker has high variance. With small sample sizes, an agent making poor decisions can win through luck, while a skilled agent can lose to bad beats. Actual chip results don't reliably indicate decision quality.

**Solution**: Track **EV chips** (Expected Value) instead of actual chip results at showdown.

| Metric | Measures | Example: You have AA vs opponent's 72o, you lose |
|--------|----------|--------------------------------------------------|
| Actual chips | Real outcome | -100 chips (lost the hand) |
| EV chips | Decision quality | +70 chips (you were 85% to win) |

**How It Works**:
- EV is calculated at **showdown** when both hands are revealed
- For each decision, calculate equity at that point: `EV = (equity × pot) - investment`
- Track EV chips won/lost instead of actual chips

**Benefits**:
- Removes luck from agent comparison
- Shows true decision-making quality regardless of card outcomes
- Makes smaller sample sizes more meaningful
- Faster iteration on prompt improvements

---

## Experiment Structure

### Agents in the Experiment

| Agent | Knowledge Access | Architecture | Purpose |
|-------|-----------------|--------------|---------|
| A, B, C | None (fixed strategy) | Rule-based | Consistent baselines with exploitable patterns |
| D | Shared knowledge | Single LLM | Test simple architecture with knowledge |
| E | Shared knowledge | Multi-agent ensemble | Test complex architecture with knowledge |

### What We Measure

1. **Tournament Placement**: Who finishes 1st, 2nd, 3rd, etc.?
2. **Win Rate**: What percentage of tournaments does each agent win?
3. **GTO Deviation Rate**: How often do agents deviate from optimal play?
4. **Deviation Profitability**: When deviating, do they win or lose money?
5. **EV Chips** (future): Expected value of decisions at showdown, removing variance from comparison

### Building Shared Knowledge

Before running comparison experiments, we run **calibration tournaments** where agents observe opponent behavior and accumulate statistics. This builds the shared knowledge base that informed agents will use.

---

## Summary

This project explores two interconnected questions:

1. **Does shared knowledge help?** Can agents perform better when they have access to accumulated intelligence about their environment?

2. **Does architecture matter?** Is there a meaningful difference between simple single-agent and complex multi-agent approaches?

The key challenges are getting enough data for statistical significance, engineering effective prompts, and measuring whether deviations from optimal play are actually smart or just errors.

If successful, this work validates the "knowledge fabric" concept and provides guidance on when architectural complexity is worth the investment.

---

## Related Documentation

- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Technical architecture and data flows
- **[PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)** - Team delegation and module responsibilities

