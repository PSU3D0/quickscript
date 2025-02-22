import argparse
import os
import sys
import inspect
import asyncio
from quickscript.cli import cli_run
from quickscript.collect import collect_from_dir


def list_scripts(scripts_dir: str) -> None:
    """Discover scripts in the given directory and pretty-print their interface."""
    collection = collect_from_dir(scripts_dir)
    if not collection.scripts:
        print(f"No scripts found in directory: {scripts_dir}")
        return
    print("Available scripts:")
    for script_fn in collection.scripts:
        sig = inspect.signature(script_fn)
        print(f"- {script_fn.__name__}{sig}")
        if script_fn.__doc__:
            print(f"   {script_fn.__doc__}")


def run_script(script_name: str, scripts_dir: str, extra_args: list) -> None:
    """Find and run the script with the given name.

    Extra arguments (if any) are available for future processing.
    """
    collection = collect_from_dir(scripts_dir)
    matching = [s for s in collection.scripts if s.__name__ == script_name]
    if not matching:
        print(f"Script '{script_name}' not found in directory: {scripts_dir}")
        sys.exit(1)
    script_fn = matching[0]
    # Note: if needed, you can process extra_args here to pass to the script.
    if inspect.iscoroutinefunction(script_fn):
        asyncio.run(script_fn())
    else:
        script_fn()


def run_graphql(path: str, host: str, port: int) -> None:
    """Launch the GraphQL server using the given discovery path and network options."""
    from quickscript.server.graphql import run_graphql_server_from_path

    run_graphql_server_from_path(path, host=host, port=port)


def main() -> None:
    parser = argparse.ArgumentParser(description="QuickScript CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Command: list – lists all discovered scripts with their interface info
    parser_list = subparsers.add_parser("list", help="List available functions")
    parser_list.add_argument(
        "--scripts-dir",
        type=str,
        default=os.path.join(os.getcwd(), "scripts"),
        help="Directory to search for functions (default: scripts/)",
    )
    parser_list.add_argument(
        "--category",
        type=str,
        choices=["scripts", "queryable", "mutatable", "all"],
        nargs="?",
        default="all",
        help="Category of functions to list (default: all)",
    )

    # Command: run – run a single script (by its function name)
    parser_run = subparsers.add_parser("run", help="Run a specified function")
    parser_run.add_argument("function", type=str, help="Name of the function to run")
    parser_run.add_argument(
        "--scripts-dir",
        type=str,
        default="scripts",
        help="Directory to search for functions (default: scripts/)",
    )
    parser_run.add_argument(
        "--category",
        type=str,
        choices=["scripts", "queryable", "mutatable", "all"],
        nargs="?",
        default="all",
        help="Category of the function to run (default: all)",
    )
    parser_run.add_argument(
        "extra",
        nargs=argparse.REMAINDER,
        help="Extra arguments for the function (if needed)",
    )

    # Command: graphql – run a GraphQL server with discovered operations
    parser_graphql = subparsers.add_parser("graphql", help="Run GraphQL server")
    parser_graphql.add_argument(
        "--path",
        type=str,
        default="scripts",
        help="Directory containing functions with GraphQL metadata (default: scripts/)",
    )
    parser_graphql.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind the GraphQL server (default: 0.0.0.0)",
    )
    parser_graphql.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind the GraphQL server (default: 8000)",
    )

    # Command: zmq – run a ZeroMQ server exposing functions
    parser_zmq = subparsers.add_parser("zmq", help="Run ZeroMQ server")
    parser_zmq.add_argument(
        "--path",
        type=str,
        default="scripts",
        help="Directory containing functions with ZeroMQ metadata (default: scripts/)",
    )

    # Command: rest – run a REST server exposing functions as HTTP endpoints
    parser_rest = subparsers.add_parser("rest", help="Run REST server")
    parser_rest.add_argument(
        "--scripts-dir",
        type=str,
        default=os.path.join(os.getcwd(), "scripts"),
        help="Directory to search for functions (default: scripts/)",
    )
    parser_rest.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind the REST server (default: 0.0.0.0)",
    )
    parser_rest.add_argument(
        "--port",
        type=int,
        default=8001,
        help="Port to bind the REST server (default: 8001)",
    )

    # Command: grpc – run a gRPC server exposing functions
    parser_grpc = subparsers.add_parser("grpc", help="Run gRPC server")
    parser_grpc.add_argument(
        "--path",
        type=str,
        default="scripts",
        help="Directory containing functions with gRPC metadata (default: scripts/)",
    )
    parser_grpc.add_argument(
        "--port",
        type=int,
        default=50051,
        help="Port to bind the gRPC server (default: 50051)",
    )

    args = parser.parse_args()

    if args.command == "list":
        import inspect

        collection = collect_from_dir(args.scripts_dir)
        category = args.category
        if category == "scripts":
            functions = collection.scripts
        elif category == "queryable":
            functions = collection.queryables
        elif category == "mutatable":
            functions = collection.mutatables
        elif category == "all":
            functions = (
                collection.scripts + collection.queryables + collection.mutatables
            )

        if not functions:
            print(f"No {category} found in directory: {args.scripts_dir}")
            sys.exit(0)
        print(f"Available {category}:")
        for fn in functions:
            sig = inspect.signature(fn)
            print(f"- {fn.__name__}{sig}")
            if fn.__doc__:
                print(f"   {fn.__doc__}")
    elif args.command == "run":
        import inspect

        collection = collect_from_dir(args.scripts_dir)
        category = args.category
        if category == "scripts":
            group = collection.scripts
        elif category == "queryable":
            group = collection.queryables
        elif category == "mutatable":
            group = collection.mutatables
        elif category == "all":
            group = collection.scripts + collection.queryables + collection.mutatables

        matching = [f for f in group if f.__name__ == args.function]
        if not matching:
            print(
                f"Function '{args.function}' not found in category '{category}' in directory: {args.scripts_dir}"
            )
            sys.exit(1)
        fn = matching[0]
        cli_run(fn, args.extra)
    elif args.command == "graphql":
        run_graphql(args.path, args.host, args.port)
    elif args.command == "zmq":
        from quickscript.server.zmq import run_zeromq_server_from_path

        run_zeromq_server_from_path(args.path)
    elif args.command == "rest":
        from quickscript.server.rest import run_rest_server

        collection = collect_from_dir(args.scripts_dir)
        run_rest_server([collection], host=args.host, port=args.port)
    elif args.command == "grpc":
        from quickscript.server.grpc import run_grpc_server_from_path

        run_grpc_server_from_path(args.path, port=args.port)


if __name__ == "__main__":
    main()
