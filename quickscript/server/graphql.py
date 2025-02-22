import asyncio
import os
from typing import Any, Callable, Dict, List, Optional, Sequence, Type, TypeVar
from pydantic import BaseModel
from starlette.applications import Starlette
from strawberry.asgi import GraphQL
import strawberry
from strawberry.experimental.pydantic.conversion_types import StrawberryTypeFromPydantic
from strawberry.experimental.pydantic.object_type import type as pydantic_to_strawberry
from strawberry.types.fields.resolver import StrawberryResolver

from quickscript.collect import (
    QuickScriptCollection,
    collect_from_dir,
    collect_from_file,
)


_strawberry_type_registry = {}

TPydanticModel = TypeVar("TPydanticModel", bound=BaseModel)


def create_strawberry_model_from_pydantic_type(
    pydantic_type: Type[TPydanticModel],
    *,
    strawberry_bases: Optional[List[Type]] = None,
    fields: Optional[List[str]] = None,
    name: Optional[str] = None,
    is_input: bool = False,
    is_interface: bool = False,
    description: Optional[str] = None,
    directives: Optional[Sequence[object]] = (),
) -> Type[StrawberryTypeFromPydantic[TPydanticModel]]:
    all_fields = fields is None

    bases = strawberry_bases or tuple()

    prefix_inner_type = "__strawberry_inputtype_" if is_input else "__strawberry_type_"

    klass_name = f"{prefix_inner_type}{pydantic_type.__name__}{''.join((base.__name__ for base in bases))}"

    if klass_name in _strawberry_type_registry:
        return _strawberry_type_registry[klass_name]

    psuedo_klass = type(klass_name, bases, {})

    strawberry_type = pydantic_to_strawberry(
        pydantic_type,
        fields=fields,
        name=name,
        is_input=is_input,
        is_interface=is_interface,
        description=description,
        directives=directives,
        all_fields=all_fields,
    )(psuedo_klass)

    _strawberry_type_registry[klass_name] = strawberry_type

    return strawberry_type


def create_strawberry_resolver_from_callable(func: Callable) -> StrawberryResolver:
    meta = getattr(func, "__qs_metadata__", {}).get("graphql", {})
    args_pydantic_type = getattr(func, "__qs_args_pydantic_type__", None)
    ret_pydantic_type = getattr(func, "__qs_ret_pydantic_type__", None)

    args_strawberry_type = (
        create_strawberry_model_from_pydantic_type(args_pydantic_type, is_input=True)
        if args_pydantic_type
        else None
    )
    ret_strawberry_type = (
        create_strawberry_model_from_pydantic_type(ret_pydantic_type)
        if ret_pydantic_type
        else None
    )

    #  We cant have a generic *args, **kwargs resolver since strawberry pulls the arguments off.
    # TODO: Find a better way to handle this.
    if args_strawberry_type and ret_strawberry_type:

        async def resolver(args: args_strawberry_type) -> ret_strawberry_type:
            to_pydantic = args.to_pydantic()

            result = func(to_pydantic)

            if asyncio.iscoroutine(result):
                result = await result

            return ret_strawberry_type.from_pydantic(result)

    elif args_strawberry_type:

        async def resolver(args: args_strawberry_type):
            to_pydantic = args.to_pydantic()
            result = func(to_pydantic)

            if asyncio.iscoroutine(result):
                result = await result

            return result
    elif ret_strawberry_type:

        async def resolver() -> ret_strawberry_type:
            result = func()

            if asyncio.iscoroutine(result):
                result = await result

            return ret_strawberry_type.from_pydantic(result)
    else:
        resolver = func

    return StrawberryResolver(
        func=resolver, description=func.__doc__, type_override=ret_strawberry_type
    )


def create_query_from_queryables(query_resolvers: List[Callable]) -> type:
    fields = {}
    for resolver in query_resolvers:
        meta = getattr(resolver, "__qs_metadata__", {}).get("graphql", {})
        field_name = meta.get("name") or resolver.__name__
        strawberry_resolver = create_strawberry_resolver_from_callable(resolver)

        field = strawberry.field(resolver=strawberry_resolver)

        fields[field_name] = field
    QueryType = type("Query", (), fields)
    return strawberry.type(QueryType)


