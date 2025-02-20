"""
quickscript: An opinionated microframework for single-file agent/worker scripts

Core Concepts
-------------
1. **Queryables**:
   - **Purpose**: Use queryable functions when you need to fetch or retrieve external data. This can include obtaining JSON data (validated with Pydantic models) or loading data from databases or files (which can be cast into pandas, polars, or pyarrow frame-like objects).
   - **Return Types**: A queryable function must return one of:
     - A tuple of `(frame_like_object, optional_metadata_dict)`,
     - A single Pydantic model instance, or
     - A list of Pydantic model instances.
   - **Usage Guidelines**:
     - Accepts an optional single positional argument (commonly referred to as `args`) that **must** be a subclass of `pydantic.BaseModel`. Additional parameters can be passed as keyword arguments.
     - It is strongly recommended to define and enforce a custom Pydantic model for the `args` to ensure robust type checking.
   - **When to Use**: Employ queryables when your function is responsible for data retrieval of any kind without causing side effects.

2. **Mutatables**:
   - **Purpose**: Use mutatable functions to perform actions that have side effects or modify external state. Examples include sending POST requests, dispatching notifications, or updating external systems.
   - **Return Types**: A mutatable function must return a Pydantic model instance that represents the result of the mutation.
   - **Usage Guidelines**:
     - Like queryables, mutatables accept an optional single positional argument (i.e., `args`) which should be strongly typed via a custom Pydantic model. This ensures clarity and reliability in parameter handling.
     - Additional parameters may be passed as keyword arguments if needed.
   - **When to Use**: Choose mutatables when your function is intended to produce side effects or modify external data rather than merely retrieving it.

Additional Considerations
-------------------------
- **`args` Parameter**:
  - Both queryable and mutatable functions allow at most one positional argument—typically named `args`. This argument should be a strongly typed Pydantic model to enforce clear, consistent interfaces.
- **Flexibility and Extensibility**:
  - QuickScript is intentionally kept light and minimal. Advanced features such as retries, transactions, or other domain-specific behaviors are left to the developer to implement as needed.
- **Script Entry Point**:
  - The `@script` is an **optional** decorator that is provided to set up context variables (like logging and CLI argument parsing) for your script’s entry point.
- **Dependencies & Environment Variables**:
  - Both decorators support declaring third-party dependencies and required environment variables, ensuring that all necessary runtime requirements are validated before execution.
"""

from __future__ import annotations
import os
import importlib
import functools
import asyncio
import contextvars
import logging
import argparse
import inspect
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Literal,
    Optional,
    Type,
    TypeVar,
    Union,
    Tuple,
    get_origin,
    get_args,
    get_type_hints,
)
from pydantic import BaseModel

# -----------------------------------------------------------------------------
# Global Runtime Typechecking Flag
# -----------------------------------------------------------------------------
GLOBAL_RUNTIME_TYPECHECKING: bool = os.getenv(
    "QUICKSCRIPT_DISABLE_RUNTIME_TYPECHECKING", ""
).lower() not in ("1", "true", "yes")

# -----------------------------------------------------------------------------
# Try importing frame libraries
# -----------------------------------------------------------------------------
try:
    import pandas as pd
except ImportError:
    pd = None
try:
    import polars as pl
except ImportError:
    pl = None
try:
    import pyarrow as pa
except ImportError:
    pa = None

# -----------------------------------------------------------------------------
# FrameLike: union of acceptable frame types
# -----------------------------------------------------------------------------
FrameLike = Union[
    pd.DataFrame if pd is not None else Any,
    pl.DataFrame if pl is not None else Any,
    pa.Table if pa is not None else Any,
]


# -----------------------------------------------------------------------------
# Helpers for dependency and env var checks
# -----------------------------------------------------------------------------
def check_env_vars(env_vars: Dict[str, Type]) -> None:
    for var, typ in env_vars.items():
        value = os.getenv(var)
        if value is None:
            raise EnvironmentError(f"Environment variable '{var}' is not set.")
        try:
            typ(value)
        except Exception as e:
            raise ValueError(
                f"Environment variable '{var}' cannot be cast to {typ}: {e}"
            )


def check_dependencies(dependencies: List[str]) -> None:
    for dep in dependencies:
        try:
            importlib.import_module(dep)
        except ImportError:
            raise ImportError(f"Dependency '{dep}' is required but not installed.")


# -----------------------------------------------------------------------------
# The unified decorator builder (for queryable & mutatable)
# -----------------------------------------------------------------------------
T = TypeVar("T", bound=Callable[..., Any])


