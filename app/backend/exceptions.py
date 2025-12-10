"""
Domain exceptions for the Poker POC.
"""


class PokerError(Exception):
    """Base exception for poker-related errors."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class GameError(PokerError):
    """Error related to game state or actions."""

    pass


class AgentError(PokerError):
    """Error related to AI agents."""

    pass


class TournamentError(PokerError):
    """Error related to tournament operations."""

    pass
