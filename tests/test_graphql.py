from pydantic import BaseModel
import pytest

from quickscript.quickscript import mutatable, queryable
from quickscript.plugins.graphql import supports_graphql
from quickscript.server.graphql import (
    create_graphql_schema,
)


@pytest.mark.asyncio
async def test_graphql_queryable():
    class PandasQueryArgs(BaseModel):
        name: str
        age: int

    class SimpleResponse(BaseModel):
        message: str

    @queryable
    @supports_graphql
    async def query_no_args() -> SimpleResponse:
        return SimpleResponse(message="Hello, world!")

    @queryable
    @supports_graphql
    async def query_with_args(args: PandasQueryArgs) -> SimpleResponse:
        return SimpleResponse(
            message=f"Hello, {args.name}! You are {args.age} years old."
        )

    result = await query_with_args(PandasQueryArgs(name="John", age=30))
    assert result.message == "Hello, John! You are 30 years old."

    result = await query_no_args()
    assert result.message == "Hello, world!"

    schema = create_graphql_schema(
        queryables=[query_no_args, query_with_args], mutatables=[], subscriptions=[]
    )
    assert schema is not None

    # TODO Add more assertions


@pytest.mark.asyncio
async def test_graphql_mutatable():
    class PandasQueryArgs(BaseModel):
        name: str
        age: int

    class SimpleResponse(BaseModel):
        message: str

    @mutatable
    @supports_graphql
    async def mutate_no_args() -> SimpleResponse:
        return SimpleResponse(message="Hello, world!")

    @mutatable
    @supports_graphql
    async def mutate_with_args(args: PandasQueryArgs) -> SimpleResponse:
        return SimpleResponse(
            message=f"Hello, {args.name}! You are {args.age} years old."
        )

    schema = create_graphql_schema(
        queryables=[], mutatables=[mutate_no_args, mutate_with_args], subscriptions=[]
    )
    assert schema is not None
