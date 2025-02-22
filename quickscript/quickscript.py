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
import inspect
from typing import (
    Any,
    Callable,
    Dict,
    Iterator,
    List,
    Literal,
    Optional,
    Type,
    TypeVar,
    Union,
    Generic,
    get_origin,
    get_args,
)
from pydantic import BaseModel, Field

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

TPydanticModel = TypeVar("TPydanticModel", bound=BaseModel)


class FrameSchema(Generic[TPydanticModel]):
    """
    A lightweight wrapper for DataFrame-like objects with explicit column schemas.

    - `iter_rows()`: Yields rows as instances of the schema.
    - `get_pydantic_model()`: Returns the schema model for JSONSchema conversion.
    - Supports Pandas, Polars, and PyArrow.
    """

    df_type: Literal["pandas", "polars", "pyarrow"]
    _data: FrameLike
    schema: BaseModel

    def __init__(self, data: FrameLike, schema: Type[TPydanticModel]):
        self.df_type = self._infer_frame_type()
        self._data = data

        self.schema = schema

    def _infer_frame_type(self):
        if pd is not None and isinstance(self.data, pd.DataFrame):
            return "pandas"
        elif pl is not None and isinstance(self.data, pl.DataFrame):
            return "polars"
        elif pa is not None and isinstance(self.data, pa.Table):
            return "pyarrow"
        else:
            raise TypeError(f"Unsupported data type: {type(self.data)}")

    def iter_rows(self, to_model: bool = False) -> Iterator[T]:
        """Yields each row as a Pydantic model instance."""
        if self.df_type == "pandas":
            for row in self.data.to_dict(
                orient="records"
            ):  # Pandas/Polars/Arrow -> Dict
                if to_model:
                    yield self.schema(**row)
                else:
                    yield row
        elif self.df_type == "polars":
            for row in self.data.iter_rows(named=True):  # Polars -> Dict
                if to_model:
                    yield self.schema(**row)
                else:
                    yield row
        elif self.df_type == "pyarrow":
            for row in self.data.to_pylist():
                if to_model:
                    yield self.schema(**row)
                else:
                    yield row

    def get_pydantic_model(self) -> Type[T]:
        """Returns the associated Pydantic schema model."""
        return self.schema

    def to_json_schema(self) -> Dict:
        """Generates JSON schema for OpenAPI integration."""
        return self.schema.model_json_schema()

    @property
    def data(self) -> FrameLike:
        return self._data


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


class BaseMetadata(BaseModel):
    """
    Base metadata class for all metadata.
    """

    dependencies: List[str] = Field(
        default_factory=list, description="A list of dependencies for the function."
    )
    env_vars: Dict[str, Type] = Field(
        default_factory=dict,
        description="A dictionary of environment variables for the function.",
    )
    runtime_typechecking: bool = Field(
        default=True,
        description="Whether to enable runtime typechecking for the function.",
    )


def attach_metadata(
    func: Callable, *, namespace: Optional[str], data: BaseModel
) -> Callable:
    """
    Attach metadata to a function.
    """
    if namespace is None:
        namespace = func.__module__

    if not hasattr(func, "__qs_metadata__"):
        func.__qs_metadata__ = {}

    if not hasattr(func, "__qs_pydantic_bases__"):
        func.__qs_pydantic_bases__ = []

    if namespace in func.__qs_metadata__:
        raise ValueError(
            f"Metadata for namespace '{namespace}' already exists. Have you already applied this decorator?"
        )

    func.__qs_metadata__[namespace] = data.model_dump()
    func.__qs_pydantic_bases__.append(data)

    return func


TContextItem = TypeVar("TContextItem")
_Context = contextvars.ContextVar("quickscript_context", default=[])


class ContextItem(Generic[TContextItem]):
    def __init__(self, name: str, value=None, get_value=None, aliases=None):
        self.name = name
        self.value = value
        self.get_value = get_value
        self.aliases = aliases or []

    def resolve(self):
        if self.value is not None:
            return self.value
        elif self.get_value is not None:
            return self.get_value()
        else:
            raise ValueError(
                f"No value or get_value provided for context item '{self.name}'"
            )


# A context manager that pushes a context item for the duration of a function call
from contextlib import contextmanager


@contextmanager
def push_context_item(item: ContextItem):
    # Get current context items, push this new item onto the list
    current = _Context.get()
    new_context = current + [item]
    token = _Context.set(new_context)
    try:
        yield
    finally:
        _Context.reset(token)


def get_context_item(name: str, _cast: Type[TContextItem] = None) -> TContextItem:
    current = _Context.get()
    for item in current:
        if item.name == name or name in item.aliases:
            return item.resolve()
    raise ValueError(f"Context item '{name}' not found")


# Now, instead of attaching the context item to the function definition,
# create a wrapper that pushes it at call time.
def with_context_item(name: str, *, value=None, get_value=None, aliases=None):
    item = ContextItem(name=name, value=value, get_value=get_value, aliases=aliases)

    def decorator(func):
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                with push_context_item(item):
                    return await func(*args, **kwargs)
        else:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                with push_context_item(item):
                    return func(*args, **kwargs)

        return wrapper

    return decorator


