import inspect
from typing import AsyncGenerator, Callable, Optional, Any, get_origin, get_type_hints

from pydantic import Field, BaseModel
from quickscript.quickscript import attach_metadata

NAMESPACE = "graphql"


class GraphQLMetadata(BaseModel):
    """
    Metadata for a GraphQL query or mutation.
    """

    name: Optional[str] = Field(
        default=None, description="Optional override for the GraphQL operation name."
    )
    description: Optional[str] = Field(
        default=None,
        description="Optional override for the GraphQL operation description.",
    )
    deprecated: bool = Field(
        default=False, description="Whether the GraphQL operation is deprecated."
    )

    subscription: bool = Field(
        default=False,
        description="Whether the GraphQL operation is a subscription. If true, the operation must be an async queryable generator.",
    )


def supports_graphql(
    _func: Optional[Callable[..., Any]] = None,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    deprecated: bool = False,
    subscription: bool = False,
) -> Callable:
    """
    A decorator that marks a script, queryable, or mutatable as a GraphQL operation.

    If 'subscription' is True, the function must be an async generator whose return annotation
    is an AsyncGenerator. Otherwise, the function must be an async coroutine.
    """
    model = GraphQLMetadata(
        name=name,
        description=description,
        deprecated=deprecated,
        subscription=subscription,
    )

    def decorator(func: Callable) -> Callable:
        # Validate return annotation
        hints = get_type_hints(func)
        if "return" not in hints:
            raise ValueError("Function must have a return type annotation.")
        ret_type = hints["return"]

        if subscription:
            if not inspect.isasyncgenfunction(func):
                raise ValueError(
                    "For subscription operations, the function must be an async generator function."
                )
            if get_origin(ret_type) is not AsyncGenerator:
                raise ValueError(
                    "For subscription operations, the return type annotation must be AsyncGenerator."
                )
        else:
            if not inspect.iscoroutinefunction(func):
                raise ValueError(
                    "Queryable operations must be asynchronous coroutine functions."
                )

        attach_metadata(func, namespace=NAMESPACE, data=model)
        return func

    return decorator(_func) if _func is not None else decorator
