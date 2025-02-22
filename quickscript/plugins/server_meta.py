from pydantic import BaseModel, Field
from typing import Any, Callable, Optional, List

from quickscript.quickscript import attach_metadata

NAMESPACE = "server_meta"


class ServerMeta(BaseModel):
    """
    Common metadata for exposure of a script as a server
    """

    timeout: int = Field(
        default=0,
        description="The timeout for the server in seconds. A value of 0 means no timeout.",
    )
    cache_ttl: int = Field(
        default=0,
        description="The time to live for the cache in seconds. A value of 0 means no caching.",
    )
    tags: List[str] = Field(
        default_factory=list, description="The tags for the server."
    )
    server_description: str = Field(
        default="",
        description="The description for the server. Overrides the function docstring.",
    )
    version: Optional[str] = Field(
        default=None, description="The version for the server."
    )


def server_meta(
    _func: Optional[Callable[..., Any]] = None,
    *,
    timeout: int = 0,
    cache_ttl: int = 0,
    tags: Optional[List[str]] = None,
    server_description: str = "",
    version: Optional[str] = None,
) -> Callable:
    """
    A fundamental decorator needed for various other plugins to work.
    """
    model = ServerMeta(
        timeout=timeout,
        cache_ttl=cache_ttl,
        tags=tags or [],
        server_description=server_description,
        version=version,
    )

    def decorator(func: Callable) -> Callable:
        attach_metadata(func, namespace=NAMESPACE, data=model)
        return func

    return decorator(_func) if _func is not None else decorator
