import uuid
from contextvars import ContextVar

trace_id: ContextVar[str] = ContextVar("trace_id", default="")
tool_name: ContextVar[str] = ContextVar("tool_name", default="")

# Minimal call chain tracking (max depth 10 to prevent unbounded growth)
_call_chain: ContextVar[tuple[str, ...]] = ContextVar("_call_chain", default=())
_MAX_CHAIN_DEPTH = 10


def new_trace_id() -> str:
    tid = f"t-{uuid.uuid4().hex[:12]}"
    trace_id.set(tid)
    return tid


def get_trace_id() -> str:
    current = trace_id.get()
    if current:
        return current
    return new_trace_id()


def set_tool_context(name: str, tid: str | None = None) -> str:
    tool_name.set(name)
    if tid:
        trace_id.set(tid)
        return tid
    return new_trace_id()


def clear_context() -> None:
    trace_id.set("")
    tool_name.set("")
    _call_chain.set(())


def get_call_chain() -> tuple[str, ...]:
    """Get current call chain (for debug events)."""
    return _call_chain.get()


def push_call_frame(frame: str) -> None:
    """Push frame to call chain (limit depth)."""
    chain = _call_chain.get()
    if len(chain) < _MAX_CHAIN_DEPTH:
        _call_chain.set(chain + (frame,))


def pop_call_frame() -> None:
    """Pop last frame from call chain."""
    chain = _call_chain.get()
    if chain:
        _call_chain.set(chain[:-1])
