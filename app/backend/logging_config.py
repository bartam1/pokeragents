"""
Logging configuration for the Poker POC with structured logging support.
"""
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class LogCollector:
    """Collects structured log messages for JSON export."""
    
    entries: list[dict[str, Any]] = field(default_factory=list)
    enabled: bool = True
    
    def add(self, record: logging.LogRecord) -> None:
        """Add a log record to the collection with structured data."""
        if not self.enabled:
            return
        
        # Base entry with standard fields
        entry = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add any extra structured fields passed via logger.info(..., extra={...})
        # Common fields: agent_id, hand_num, action, cards, etc.
        structured_fields = [
            # Core identifiers
            'agent_id', 'hand_num', 'event_type',
            # Game state
            'cards', 'board', 'pot', 'stack', 'position', 'street',
            # Action details
            'action', 'amount', 'to_call', 'min_raise', 'max_raise',
            # Reasoning breakdown (structured)
            'gto_analysis', 'exploit_analysis', 'gto_deviation', 
            'is_following_gto', 'deviation_reason',
            # Confidence and decision
            'confidence', 'decision',
            # Tool usage
            'tools_used',
            # Opponent info
            'opponent_stats', 'target_opponent',
            # Hand result
            'winner', 'pot_won', 'showdown',
        ]
        for key in structured_fields:
            if hasattr(record, key):
                entry[key] = getattr(record, key)
        
        self.entries.append(entry)
    
    def get_entries(self) -> list[dict[str, Any]]:
        """Get all collected log entries."""
        return self.entries
    
    def get_entries_by_agent(self, agent_id: str) -> list[dict[str, Any]]:
        """Get log entries for a specific agent."""
        return [e for e in self.entries if e.get('agent_id') == agent_id]
    
    def get_entries_by_hand(self, hand_num: int) -> list[dict[str, Any]]:
        """Get log entries for a specific hand."""
        return [e for e in self.entries if e.get('hand_num') == hand_num]
    
    def get_entries_by_type(self, event_type: str) -> list[dict[str, Any]]:
        """Get log entries by event type."""
        return [e for e in self.entries if e.get('event_type') == event_type]
    
    def clear(self) -> None:
        """Clear all collected entries."""
        self.entries = []
    
    def to_dict(self) -> dict:
        """Export for JSON serialization."""
        return {
            "total_entries": len(self.entries),
            "entries": self.entries,
        }


# Global log collector instance
log_collector = LogCollector()


class CollectorHandler(logging.Handler):
    """Custom handler that collects logs to the global collector."""
    
    def emit(self, record: logging.LogRecord) -> None:
        log_collector.add(record)


class StructuredFormatter(logging.Formatter):
    """Formatter that outputs JSON for structured logging to console."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add extra fields
        for key in ['agent_id', 'hand_num', 'action', 'amount', 'event_type']:
            if hasattr(record, key):
                log_entry[key] = getattr(record, key)
        
        return json.dumps(log_entry)


class HumanReadableFormatter(logging.Formatter):
    """Human-readable formatter for console output."""
    
    def format(self, record: logging.LogRecord) -> str:
        # Build prefix with structured context if available
        prefix_parts = []
        if hasattr(record, 'hand_num'):
            prefix_parts.append(f"H{record.hand_num}")
        if hasattr(record, 'agent_id'):
            prefix_parts.append(f"[{record.agent_id}]")
        
        prefix = " ".join(prefix_parts)
        if prefix:
            prefix = f"{prefix} "
        
        # Format timestamp
        timestamp = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
        
        return f"{timestamp} | {record.levelname:<8} | {record.name} | {prefix}{record.getMessage()}"


def setup_logging(
    level: str = "INFO",
    collect_logs: bool = True,
    json_console: bool = False,
) -> None:
    """Set up logging configuration.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        collect_logs: Whether to collect logs for JSON export
        json_console: If True, output JSON to console; otherwise human-readable
    """
    # Create console handler with appropriate formatter
    console_handler = logging.StreamHandler(sys.stdout)
    if json_console:
        console_handler.setFormatter(StructuredFormatter())
    else:
        console_handler.setFormatter(HumanReadableFormatter())
    
    handlers: list[logging.Handler] = [console_handler]
    
    # Add collector handler if enabled
    if collect_logs:
        log_collector.enabled = True
        log_collector.clear()  # Start fresh
        handlers.append(CollectorHandler())
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))
    
    # Remove existing handlers and add new ones
    root_logger.handlers.clear()
    for handler in handlers:
        root_logger.addHandler(handler)

    # Suppress noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.ERROR)
    logging.getLogger("openai.agents").setLevel(logging.ERROR)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)


# Convenience functions for structured logging
def log_agent_decision(
    logger: logging.Logger,
    agent_id: str,
    hand_num: int,
    action: str,
    amount: float | None = None,
    cards: str | None = None,
    confidence: float | None = None,
    gto_analysis: str | None = None,
    exploit_analysis: str | None = None,
    gto_deviation: str | None = None,
    is_following_gto: bool | None = None,
    tools_used: list[str] | None = None,
    pot: float | None = None,
    stack: float | None = None,
    board: str | None = None,
    street: str | None = None,
) -> None:
    """Log an agent decision with structured data."""
    extra: dict[str, Any] = {
        'event_type': 'decision',
        'agent_id': agent_id,
        'hand_num': hand_num,
        'action': action,
    }
    if amount is not None:
        extra['amount'] = amount
    if cards:
        extra['cards'] = cards
    if confidence is not None:
        extra['confidence'] = confidence
    if gto_analysis:
        extra['gto_analysis'] = gto_analysis
    if exploit_analysis:
        extra['exploit_analysis'] = exploit_analysis
    if gto_deviation:
        extra['gto_deviation'] = gto_deviation
    if is_following_gto is not None:
        extra['is_following_gto'] = is_following_gto
    if tools_used:
        extra['tools_used'] = tools_used
    if pot is not None:
        extra['pot'] = pot
    if stack is not None:
        extra['stack'] = stack
    if board:
        extra['board'] = board
    if street:
        extra['street'] = street
    
    msg = f"=> {action}"
    if amount:
        msg += f" {amount}"
    if confidence:
        msg += f" (conf: {confidence:.2f})"
    
    logger.info(msg, extra=extra)


def log_hand_start(
    logger: logging.Logger,
    hand_num: int,
    players: list[str],
    blinds: tuple[int, int],
    stacks: dict[str, float],
) -> None:
    """Log the start of a new hand with structured data."""
    extra = {
        'event_type': 'hand_start',
        'hand_num': hand_num,
        'players': players,
        'blinds': blinds,
        'stacks': stacks,
    }
    logger.info(f"--- Hand #{hand_num} ---", extra=extra)


def log_street(
    logger: logging.Logger,
    hand_num: int,
    street: str,
    board: str,
    pot: float,
) -> None:
    """Log a street transition with structured data."""
    extra = {
        'event_type': 'street',
        'hand_num': hand_num,
        'street': street,
        'board': board,
        'pot': pot,
    }
    logger.info(f"[{street}] Board: {board} | Pot: {pot}", extra=extra)


def log_tool_usage(
    logger: logging.Logger,
    agent_id: str,
    hand_num: int,
    tools_used: list[str],
) -> None:
    """Log tool usage with structured data."""
    if not tools_used:
        return
    extra = {
        'event_type': 'tool_usage',
        'agent_id': agent_id,
        'hand_num': hand_num,
        'tools_used': tools_used,
    }
    logger.info(f"🔧 Tools used: {', '.join(tools_used)}", extra=extra)
