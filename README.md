# Poker Agents Research

Research project exploring how AI agents can benefit from **shared knowledge** and whether different **agent architectures** affect decision quality.

## Core Questions

1. **Does shared knowledge help?** Can agents perform better when they have access to accumulated intelligence about their environment (opponents)?

2. **Does architecture matter?** Is there a meaningful difference between simple single-agent and complex multi-agent ensemble approaches?

## The Experiment

Using poker as a testbed, we compare:

| Agent | Knowledge | Architecture |
|-------|-----------|--------------|
| **Agent D** | Shared opponent statistics | Single LLM |
| **Agent E** | Shared opponent statistics | Multi-agent ensemble (GTO + Exploit + Decision) |

Both agents receive **identical knowledge** - only the decision-making structure differs.

## Key Concept: Shared Knowledge Fabric

Imagine a system where multiple AI agents contribute to and benefit from a **common knowledge base**. As agents interact with opponents, they accumulate insights that become available to all agents.

This project validates whether such "knowledge fabric" systems provide meaningful advantages.

## Documentation

- **[EXPERIMENT.md](docs/EXPERIMENT.md)** - Goals, hypotheses, and challenges
- **[ARCHITECTURE.md](docs/ARCHITECTURE.md)** - Technical architecture and data flows
- **[PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md)** - Team delegation and module responsibilities

## Status

🔬 **Active Research** - Running experiments to gather statistically significant results.

