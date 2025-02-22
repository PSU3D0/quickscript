from pydantic import Field, BaseModel

# sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from quickscript import queryable
from quickscript.plugins.graphql import supports_graphql
from quickscript.quickscript import mutatable
from quickscript.plugins.zeromq import supports_zeromq


class SimpleResponse(BaseModel):
    message: str


@queryable
@supports_graphql
@supports_zeromq
async def hello_world() -> SimpleResponse:
    return SimpleResponse(message="Hello, world!")


class MoreComplexArgs(BaseModel):
    name: str = Field(description="The name of the person to greet.")
    age: int = Field(description="The age of the person to greet.")


@queryable
@supports_graphql
async def more_complex(args: MoreComplexArgs) -> SimpleResponse:
    return SimpleResponse(message=f"Hello, {args.name}! You are {args.age} years old.")


@mutatable
@supports_graphql
async def mutate_no_args() -> SimpleResponse:
    return SimpleResponse(message="Hello, world!")


@mutatable
@supports_graphql
async def mutate_with_args(args: MoreComplexArgs) -> SimpleResponse:
    return SimpleResponse(message=f"Hello, {args.name}! You are {args.age} years old.")
