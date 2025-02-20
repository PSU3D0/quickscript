import sys
import os
import pytest
import polars as pl
from pydantic import BaseModel

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from quickscript import queryable


class PolarsQueryArgs(BaseModel):
    min_value: int


@pytest.mark.asyncio
async def test_polars_basic_frame():
    @queryable
    async def query_polars(args: PolarsQueryArgs) -> pl.DataFrame:
        data = {"id": [1, 2, 3, 4], "value": [10, 20, 30, 40]}
        return pl.DataFrame(data)

    result = await query_polars(PolarsQueryArgs(min_value=25))
    assert isinstance(result, pl.DataFrame)
    assert len(result) == 4
    assert result.columns == ["id", "value"]


@pytest.mark.asyncio
async def test_polars_with_metadata():
    @queryable
    async def query_polars_meta(args: PolarsQueryArgs) -> pl.DataFrame:
        data = {"id": [1, 2], "value": [args.min_value, args.min_value * 2]}
        df = pl.DataFrame(data)
        return df, {"source": "test", "timestamp": "2025-01-01"}

    result, metadata = await query_polars_meta(PolarsQueryArgs(min_value=15))
    assert isinstance(result, pl.DataFrame)
    assert metadata["source"] == "test"
    assert len(result) == 2
    assert result["value"].to_list() == [15, 30]


@pytest.mark.asyncio
async def test_polars_filtered_frame():
    @queryable
    async def query_filtered(args: PolarsQueryArgs) -> pl.DataFrame:
        data = {"id": [1, 2, 3, 4], "value": [10, 20, 30, 40]}
        df = pl.DataFrame(data)
        return df.filter(pl.col("value") > args.min_value)

    result = await query_filtered(PolarsQueryArgs(min_value=25))
    assert isinstance(result, pl.DataFrame)
    assert len(result) == 2  # Only values > 25
    assert result["value"].to_list() == [30, 40]
