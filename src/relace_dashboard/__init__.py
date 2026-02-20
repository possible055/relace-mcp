def main() -> None:
    """Entry point for `relace-dashboard`.

    The dashboard depends on optional UI packages (installed via `relace-mcp[tools]`).
    Keep imports lazy so `relace-mcp` remains usable without those extras.
    """
    try:
        from .app import main as _main
    except ModuleNotFoundError as exc:
        missing = (exc.name or "").split(".", 1)[0]
        if missing in {"textual", "rich"}:
            raise SystemExit(
                "relace-dashboard requires optional dependencies.\n"
                "Install with: pip install relace-mcp[tools]"
            ) from exc
        raise
    _main()


__all__ = ["main"]