def _build_decorator(
    mode: Literal["queryable", "mutatable"],
    _func: Optional[T] = None,
    *,
    dependencies: Optional[List[str]] = None,
    env_vars: Optional[Dict[str, Type]] = None,
    runtime_typechecking: bool = True,
) -> Callable[[T], T]:
    dependencies = dependencies or []
    env_vars = env_vars or {}

    def decorator(func: T) -> T:
        sig = inspect.signature(func)
        # Allow at most one positional argument (if provided, must be a subclass of BaseModel)
        positional = [
            p
            for p in sig.parameters.values()
            if p.kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        ]
        if len(positional) > 1:
            raise ValueError(
                f"{mode.capitalize()} function '{func.__name__}' can accept at most one positional argument."
            )
        if positional:
            p = positional[0]
            if p.annotation is inspect.Parameter.empty or not (
                isinstance(p.annotation, type) and issubclass(p.annotation, BaseModel)
            ):
                raise TypeError(
                    f"{mode.capitalize()} function '{func.__name__}' positional argument '{p.name}' must be annotated with a subclass of pydantic.BaseModel."
                )

        # Check return annotation
        if sig.return_annotation is inspect.Signature.empty:
            raise TypeError(
                f"{mode.capitalize()} function '{func.__name__}' must have a return type annotation."
            )
        ret_ann = sig.return_annotation

        if mode == "queryable":
            # Infer expected return category:
            if get_origin(ret_ann) in (list, List):
                inner = get_args(ret_ann)[0]
                if isinstance(inner, type) and issubclass(inner, BaseModel):
                    expected = "model_list"
                else:
                    raise TypeError(
                        f"Queryable '{func.__name__}' returns a list but its inner type is not a subclass of BaseModel."
                    )
            elif isinstance(ret_ann, type) and issubclass(ret_ann, BaseModel):
                expected = "model"
            else:
                expected = "frame"
        else:  # mutatable
            if not (isinstance(ret_ann, type) and issubclass(ret_ann, BaseModel)):
                raise TypeError(
                    f"Mutatable function '{func.__name__}' must have a return type annotation that is a subclass of BaseModel."
                )
            expected = "model"

        # The actual wrapper
        def _validate_args(bound):
            if positional:
                arg = bound.arguments.get(positional[0].name)
                if arg is not None and not isinstance(arg, positional[0].annotation):
                    raise TypeError(
                        f"In {mode} '{func.__name__}', argument '{positional[0].name}' must be an instance of {positional[0].annotation}."
                    )

        def _validate_result(result):
            if mode == "queryable":
                if expected == "frame":
                    frame_obj = result[0] if isinstance(result, tuple) else result
                    if not (
                        (pd is not None and isinstance(frame_obj, pd.DataFrame))
                        or (pl is not None and isinstance(frame_obj, pl.DataFrame))
                        or (pa is not None and isinstance(frame_obj, pa.Table))
                    ):
                        raise TypeError(
                            f"Queryable '{func.__name__}' expected to return a valid frame-like object."
                        )
                elif expected == "model" and not isinstance(result, BaseModel):
                    raise TypeError(
                        f"Queryable '{func.__name__}' expected to return a BaseModel instance."
                    )
                elif expected == "model_list" and not (
                    isinstance(result, list)
                    and all(isinstance(item, BaseModel) for item in result)
                ):
                    raise TypeError(
                        f"Queryable '{func.__name__}' expected to return a list of BaseModel instances."
                    )
            else:  # mutatable
                if not isinstance(result, ret_ann):
                    raise TypeError(
                        f"Mutatable '{func.__name__}' returned {type(result)} but must return {ret_ann}."
                    )

        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                if runtime_typechecking and GLOBAL_RUNTIME_TYPECHECKING:
                    check_dependencies(dependencies)
                    check_env_vars(env_vars)
                    bound = sig.bind(*args, **kwargs)
                    bound.apply_defaults()
                    _validate_args(bound)
                result = await func(*args, **kwargs)
                if runtime_typechecking and GLOBAL_RUNTIME_TYPECHECKING:
                    _validate_result(result)
                return result

            return async_wrapper  # type: ignore
        else:

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                if runtime_typechecking and GLOBAL_RUNTIME_TYPECHECKING:
                    check_dependencies(dependencies)
                    check_env_vars(env_vars)
                    bound = sig.bind(*args, **kwargs)
                    bound.apply_defaults()
                    _validate_args(bound)
                result = func(*args, **kwargs)
                if runtime_typechecking and GLOBAL_RUNTIME_TYPECHECKING:
                    _validate_result(result)
                return result

            return sync_wrapper  # type: ignore

    return decorator(_func) if _func is not None else decorator


# -----------------------------------------------------------------------------
# Decorators for Declaring Queryables and Mutatables (now unified)
# -----------------------------------------------------------------------------
def queryable(
    _func: Optional[Callable[..., Any]] = None,
    *,
    dependencies: Optional[List[str]] = None,
    env_vars: Optional[Dict[str, Type]] = None,
    runtime_typechecking: bool = True,
) -> Callable:
    """
    Decorator for queryable functions.
    The function’s return type annotation is used to infer the expected type:
      - If annotated as a list of BaseModel, it must return a list of BaseModel instances.
      - If annotated as a BaseModel subclass, it must return a BaseModel instance.
      - Otherwise it is assumed to return a frame-like object (pandas, polars, or pyarrow).
    """
    return _build_decorator(
        "queryable",
        _func,
        dependencies=dependencies,
        env_vars=env_vars,
        runtime_typechecking=runtime_typechecking,
    )


