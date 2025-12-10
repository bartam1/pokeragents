"""
Utility functions for agent operations.

Provides shared functionality used across different agent implementations.
"""
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from backend.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class ToolUsageTracker:
    """Tracks tool usage across all agents during a session."""

    # Stores tool calls per agent: {agent_name: [{tool_name, arguments, hand_num}]}
    _calls: dict[str, list[dict[str, Any]]] = field(default_factory=lambda: defaultdict(list))

    # Summary counts: {agent_name: {tool_name: count}}
    _summary: dict[str, dict[str, int]] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(int))
    )

    # Current hand number (set by orchestrator)
    current_hand: int = 0

    def record(self, agent_name: str, tool_name: str, arguments: str = "") -> None:
        """Record a tool call."""
        self._calls[agent_name].append(
            {
                "tool": tool_name,
                "hand": self.current_hand,
                "arguments": arguments,
            }
        )
        self._summary[agent_name][tool_name] += 1

    def record_from_result(self, agent_name: str, result) -> list[str]:
        """Record all tool calls from a RunResult and return tool names."""
        tools = extract_tools_used(result)
        details = get_detailed_tool_usage(result)

        for detail in details:
            self.record(agent_name, detail["name"], detail.get("arguments", ""))

        return tools

    def get_summary(self) -> dict[str, dict[str, int]]:
        """Get summary of tool usage counts per agent."""
        return {agent: dict(tools) for agent, tools in self._summary.items()}

    def get_all_calls(self) -> dict[str, list[dict]]:
        """Get all recorded tool calls per agent."""
        return dict(self._calls)

    def get_total_calls(self) -> int:
        """Get total number of tool calls across all agents."""
        return sum(len(calls) for calls in self._calls.values())

    def reset(self) -> None:
        """Reset all tracking data."""
        self._calls = defaultdict(list)
        self._summary = defaultdict(lambda: defaultdict(int))
        self.current_hand = 0

    def to_dict(self) -> dict:
        """Export tracker data for JSON serialization."""
        return {
            "summary": self.get_summary(),
            "total_calls": self.get_total_calls(),
            "calls_by_agent": {agent: calls for agent, calls in self._calls.items()},
        }


# Global tracker instance
tool_tracker = ToolUsageTracker()


@dataclass
class GTODeviationTracker:
    """Tracks GTO deviations and their outcomes across agents."""

    # Deviations: {agent_id: [{hand_num, action, reason, is_deviation}]}
    _decisions: dict[str, list[dict[str, Any]]] = field(default_factory=lambda: defaultdict(list))

    # Hand outcomes: {hand_num: {agent_id: profit/loss}}
    _hand_outcomes: dict[int, dict[str, float]] = field(default_factory=lambda: defaultdict(dict))

    # Current hand number
    current_hand: int = 0

    def record_decision(
        self,
        agent_id: str,
        hand_num: int,
        action: str,
        is_following_gto: bool,
        deviation_reason: str = "",
        amount: float | None = None,
    ) -> None:
        """Record a decision with GTO deviation info."""
        self._decisions[agent_id].append(
            {
                "hand": hand_num,
                "action": action,
                "amount": amount,
                "is_following_gto": is_following_gto,
                "deviation_reason": deviation_reason,
            }
        )

    def record_hand_outcome(self, hand_num: int, agent_id: str, profit: float) -> None:
        """Record the profit/loss for an agent in a hand."""
        self._hand_outcomes[hand_num][agent_id] = profit

    def get_agent_stats(self, agent_id: str) -> dict:
        """Get deviation statistics for a specific agent."""
        decisions = self._decisions.get(agent_id, [])

        gto_count = sum(1 for d in decisions if d["is_following_gto"])
        deviation_count = sum(1 for d in decisions if not d["is_following_gto"])
        total = len(decisions)

        # Calculate profit/loss for GTO vs deviation decisions
        gto_hands = {d["hand"] for d in decisions if d["is_following_gto"]}
        deviation_hands = {d["hand"] for d in decisions if not d["is_following_gto"]}

        gto_profit = sum(self._hand_outcomes.get(h, {}).get(agent_id, 0) for h in gto_hands)
        deviation_profit = sum(
            self._hand_outcomes.get(h, {}).get(agent_id, 0) for h in deviation_hands
        )

        return {
            "total_decisions": total,
            "gto_decisions": gto_count,
            "deviation_decisions": deviation_count,
            "deviation_rate": deviation_count / total if total > 0 else 0,
            "gto_profit": gto_profit,
            "deviation_profit": deviation_profit,
            "gto_avg_profit": gto_profit / len(gto_hands) if gto_hands else 0,
            "deviation_avg_profit": deviation_profit / len(deviation_hands)
            if deviation_hands
            else 0,
        }

    def get_all_stats(self) -> dict[str, dict]:
        """Get deviation statistics for all agents."""
        return {agent_id: self.get_agent_stats(agent_id) for agent_id in self._decisions}

    def reset(self) -> None:
        """Reset all tracking data."""
        self._decisions = defaultdict(list)
        self._hand_outcomes = defaultdict(dict)
        self.current_hand = 0

    def to_dict(self) -> dict:
        """Export tracker data for JSON serialization."""
        all_stats = self.get_all_stats()

        # Calculate totals across all agents
        total_gto = sum(s["gto_decisions"] for s in all_stats.values())
        total_deviation = sum(s["deviation_decisions"] for s in all_stats.values())
        total_gto_profit = sum(s["gto_profit"] for s in all_stats.values())
        total_deviation_profit = sum(s["deviation_profit"] for s in all_stats.values())

        return {
            "summary": {
                "total_gto_decisions": total_gto,
                "total_deviation_decisions": total_deviation,
                "overall_deviation_rate": total_deviation / (total_gto + total_deviation)
                if (total_gto + total_deviation) > 0
                else 0,
                "total_gto_profit": total_gto_profit,
                "total_deviation_profit": total_deviation_profit,
            },
            "by_agent": all_stats,
        }