def create_mutation_from_mutatables(mutation_resolvers: List[Callable]) -> type:
    fields = {}
    for resolver in mutation_resolvers:
        meta = getattr(resolver, "__qs_metadata__", {}).get("graphql", {})
        field_name = meta.get("name") or resolver.__name__
        strawberry_resolver = create_strawberry_resolver_from_callable(resolver)
        fields[field_name] = strawberry.field(
            resolver=strawberry_resolver, description=resolver.__doc__
        )

    MutationType = type("Mutation", (), fields)
    return strawberry.type(MutationType)


def create_subscription_from_queryables(subscription_resolvers: List[Callable]) -> type:
    fields = {}
    for resolver in subscription_resolvers:
        meta = getattr(resolver, "__qs_metadata__", {}).get("graphql", {})
        field_name = meta.get("name") or resolver.__name__
        fields[field_name] = strawberry.field(
            resolver=resolver, description=resolver.__doc__
        )
    SubscriptionType = type("Subscription", (), fields)
    return strawberry.type(SubscriptionType)


@strawberry.field
def noop() -> str:
    return "noop"


def create_graphql_schema(
    queryables: List[Callable],
    mutatables: List[Callable],
    subscriptions: List[Callable],
) -> strawberry.Schema:
    query = (
        create_query_from_queryables(queryables)
        if queryables
        else strawberry.type(type("EmptyQuery", (), {"noop": noop}))
    )
    mutation = create_mutation_from_mutatables(mutatables) if mutatables else None
    subscription = (
        create_subscription_from_queryables(subscriptions) if subscriptions else None
    )
    return strawberry.Schema(query=query, mutation=mutation, subscription=subscription)


def create_schema_from_collections(
    collections: List[QuickScriptCollection],
) -> strawberry.Schema:
    # Combine all collections into one.
    combined = QuickScriptCollection(name="graphql_combined")
    for coll in collections:
        combined.add_collection(coll)

    # Separate resolvers by GraphQL metadata.
    query_resolvers = []
    mutation_resolvers = []
    subscription_resolvers = []
    for func in combined.queryables + combined.mutatables:
        if hasattr(func, "__qs_metadata__") and "graphql" in func.__qs_metadata__:
            meta = func.__qs_metadata__["graphql"]
            if meta.get("subscription", False):
                subscription_resolvers.append(func)
            elif func in combined.mutatables:
                mutation_resolvers.append(func)
            else:
                query_resolvers.append(func)

    return create_graphql_schema(
        queryables=query_resolvers,
        mutatables=mutation_resolvers,
        subscriptions=subscription_resolvers,
    )


def create_graphql_app(
    collections: List[QuickScriptCollection],
    enable_graphiql: bool = True,
    graphql_kwargs: Optional[Dict[str, Any]] = None,
    starlette_kwargs: Optional[Dict[str, Any]] = None,
) -> Starlette:
    graphql_schema = create_schema_from_collections(collections)
    graphql_app = GraphQL(
        graphql_schema, graphiql=enable_graphiql, **(graphql_kwargs or {})
    )
    app = Starlette(**(starlette_kwargs or {}))
    app.add_route("/graphql", graphql_app)
    app.add_websocket_route("/graphql", graphql_app)
    return app


def run_graphql_server(
    collections: List[QuickScriptCollection],
    host: str = "0.0.0.0",
    port: int = 8000,
    enable_graphiql: bool = True,
    graphql_kwargs: Optional[Dict[str, Any]] = None,
    starlette_kwargs: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Run a barebones Starlette server hosting the GraphQL API.
    """
    # Create the GraphQL ASGI app.
    app = create_graphql_app(
        collections,
        enable_graphiql=enable_graphiql,
        graphql_kwargs=graphql_kwargs,
        starlette_kwargs=starlette_kwargs,
    )

    import uvicorn

    uvicorn.run(app, host=host, port=port)


def run_graphql_server_from_path(
    path: str,
    host: str = "0.0.0.0",
    port: int = 8000,
    enable_graphiql: bool = True,
    graphql_kwargs: Optional[Dict[str, Any]] = None,
    starlette_kwargs: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Run a barebones Starlette server hosting the GraphQL API.
    """
    if os.path.isdir(path):
        collections = collect_from_dir(path)
    elif os.path.isfile(path):
        collections = collect_from_file(path)
    else:
        raise ValueError(f"Invalid path: {path}")

    run_graphql_server(
        [collections],
        host=host,
        port=port,
        enable_graphiql=enable_graphiql,
        graphql_kwargs=graphql_kwargs,
        starlette_kwargs=starlette_kwargs,
    )
