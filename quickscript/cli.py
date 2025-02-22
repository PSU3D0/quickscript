from __future__ import annotations
import argparse
import sys
import asyncio
import inspect
import time
from datetime import datetime
from typing import Any, Callable, get_type_hints, Type, Optional, List
from pydantic import BaseModel
from rich.panel import Panel
from rich.table import Table
from rich.console import Console


def _print_result(
    func: Callable, args: Optional[Any], result: Any, elapsed: float
) -> None:
    console = Console()

    # Create function info table
    info_table = Table(show_header=False, box=None)
    info_table.add_row("Function:", f"[cyan]{func.__name__}[/cyan]")
    info_table.add_row("Module:", f"[blue]{func.__module__}[/blue]")
    info_table.add_row(
        "Docstring:", f"[italic]{func.__doc__ or 'No docstring'}[/italic]"
    )
    info_table.add_row("Time:", f"[green]{elapsed:.4f}s[/green]")

    console.print(info_table)

    # Format arguments if present
    if args is not None:
        if isinstance(args, BaseModel):
            args_str = args.model_dump_json(indent=2)
        else:
            args_str = str(args)
        info_table.add_row("Arguments:", f"[yellow]{args_str}[/yellow]")

    # Format result
    if isinstance(result, BaseModel):
        result_str = result.model_dump_json(indent=2)
    elif result is None:
        result_str = "[red]No result returned[/red]"
    else:
        result_str = str(result)

    # Create the final panel with all information
    panel = Panel(
        f"{result_str}",
        title="[bold]Function Execution Results[/bold]",
        subtitle=f"[dim]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/dim]",
        expand=False,
    )

    console.print(panel)


def cli_run(func: Callable, argv: Optional[List[str]] = None) -> None:
    # Default to sys.argv[1:] if argv not provided
    if argv is None:
        argv = sys.argv[1:]
    sig = inspect.signature(func)
    args_instance = None
    # Look for the first positional parameter whose annotation is a subclass of BaseModel
    for param in sig.parameters.values():
        if param.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            if param.annotation is not inspect.Parameter.empty:
                try:
                    if issubclass(param.annotation, BaseModel):
                        args_instance = parse_cli_args(param.annotation, argv=argv)
                        break
                except TypeError:
                    continue
    # If the function expects a logger, inject one.
    kwargs = {}
    if "logger" in sig.parameters and "logger" not in kwargs:
        import logging

        kwargs["logger"] = logging.getLogger(func.__name__)
    # Call the function, using asyncio if needed.
    start_time = time.time()
    if inspect.iscoroutinefunction(func):
        if args_instance is not None:
            result = asyncio.run(func(args_instance, **kwargs))
        else:
            result = asyncio.run(func(**kwargs))
    else:
        if args_instance is not None:
            result = func(args_instance, **kwargs)
        else:
            result = func(**kwargs)
    elapsed = time.time() - start_time

    _print_result(func, args_instance, result, elapsed)


def parse_cli_args(
    arg_parser_model: Type[BaseModel], argv: Optional[List[str]] = None
) -> BaseModel:
    parser = argparse.ArgumentParser(description=arg_parser_model.__doc__ or "")
    type_hints = get_type_hints(arg_parser_model)
    for field_name, field in arg_parser_model.model_fields.items():
        parser_kwargs = {
            "type": type_hints[field_name],
            "required": field.is_required(),
            "default": field.default,
            "help": field.description,
        }
        json_schema_extra = field.json_schema_extra
        if json_schema_extra:
            extra = json_schema_extra.get("argparse", {})
            if "cli_required" in extra:
                parser_kwargs["required"] = extra.pop("cli_required")
            parser_kwargs.update(extra)
        parser.add_argument(f"--{field_name}", **parser_kwargs)
    args = parser.parse_args(argv)
    return arg_parser_model(**vars(args))
