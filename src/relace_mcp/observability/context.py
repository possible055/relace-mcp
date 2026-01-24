import uuid
from contextvars import ContextVar

trace_id: ContextVar[str] = ContextVar("trace_id", default="")
tool_name: ContextVar[str] = ContextVar("tool_name", default="")


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
