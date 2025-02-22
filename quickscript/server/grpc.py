import json
import asyncio
import inspect
from grpc import aio, StatusCode, GenericRpcHandler, unary_unary_rpc_method_handler

from quickscript.collect import collect_from_dir, QuickScriptCollection


# Define a generic gRPC handler for QuickScript functions.
class QuickScriptGRPCHandler(GenericRpcHandler):
    def __init__(self, collection: QuickScriptCollection):
        self.collection = collection

    def service(self, handler_call_details):
        # We expose a single method: /QuickScript/Call
        if handler_call_details.method == "/QuickScript/Call":
            return unary_unary_rpc_method_handler(
                self.call_function,
                request_deserializer=lambda x: x,
                response_serializer=lambda x: x,
            )
        return None

    def call_function(self, request, context):
        # Expect request as JSON-encoded bytes with keys 'function_name' and 'args'
        try:
            req = json.loads(request.decode("utf-8"))
            function_name = req.get("function_name")
            args = req.get("args")
        except Exception as e:
            context.set_code(StatusCode.INVALID_ARGUMENT)
            context.set_details(f"Failed to decode request: {e}")
            return b""

        # Find matching function from all categories.
        funcs = (
            self.collection.queryables
            + self.collection.mutatables
            + self.collection.scripts
        )
        func = next((f for f in funcs if f.__name__ == function_name), None)
        if not func:
            context.set_code(StatusCode.NOT_FOUND)
            context.set_details(f"Function '{function_name}' not found.")
            return b""

        try:
            sig = inspect.signature(func)
            # If a positional parameter is expected, pass 'args', otherwise call with no args.
            positional = [
                p
                for p in sig.parameters.values()
                if p.kind
                in (
                    inspect.Parameter.POSITIONAL_ONLY,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                )
            ]
            result = func(args) if positional else func()
            if inspect.iscoroutine(result):
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                result = loop.run_until_complete(result)
        except Exception as e:
            context.set_code(StatusCode.INTERNAL)
            context.set_details(str(e))
            return b""

        # Serialize result: if BaseModel instance then dump as JSON, else assume JSON serializable.
        try:
            from pydantic import BaseModel

            if isinstance(result, BaseModel):
                result_json = result.model_dump_json()
            else:
                result_json = json.dumps(result)
        except Exception as e:
            context.set_code(StatusCode.INTERNAL)
            context.set_details(f"Error serializing result: {e}")
            return b""

        return result_json.encode("utf-8")


async def serve_grpc_async(collection: QuickScriptCollection, port: int):
    server = aio.server()
    handler = QuickScriptGRPCHandler(collection)
    server.add_generic_rpc_handlers((handler,))
    listen_addr = f"[::]:{port}"
    server.add_insecure_port(listen_addr)
    print(f"gRPC server listening on {listen_addr}")
    await server.start()
    await server.wait_for_termination()


def run_grpc_server(collection: QuickScriptCollection, port: int = 50051) -> None:
    asyncio.run(serve_grpc_async(collection, port))


def run_grpc_server_from_path(path: str, port: int = 50051) -> None:
    import os

    if os.path.isdir(path):
        collection = collect_from_dir(path)
    elif os.path.isfile(path):
        from quickscript.collect import collect_from_file

        collection = collect_from_file(path)
    else:
        raise ValueError(f"Invalid path: {path}")
    run_grpc_server(collection, port)
