import sys
import os
import pytest
import pyarrow as pa
from pydantic import BaseModel

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from quickscript import queryable


class ArrowQueryArgs(BaseModel):
    key: str


@pytest.mark.asyncio
async def test_arrow_basic_table():
    @queryable(frame_type="arrow")
    async def query_arrow(args: ArrowQueryArgs) -> pa.Table:
        data = {"name": ["Alice", "Bob", "Charlie"], "key": [args.key] * 3}
        return pa.Table.from_pydict(data)

    result = await query_arrow(ArrowQueryArgs(key="test"))
    assert isinstance(result, pa.Table)
    assert result.num_rows == 3
    assert result.column_names == ["name", "key"]


@pytest.mark.asyncio
async def test_arrow_with_metadata():
    @queryable(frame_type="arrow")
    async def query_arrow_meta(args: ArrowQueryArgs) -> pa.Table:
        data = {"name": ["Alice", "Bob"], "key": [args.key, args.key * 2]}
        table = pa.Table.from_pydict(data)
        return table, {"source": "test", "timestamp": "2025-01-01"}

    result, metadata = await query_arrow_meta(ArrowQueryArgs(key="A"))
    assert isinstance(result, pa.Table)
    assert metadata["source"] == "test"
    assert result.num_rows == 2
    assert result.column("key").to_pylist() == ["A", "AA"]


@pytest.mark.asyncio
async def test_arrow_schema():
    @queryable(frame_type="arrow")
    async def query_schema(args: ArrowQueryArgs) -> pa.Table:
        schema = pa.schema([("name", pa.string()), ("key", pa.string())])
        data = [pa.array(["Alice", "Bob"]), pa.array([args.key, args.key])]
        return pa.Table.from_arrays(data, schema=schema)

    result = await query_schema(ArrowQueryArgs(key="test"))
    assert isinstance(result, pa.Table)
    assert result.schema.names == ["name", "key"]
    assert result.schema.types == [pa.string(), pa.string()]
