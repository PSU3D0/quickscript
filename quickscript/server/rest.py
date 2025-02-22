from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.requests import Request
from starlette.routing import Route
import inspect
from typing import List, Callable
from quickscript.collect import QuickScriptCollection
from pydantic import BaseModel

from quickscript.quickscript import ContextItem, push_context_item


def _wrap_rest_endpoint(func: Callable) -> Callable:
    """
    Returns an async endpoint function for Starlette that wraps a quickscript function.
    If the function has a positional argument (a Pydantic model), the JSON body is parsed and validated.
    """

    async def endpoint(request: Request):
        arg_model = getattr(func, "__qs_args_pydantic_type__", None)

        with push_context_item(ContextItem("request", value=request)):
            if arg_model:
                try:
                    body = await request.json()
                except Exception as e:
                    return JSONResponse(
                        {"error": "Invalid JSON body", "detail": str(e)},
                        status_code=400,
                    )
                try:
                    args_instance = arg_model.model_validate(body)
                except Exception as e:
                    return JSONResponse(
                        {"error": "Validation error", "detail": str(e)},
                        status_code=422,
                    )
                result = (
                    await func(args_instance)
                    if inspect.iscoroutinefunction(func)
                    else func(args_instance)
                )
            else:
                result = await func() if inspect.iscoroutinefunction(func) else func()
            # If result is a Pydantic model, return its dict; otherwise, assume it is JSON-serializable.
            if isinstance(result, BaseModel):
                return JSONResponse(result.model_dump())
            return JSONResponse(result)

    return endpoint


def create_rest_app(collections: List[QuickScriptCollection]) -> Starlette:
    """
    Creates and returns a Starlette app that exposes QuickScript functions as REST endpoints.
    Each function is available as a POST endpoint at /<function_name>.
    """
    routes = []
    combined = QuickScriptCollection(name="rest_combined")
    for coll in collections:
        combined.add_collection(coll)
    available_funcs = combined.queryables + combined.mutatables + combined.scripts
    for func in available_funcs:
        route_path = f"/{func.__name__}"
        method = "POST" if func.__qs_mode__ == "mutatable" else "GET"
        routes.append(Route(route_path, _wrap_rest_endpoint(func), methods=[method]))

    # Optional: List available endpoints at the root.
    async def list_endpoints(request: Request):
        endpoints = [f.__name__ for f in available_funcs]
        return JSONResponse({"endpoints": endpoints})

    routes.append(Route("/", list_endpoints, methods=["GET"]))
    return Starlette(routes=routes)


def run_rest_server(
    collections: List[QuickScriptCollection],
    host: str = "0.0.0.0",
    port: int = 8001,  # choose a port (different from GraphQL, if needed)
) -> None:
    """
    Runs the REST server using uvicorn.
    """
    from uvicorn import run

    app = create_rest_app(collections)
    run(app, host=host, port=port)
