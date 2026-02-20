class ExternalCLIError(RuntimeError):
    """Structured error for external CLI backend failures.

    Attributes:
        backend: Name of the backend (e.g. "chunkhound", "codanna").
        kind: Error category for programmatic handling.
        command: CLI command that failed.
    """

    def __init__(self, *, backend: str, kind: str, message: str, command: list[str] | None = None):
        super().__init__(message)
        self.backend = backend
        self.kind = kind
        self.command = command or []
