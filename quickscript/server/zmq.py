import asyncio
import json
from pydantic import BaseModel
import zmq
import os
import zmq.asyncio
from typing import Any, Dict, List, Optional
from quickscript.collect import (
    QuickScriptCollection,
    collect_from_dir,
    collect_from_file,
)

_default_addresses = {
    "REP": "tcp://*:5555",
    "PUB": "tcp://*:5556",
    "SUB": "tcp://*:5557",
}


async def run_zeromq_server(
    collections: List[QuickScriptCollection],
    context: Optional[zmq.asyncio.Context] = None,
) -> None:
    """
    Run a ZeroMQ server that exposes the functions from the collections.
    """
    if context is None:
        context = zmq.asyncio.Context()

    # Group functions by their ZeroMQ metadata
    sockets: Dict[str, List[tuple[zmq.Socket, Any]]] = {}

    for collection in collections:
        for func in collection.queryables + collection.mutatables:
            if (
                not hasattr(func, "__qs_metadata__")
                or "zeromq" not in func.__qs_metadata__
            ):
                continue

            meta = func.__qs_metadata__["zeromq"]
            socket_mode = meta["socket_mode"]
            socket_key = f"{socket_mode}"

            if socket_key not in sockets:
                socket = context.socket(getattr(zmq, socket_mode))
                sockets[socket_key] = []

            sockets[socket_key].append((socket, func))
            print(f"Added {func.__name__} to {socket_mode} socket at {socket_key}")

    if not sockets:
        raise ValueError("No ZeroMQ-enabled functions found in collections")

    print(f"Sockets: {sockets}")

    for socket_key, socket_funcs in sockets.items():
        socket.bind(_default_addresses[socket_key])
        print(f"Bound {socket_key} to {_default_addresses[socket_key]}")

    # Create tasks for each socket
    tasks = []
    for socket_funcs in sockets.values():
        for socket, func in socket_funcs:
            if socket.type == zmq.REP:
                tasks.append(handle_rep_socket(socket, func))
            elif socket.type == zmq.PUB:
                tasks.append(handle_pub_socket(socket, func))
            # Add more patterns as needed

    await asyncio.gather(*tasks)


async def handle_rep_socket(socket: zmq.Socket, func: Any) -> None:
    """Handle REQ/REP pattern"""
    while True:
        try:
            message = await socket.recv_string()
            if func.__qs_args_pydantic_type__:
                args = func.__qs_args_pydantic_type__.model_validate_json(message)
            else:
                args = None

            # Execute function
            if asyncio.iscoroutinefunction(func):
                result = await func(args) if args else await func()
            else:
                result = func(args) if args else func()

            if isinstance(result, BaseModel):
                final = result.model_dump_json()
            else:
                final = result

            # Send response
            await socket.send_string(final)
        except Exception as e:
            await socket.send_string(json.dumps({"error": str(e)}))


async def handle_pub_socket(socket: zmq.Socket, func: Any) -> None:
    """Handle PUB/SUB pattern"""
    meta = func.__qs_metadata__["zeromq"]
    topic = meta.get("topic", "")

    while True:
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func()
            else:
                result = func()

            message = json.dumps(result)
            await socket.send_string(f"{topic} {message}")
            await asyncio.sleep(1)  # Adjust as needed
        except Exception as e:
            print(f"Error in PUB socket: {e}")
            await asyncio.sleep(1)


def run_zeromq_server_from_path(
    path: str, context: Optional[zmq.asyncio.Context] = None
) -> None:
    """
    Run a ZeroMQ server from a path containing QuickScript functions.
    """
    if os.path.isdir(path):
        collections = [collect_from_dir(path)]
    elif os.path.isfile(path):
        collections = [collect_from_file(path)]
    else:
        raise ValueError(f"Invalid path: {path}")

    asyncio.run(run_zeromq_server(collections, context))
