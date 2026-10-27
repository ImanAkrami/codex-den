"""Actionable errors shared by command and interactive interfaces."""


class DenError(Exception):
    """An operation was rejected without intentionally changing user state."""

    def __init__(self, message: str, exit_code: int = 2):
        super().__init__(message)
        self.exit_code = exit_code


class PublicationError(DenError):
    """A write was published, but its directory durability could not be confirmed."""

    registry_committed = False