# Global deviation tracker instance
deviation_tracker = GTODeviationTracker()


def extract_tools_used(result) -> list[str]:
    """
    Extract the list of tools that were called during an agent run.

    Works with OpenAI Agents SDK RunResult objects by inspecting the
    `new_items` attribute for tool call results.

    Args:
        result: The RunResult from Runner.run()

    Returns:
        List of tool names that were invoked
    """
    tools_used = []

    if not hasattr(result, "new_items"):
        return tools_used

    for item in result.new_items:
        # ToolCallItem contains raw_item with the function name
        if type(item).__name__ == "ToolCallItem":
            if hasattr(item, "raw_item") and hasattr(item.raw_item, "name"):
                tools_used.append(item.raw_item.name)

    return tools_used


def log_tools_used(
    agent_name: str, result, log_level: str = "info", track: bool = True
) -> list[str]:
    """
    Extract and log tools used during an agent run.

    Convenience function that combines extraction with logging.

    Args:
        agent_name: Name/ID of the agent for logging context
        result: The RunResult from Runner.run()
        log_level: Logging level ("info" or "debug")
        track: Whether to record in the global tool_tracker

    Returns:
        List of tool names that were invoked
    """
    if track:
        tools_used = tool_tracker.record_from_result(agent_name, result)
    else:
        tools_used = extract_tools_used(result)

    if tools_used:
        msg = f"[{agent_name}] 🔧 Tools used: {', '.join(tools_used)}"
        if log_level == "debug":
            logger.debug(msg)
        else:
            logger.info(msg)
    else:
        logger.debug(f"[{agent_name}] No tools called")

    return tools_used


def get_detailed_tool_usage(result) -> list[dict]:
    """
    Get detailed information about tools used during an agent run.

    Useful for analytics, debugging, and tracking tool effectiveness.

    Args:
        result: The RunResult from Runner.run()

    Returns:
        List of dicts with tool details: name, arguments, call_id
    """
    tool_details = []

    if not hasattr(result, "new_items"):
        return tool_details

    for item in result.new_items:
        # ToolCallItem contains raw_item with function details
        if type(item).__name__ == "ToolCallItem":
            if hasattr(item, "raw_item"):
                raw = item.raw_item
                tool_details.append(
                    {
                        "name": getattr(raw, "name", "unknown"),
                        "arguments": getattr(raw, "arguments", ""),
                        "call_id": getattr(raw, "call_id", None),
                    }
                )

    return tool_details
