from typing import Callable, Optional, Any

from pydantic import Field, BaseModel
from quickscript.quickscript import attach_metadata

NAMESPACE = "rest"


class RESTMetadata(BaseModel):
    """
    Metadata for a REST endpoint.
    """

    prefix: Optional[str] = Field(
        default=None, description="The path prefix for the REST endpoint."
    )
    method: Optional[str] = Field(
        default=None,
        description="The HTTP method for the REST endpoint, overrides the default method.",
    )
    path: Optional[str] = Field(
        default=None, description="The full path for the REST endpoint."
    )
    deprecated: bool = Field(
        default=False, description="Whether the REST endpoint is deprecated."
    )


def supports_rest(
    _func: Optional[Callable[..., Any]] = None,
    *,
    prefix: Optional[str] = None,
    method: Optional[str] = None,
    path: Optional[str] = None,
    deprecated: bool = False,
) -> Callable:
    """
    A decorator that marks a function as a REST endpoint.
    """

    def decorator(func: Callable) -> Callable:
        attach_metadata(
            func,
            NAMESPACE,
            RESTMetadata(
                prefix=prefix, method=method, path=path, deprecated=deprecated
            ),
        )

        return func

    return decorator(_func) if _func else decorator
