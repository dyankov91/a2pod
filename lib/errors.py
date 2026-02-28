"""Shared exceptions for the a2pod pipeline."""


class PipelineError(Exception):
    """Raised when a pipeline step fails with a user-facing message."""
