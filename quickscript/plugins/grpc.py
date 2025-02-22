from typing import Any, Callable, Optional
from pydantic import BaseModel, Field
from quickscript.quickscript import attach_metadata

NAMESPACE = "grpc"


class GRPCMetadata(BaseModel):
    service_name: str = Field(
        default="QuickScriptService",
        description="The gRPC service name for exposing functions.",
    )
    method: str = Field(
        default="Unary",
        description="The gRPC method type (e.g., 'Unary' or 'Streaming').",
    )


def supports_grpc(
    _func: Optional[Callable[..., Any]] = None,
    *,
    service_name: Optional[str] = None,
    method: Optional[str] = None,
) -> Callable:
    metadata = GRPCMetadata(
        service_name=service_name or "QuickScriptService", method=method or "Unary"
    )

    def decorator(func: Callable) -> Callable:
        attach_metadata(func, namespace=NAMESPACE, data=metadata)
        return func

    return decorator(_func) if _func is not None else decorator
