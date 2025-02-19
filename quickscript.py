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
    Optional,
    Type,
    TypeVar,
    Generic,
    Literal,
    Union,
    Tuple,
    Protocol,
    get_type_hints,
    get_origin,
    get_args,
)
from pydantic import BaseModel

# -----------------------------------------------------------------------------
# Global Flag for Runtime Typechecking
# -----------------------------------------------------------------------------
GLOBAL_RUNTIME_TYPECHECKING: bool = not (
    os.getenv("QUICKSCRIPT_DISABLE_RUNTIME_TYPECHECKING", "").lower()
    in ("1", "true", "yes")
)

# -----------------------------------------------------------------------------
# Generic Types for State and Config
# -----------------------------------------------------------------------------
TState = TypeVar("TState", bound=BaseModel)
TConfig = TypeVar("TConfig", bound=BaseModel)

# -----------------------------------------------------------------------------
# Generic Types for Mutatable Functions
# -----------------------------------------------------------------------------
TInput = TypeVar("TInput", bound=BaseModel)
TOutput = TypeVar("TOutput", bound=BaseModel)

# -----------------------------------------------------------------------------
# Frame Type Declarations for Queryable Functions
# -----------------------------------------------------------------------------
FrameTypeLiteral = Literal["pandas", "polars", "arrow"]

try:
    import pandas as pd  # type: ignore
except ImportError:
    pd = None

try:
    import polars as pl  # type: ignore
except ImportError:
    pl = None

try:
    import pyarrow as pa  # type: ignore
except ImportError:
    pa = None

FrameLike = Union[
    pd.DataFrame if pd is not None else Any,
    pl.DataFrame if pl is not None else Any,
    pa.Table if pa is not None else Any,
]


# -----------------------------------------------------------------------------
# Protocols for Callable Types
# -----------------------------------------------------------------------------
class QueryableFunc(Protocol, Generic[TConfig, TState, TOutput]):
    async def __call__(self, *args: Any, **kwargs: Any) -> Union[
        Tuple[FrameLike, Optional[Dict[str, Any]]],
        TOutput,
        List[TOutput],
    ]:
        """
        A queryable function takes optional arguments and returns one of:
          - a tuple (frame-like object, optional metadata dict),
          - a single BaseModel instance (of type TOutput), or
          - a list of BaseModel instances (of type TOutput).
        """
        ...


class MutatableFunc(Protocol, Generic[TConfig, TState, TInput, TOutput]):
    async def __call__(self, *args: Any, **kwargs: Any) -> TOutput:
        """
        A mutatable function takes optional arguments, performs some side effect, and returns an output.
        """
        ...


# -----------------------------------------------------------------------------
# Runtime Checking Utilities
# -----------------------------------------------------------------------------
def check_env_vars(env_vars: Dict[str, Type]) -> None:
    for var, var_type in env_vars.items():
        value = os.getenv(var)
        if value is None:
            raise EnvironmentError(f"Environment variable '{var}' is not set.")
        try:
            var_type(value)
        except Exception as e:
            raise ValueError(
                f"Environment variable '{var}' cannot be cast to {var_type}: {e}"
            )


def check_dependencies(dependencies: List[str]) -> None:
    for dep in dependencies:
        try:
            importlib.import_module(dep)
        except ImportError:
            raise ImportError(f"Dependency '{dep}' is required but not installed.")