def _build_decorator(
    mode: Literal["queryable", "mutatable", "script"],
    _func: Optional[T] = None,
    *,
    dependencies: Optional[List[str]] = None,
    env_vars: Optional[Dict[str, Type]] = None,
    runtime_typechecking: bool = True,
) -> Callable[[T], T]:
    dependencies = dependencies or []
    env_vars = env_vars or {}

    model = BaseMetadata(
        dependencies=dependencies,
        env_vars=env_vars,
        runtime_typechecking=runtime_typechecking,
    )

    def decorator(func: T) -> T:
        sig = inspect.signature(func)
        args_pydantic_type = None  # The type of the positional argument, if provided.
        ret_pydantic_type = None  # The type of the return value.

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

            args_pydantic_type = p.annotation

        # Check return annotation
        if sig.return_annotation is inspect.Signature.empty and mode != "script":
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
                    ret_pydantic_type = inner
                else:
                    raise TypeError(
                        f"Queryable '{func.__name__}' returns a list but its inner type is not a subclass of BaseModel."
                    )
            elif isinstance(ret_ann, type) and issubclass(ret_ann, BaseModel):
                expected = "model"
                ret_pydantic_type = ret_ann
            elif isinstance(ret_ann, type) and issubclass(ret_ann, FrameSchema):
                expected = "frame_schema"
                ret_pydantic_type = None
            else:
                expected = "frame"
                ret_pydantic_type = None
        elif mode == "mutatable":  # mutatable
            if not (isinstance(ret_ann, type) and issubclass(ret_ann, BaseModel)):
                raise TypeError(
                    f"Mutatable function '{func.__name__}' must have a return type annotation that is a subclass of BaseModel."
                )
            expected = "model"
            ret_pydantic_type = ret_ann

        func.__qs_args_pydantic_type__ = args_pydantic_type
        func.__qs_ret_pydantic_type__ = ret_pydantic_type
        func.__qs_mode__ = mode

        # The actual wrapper
        def _validate_args(bound):
            if positional:
                arg = bound.arguments.get(positional[0].name)
                annotation = positional[0].annotation
                if arg is not None and not isinstance(arg, annotation):
                    if isinstance(arg, dict) and issubclass(annotation, BaseModel):
                        try:
                            casted = annotation.model_validate(arg)
                        except ValueError as e:
                            raise ValueError(
                                f"In {mode} '{func.__name__}', dictionary argument '{positional[0].name}' could not be validated as a {annotation}."
                            ) from e
                        else:
                            bound.arguments[positional[0].name] = casted
                    else:
                        raise TypeError(
                            f"In {mode} '{func.__name__}', argument '{positional[0].name}' must be an instance of {annotation}."
                        )

        def _validate_result(result):
            if mode == "queryable":
                if expected == "frame" or expected == "frame_schema":
                    frame_obj = result[0] if isinstance(result, tuple) else result

                    if not (
                        (pd is not None and isinstance(frame_obj, pd.DataFrame))
                        or (pl is not None and isinstance(frame_obj, pl.DataFrame))
                        or (pa is not None and isinstance(frame_obj, pa.Table))
                        or (isinstance(frame_obj, FrameSchema))
                    ):
                        raise TypeError(
                            f"Queryable '{func.__name__}' expected to return a valid frame-like object or frame schema."
                        )

                    if (
                        not isinstance(frame_obj, FrameSchema)
                        and expected == "frame_schema"
                    ):
                        return frame_obj  # TODO Convert into frame schema, getting the annotation off the `ret_anna`
                    else:
                        return frame_obj

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
            elif mode == "mutatable":  # mutatable
                if not isinstance(result, ret_ann):
                    raise TypeError(
                        f"Mutatable '{func.__name__}' returned {type(result)} but must return {ret_ann}."
                    )

            return result

        attach_metadata(func, namespace=None, data=model)

        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                if runtime_typechecking and GLOBAL_RUNTIME_TYPECHECKING:
                    check_dependencies(dependencies)
                    check_env_vars(env_vars)
                    bound = sig.bind(*args, **kwargs)
                    bound.apply_defaults()
                    _validate_args(bound)
                result = await func(*bound.args, **bound.kwargs)
                if runtime_typechecking and GLOBAL_RUNTIME_TYPECHECKING:
                    validated = _validate_result(result)
                    if isinstance(result, tuple):
                        return validated, result[1]
                    else:
                        return validated
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
                result = func(*bound.args, **bound.kwargs)
                if runtime_typechecking and GLOBAL_RUNTIME_TYPECHECKING:
                    validated = _validate_result(result)
                    if isinstance(result, tuple):
                        return validated, result[1]
                    else:
                        return validated
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


TScript = TypeVar("TScript", bound=Callable[..., Any])


def script(
    _func: Optional[TScript] = None,
    *,
    dependencies: Optional[List[str]] = None,
    env_vars: Optional[Dict[str, Type]] = None,
    runtime_typechecking: bool = True,
) -> Callable[[TScript], TScript]:
    def decorator(func: TScript) -> TScript:
        # Wrap using the same _build_decorator as queryable
        wrapped = _build_decorator(
            "script",
            func,
            dependencies=dependencies,
            env_vars=env_vars,
            runtime_typechecking=runtime_typechecking,
        )

        wrapped_with_logger = with_context_item(
            "logger",
            value=logging.getLogger(func.__name__),
        )(wrapped)

        return wrapped_with_logger

    return decorator(_func) if _func is not None else decorator


__all__ = [
    "queryable",
    "mutatable",
    "script",
]