def mutatable(
    _func: Optional[Callable[..., Any]] = None,
    *,
    dependencies: Optional[List[str]] = None,
    env_vars: Optional[Dict[str, Type]] = None,
    runtime_typechecking: bool = True,
) -> Callable:
    """
    Decorator for mutatable functions.
    The function must have a return type annotation that is a subclass of BaseModel.
    """
    return _build_decorator(
        "mutatable",
        _func,
        dependencies=dependencies,
        env_vars=env_vars,
        runtime_typechecking=runtime_typechecking,
    )


# -----------------------------------------------------------------------------
# Script Decorator and Helpers (unchanged)
# -----------------------------------------------------------------------------
script_logger_var: contextvars.ContextVar[logging.Logger] = contextvars.ContextVar(
    "script_logger", default=logging.getLogger("default")
)
script_args_var: contextvars.ContextVar[Optional[BaseModel]] = contextvars.ContextVar(
    "script_args", default=None
)

TScript = TypeVar("TScript", bound=Callable[..., Any])


def script(
    arg_parser_model: Optional[Type[BaseModel]] = None,
) -> Callable[[TScript], TScript]:
    def decorator(func: TScript) -> TScript:
        sig = inspect.signature(func)

        def setup_context() -> Tuple[
            logging.Logger, contextvars.Token, Optional[contextvars.Token]
        ]:
            logger = logging.getLogger(func.__name__)
            token_logger = script_logger_var.set(logger)
            token_args = None
            if arg_parser_model is not None:
                cli_args = parse_cli_args(arg_parser_model)
                token_args = script_args_var.set(cli_args)
            return logger, token_logger, token_args

        def reset_context(
            token_logger: contextvars.Token, token_args: Optional[contextvars.Token]
        ) -> None:
            script_logger_var.reset(token_logger)
            if token_args is not None:
                script_args_var.reset(token_args)

        def inject_kwargs(kwargs: Dict[str, Any], logger: logging.Logger) -> None:
            if "logger" in sig.parameters and "logger" not in kwargs:
                kwargs["logger"] = logger
            if (
                arg_parser_model is not None
                and "cli_args" in sig.parameters
                and "cli_args" not in kwargs
            ):
                kwargs["cli_args"] = script_args_var.get()

        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                logger, token_logger, token_args = setup_context()
                try:
                    inject_kwargs(kwargs, logger)
                    result = await func(*args, **kwargs)
                finally:
                    reset_context(token_logger, token_args)
                return result

            return async_wrapper  # type: ignore
        else:

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                logger, token_logger, token_args = setup_context()
                try:
                    inject_kwargs(kwargs, logger)
                    result = func(*args, **kwargs)
                finally:
                    reset_context(token_logger, token_args)
                return result

            return sync_wrapper  # type: ignore

    return decorator


def parse_cli_args(arg_parser_model: Type[BaseModel]) -> BaseModel:
    parser = argparse.ArgumentParser(description=arg_parser_model.__doc__ or "")
    type_hints = get_type_hints(arg_parser_model)
    for field_name, field in arg_parser_model.model_fields.items():
        parser_kwargs = {
            "type": type_hints[field_name],
            "required": field.is_required(),
            "default": field.default,
            "help": field.description,
        }
        extra = field.json_schema_extra.get("argparse", {})
        if "cli_required" in extra:
            parser_kwargs["required"] = extra.pop("cli_required")
        parser_kwargs.update(extra)
        parser.add_argument(f"--{field_name}", **parser_kwargs)
    args = parser.parse_args()
    return arg_parser_model(**vars(args))


def get_script_logger() -> logging.Logger:
    return script_logger_var.get()


def get_script_args() -> Optional[BaseModel]:
    return script_args_var.get()


__all__ = [
    "queryable",
    "mutatable",
    "script",
    "get_script_logger",
    "get_script_args",
]

# -----------------------------------------------------------------------------
# Example Usage
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    from pydantic import Field

    class CLIArgs(BaseModel):
        """Command-line arguments for the script."""

        input_file: str = Field(
            "default.txt",
            description="Path to the input file",
            argparse={"cli_required": True, "metavar": "FILE"},
        )
        mode: str = Field(
            ...,
            description="Operation mode",
            argparse={"choices": ["fast", "slow"], "metavar": "MODE"},
        )

    @script(arg_parser_model=CLIArgs)
    def main(cli_args: CLIArgs, logger: logging.Logger):
        logger.info(
            f"Running in {cli_args.mode} mode using file: {cli_args.input_file}"
        )
        print(f"CLI args: {cli_args}")

    main()