# -----------------------------------------------------------------------------
# Decorators for Declaring Dependencies and Environment Variables
# -----------------------------------------------------------------------------
def queryable(
    *,
    frame_type: Optional[FrameTypeLiteral] = None,
    returns: Optional[Literal["frame", "model", "model_list"]] = None,
    dependencies: Optional[List[str]] = None,
    env_vars: Optional[Dict[str, Type]] = None,
    runtime_typechecking: bool = True,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator for queryable functions.

    The decorated function must be asynchronous and may accept a single optional positional argument,
    which must be annotated with a subclass of pydantic.BaseModel. The function can also accept any keyword
    arguments. Additionally, the function must specify a return type annotation, which is used to infer the expected
    return type as one of:
      - "frame": The function returns a frame-like object (or a tuple of (frame, optional metadata)).
      - "model": The function returns a single BaseModel instance.
      - "model_list": The function returns a list of BaseModel instances.

    Parameters:
      - frame_type: Which frame type this function returns (e.g. "pandas", "polars", "arrow").
         Must be provided if the return type is inferred as "frame".
      - returns: Optionally, explicitly specify the expected return type. If omitted, it is inferred from the function's
         return annotation.
      - dependencies: List of third-party package names required.
      - env_vars: Dictionary mapping environment variable names to expected types.
      - runtime_typechecking: If True (the default) runtime type and dependency checking will occur.
          This can be disabled globally via the QUICKSCRIPT_DISABLE_RUNTIME_TYPECHECKING environment variable.
    """
    dependencies = dependencies or []
    env_vars = env_vars or {}

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        sig = inspect.signature(func)
        # Allow only up to one positional argument (which must be a BaseModel if provided)
        positional_params = [
            param
            for param in sig.parameters.values()
            if param.kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        ]
        if len(positional_params) > 1:
            raise ValueError(
                f"Queryable function '{func.__name__}' can accept at most one positional argument, got {len(positional_params)}"
            )
        if positional_params:
            pos_param = positional_params[0]
            if pos_param.annotation is inspect.Parameter.empty:
                raise TypeError(
                    f"Queryable function '{func.__name__}' positional argument '{pos_param.name}' must have a type annotation of a pydantic model."
                )
            if not (
                isinstance(pos_param.annotation, type)
                and issubclass(pos_param.annotation, BaseModel)
            ):
                raise TypeError(
                    f"Queryable function '{func.__name__}' positional argument '{pos_param.name}' must be a subclass of pydantic.BaseModel."
                )

        # Ensure a return type annotation is provided.
        if sig.return_annotation is inspect.Signature.empty:
            raise TypeError(
                f"Queryable function '{func.__name__}' must have a return type annotation."
            )

        # Infer the expected return type from the function's return annotation.
        ret_ann = sig.return_annotation
        if get_origin(ret_ann) in (list, List):
            inner = get_args(ret_ann)[0]
            if isinstance(inner, type) and issubclass(inner, BaseModel):
                inferred_return: Literal["frame", "model", "model_list"] = "model_list"
            else:
                raise TypeError(
                    f"Queryable function '{func.__name__}' return type is a list but its inner type is not a subclass of pydantic.BaseModel."
                )
        elif isinstance(ret_ann, type) and issubclass(ret_ann, BaseModel):
            inferred_return = "model"
        else:
            inferred_return = "frame"

        # Use the explicit 'returns' if provided; otherwise, use the inferred type.
        if returns is None:
            returns_value = inferred_return
        else:
            if returns != inferred_return:
                raise ValueError(
                    f"Queryable function '{func.__name__}' has a return annotation that infers '{inferred_return}' but "
                    f"the decorator was provided with returns='{returns}'. They must match."
                )
            returns_value = returns

        # For frame-like returns, ensure a frame_type is provided.
        if returns_value == "frame" and frame_type is None:
            raise ValueError(
                f"Queryable function '{func.__name__}' is inferred to return a frame-like object, so 'frame_type' must be specified."
            )

        setattr(func, "_frame_type", frame_type)
        setattr(func, "_returns", returns_value)
        setattr(func, "_dependencies", dependencies)
        setattr(func, "_env_vars", env_vars)

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            typecheck_enabled = runtime_typechecking and GLOBAL_RUNTIME_TYPECHECKING
            if typecheck_enabled:
                check_dependencies(dependencies)
                check_env_vars(env_vars)
                bound = sig.bind(*args, **kwargs)
                bound.apply_defaults()
                if positional_params:
                    pos_arg = bound.arguments.get(positional_params[0].name)
                    if pos_arg is not None and not isinstance(
                        pos_arg, positional_params[0].annotation
                    ):
                        raise TypeError(
                            f"In queryable '{func.__name__}', argument '{positional_params[0].name}' must be an instance of {positional_params[0].annotation}."
                        )
            result = await func(*args, **kwargs)

            if typecheck_enabled:
                # Runtime checking for the returned value based on the inferred return type.
                if returns_value == "frame":
                    # Allow either a tuple (frame, [metadata]) or a direct frame-like object.
                    if isinstance(result, tuple):
                        if len(result) not in (1, 2):
                            raise ValueError(
                                f"Queryable '{func.__name__}' returning a tuple must have 1 or 2 elements."
                            )
                        frame_obj = result[0]
                    else:
                        frame_obj = result

                    # Validate the frame type.
                    if frame_type == "pandas":
                        if pd is None or not isinstance(frame_obj, pd.DataFrame):
                            raise TypeError(
                                f"Queryable '{func.__name__}' expected to return a pandas.DataFrame."
                            )
                    elif frame_type == "polars":
                        if pl is None or not isinstance(frame_obj, pl.DataFrame):
                            raise TypeError(
                                f"Queryable '{func.__name__}' expected to return a polars.DataFrame."
                            )
                    elif frame_type == "arrow":
                        if pa is None or not isinstance(frame_obj, pa.Table):
                            raise TypeError(
                                f"Queryable '{func.__name__}' expected to return a pyarrow.Table."
                            )
                    else:
                        raise ValueError(
                            f"Unknown frame_type '{frame_type}' declared in queryable '{func.__name__}'."
                        )
                elif returns_value == "model":
                    if not isinstance(result, BaseModel):
                        raise TypeError(
                            f"Queryable '{func.__name__}' expected to return a BaseModel instance."
                        )
                elif returns_value == "model_list":
                    if not (
                        isinstance(result, list)
                        and all(isinstance(item, BaseModel) for item in result)
                    ):
                        raise TypeError(
                            f"Queryable '{func.__name__}' expected to return a list of BaseModel instances."
                        )
                else:
                    raise ValueError(
                        f"Queryable '{func.__name__}' has unknown returns declaration: {returns_value}"
                    )
            return result

        return wrapper

    return decorator


def mutatable(
    dependencies: Optional[List[str]] = None,
    env_vars: Optional[Dict[str, Type]] = None,
    runtime_typechecking: bool = True,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator for mutatable functions.

    The decorated function must be asynchronous and may accept a single optional positional argument,
    which must be annotated with a subclass of pydantic.BaseModel. The function can also accept any keyword
    arguments. Additionally, the function must specify a return type annotation and, for mutatable functions,
    that return type must be a subclass of pydantic.BaseModel.

    Parameters:
      - dependencies: List of third-party package names required.
      - env_vars: Dictionary mapping environment variable names to expected types.
      - runtime_typechecking: If True (the default) runtime type and dependency checking will occur.
          This can be disabled globally via the QUICKSCRIPT_DISABLE_RUNTIME_TYPECHECKING environment variable.
    """
    dependencies = dependencies or []
    env_vars = env_vars or {}

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        sig = inspect.signature(func)
        return_type_klass = get_origin(sig.return_annotation) or sig.return_annotation
        # Allow only up to one positional argument (which must be a BaseModel if provided)
        positional_params = [
            param
            for param in sig.parameters.values()
            if param.kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        ]
        if len(positional_params) > 1:
            raise ValueError(
                f"Mutatable function '{func.__name__}' can accept at most one positional argument, got {len(positional_params)}"
            )
        if positional_params:
            pos_param = positional_params[0]
            if pos_param.annotation is inspect.Parameter.empty:
                raise TypeError(
                    f"Mutatable function '{func.__name__}' positional argument '{pos_param.name}' must have a type annotation of a pydantic model."
                )
            if not (
                isinstance(pos_param.annotation, type)
                and issubclass(pos_param.annotation, BaseModel)
            ):
                raise TypeError(
                    f"Mutatable function '{func.__name__}' positional argument '{pos_param.name}' must be a subclass of pydantic.BaseModel."
                )

        # Ensure a return type annotation is provided and that it is a subclass of BaseModel.
        if sig.return_annotation is inspect.Signature.empty:
            raise TypeError(
                f"Mutatable function '{func.__name__}' must have a return type annotation."
            )
        if not (
            isinstance(sig.return_annotation, type)
            and issubclass(sig.return_annotation, BaseModel)
        ):
            raise TypeError(
                f"Mutatable function '{func.__name__}' return type must be a subclass of pydantic.BaseModel."
            )

        setattr(func, "_dependencies", dependencies)
        setattr(func, "_env_vars", env_vars)

        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            typecheck_enabled = runtime_typechecking and GLOBAL_RUNTIME_TYPECHECKING
            if typecheck_enabled:
                check_dependencies(dependencies)
                check_env_vars(env_vars)
                bound = sig.bind(*args, **kwargs)
                bound.apply_defaults()
                if positional_params:
                    pos_arg = bound.arguments.get(positional_params[0].name)
                    if pos_arg is not None and not isinstance(
                        pos_arg, positional_params[0].annotation
                    ):
                        raise TypeError(
                            f"In mutatable '{func.__name__}', argument '{positional_params[0].name}' must be an instance of {positional_params[0].annotation}."
                        )
            result = await func(*args, **kwargs)
            if typecheck_enabled and return_type_klass is not None:
                if not isinstance(result, return_type_klass):
                    raise TypeError(
                        f"Mutatable '{func.__name__}' returned an instance of {type(result)} "
                        f"but must return an instance of {return_type_klass}."
                    )
            return result

        return wrapper

    return decorator


# -----------------------------------------------------------------------------
# Helper: Parse CLI Arguments from a Pydantic Model
# -----------------------------------------------------------------------------
def parse_cli_args(arg_parser_model: Type[BaseModel]) -> BaseModel:
    """
    Build an argparse.ArgumentParser from a pydantic model, taking into account extra
    CLI keyword arguments provided in the Field's extra metadata under the key "argparse".
    """
    parser = argparse.ArgumentParser(description=arg_parser_model.__doc__ or "")
    type_hints = get_type_hints(arg_parser_model)
    for field_name, field in arg_parser_model.model_fields.items():
        parser_kwargs = {
            "type": type_hints[field_name],
            "required": field.is_required(),
            "default": field.default,
            "help": field.description,
        }
        extra_kwargs = field.json_schema_extra.get("argparse", {})
        if "cli_required" in extra_kwargs:
            parser_kwargs["required"] = extra_kwargs.pop("cli_required")
        parser_kwargs.update(extra_kwargs)
        parser.add_argument(f"--{field_name}", **parser_kwargs)
    parsed = parser.parse_args()
    args_dict = vars(parsed)
    return arg_parser_model(**args_dict)


# -----------------------------------------------------------------------------
# Script Decorator with ContextVars and Typed Argparse Support
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
    """
    Decorator for script entry points that sets up context variables for logger and CLI arguments.
    """

    def decorator(func: TScript) -> TScript:
        sig = inspect.signature(func)

        def setup_context() -> (
            Tuple[logging.Logger, contextvars.Token, Optional[contextvars.Token]]
        ):
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


# -----------------------------------------------------------------------------
# Helper Functions to Access Script Context
# -----------------------------------------------------------------------------
def get_script_logger() -> logging.Logger:
    """
    Retrieve the current script logger from context.
    """
    return script_logger_var.get()


def get_script_args() -> Optional[BaseModel]:
    """
    Retrieve the current CLI arguments (as a pydantic model) from context.
    """
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
        """
        Command-line arguments for the script.
        """

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
