from pydantic import BaseModel, Field
from typing import Any, Callable, Optional

from quickscript.quickscript import attach_metadata


class ZeroMQMetadata(BaseModel):
    """
    Minimal metadata for a ZeroMQ endpoint.
    Only declares the intended ZeroMQ communication pattern.
    """

    socket_mode: str = Field(
        default="REP",
        description="Intended ZeroMQ socket mode (e.g., 'REP', 'PUB', or 'SUB').",
    )


def supports_zeromq(
    _func: Optional[Callable[..., Any]] = None,
    *,
    socket_mode: str = "REP",
) -> Callable:
    """
    Decorator marking a function as supporting ZeroMQ communication.

    """
    model = ZeroMQMetadata(socket_mode=socket_mode)

    def decorator(func: Callable) -> Callable:
        attach_metadata(func, namespace="zeromq", data=model)
        return func

    return decorator(_func) if _func is not None else decorator
