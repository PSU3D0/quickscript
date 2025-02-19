import sys
import os
import pytest
import pandas as pd
from pydantic import BaseModel

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from quickscript import queryable


class PandasQueryArgs(BaseModel):
    filter_value: int


@pytest.mark.asyncio
async def test_pandas_basic_frame():
    @queryable(frame_type="pandas")
    async def query_pandas(args: PandasQueryArgs) -> pd.DataFrame:
        data = {"id": [1, 2, 3, 4], "value": [10, 20, 30, 40]}
        return pd.DataFrame(data)

    result = await query_pandas(PandasQueryArgs(filter_value=25))
    assert isinstance(result, pd.DataFrame)
    assert len(result) == 4
    assert list(result.columns) == ["id", "value"]


@pytest.mark.asyncio
async def test_pandas_with_metadata():
    @queryable(frame_type="pandas")
    async def query_pandas_meta(args: PandasQueryArgs) -> pd.DataFrame:
        data = {"id": [1, 2], "value": [args.filter_value, args.filter_value * 2]}
        df = pd.DataFrame(data)
        return df, {"source": "test", "timestamp": "2025-01-01"}

    result, metadata = await query_pandas_meta(PandasQueryArgs(filter_value=15))
    assert isinstance(result, pd.DataFrame)
    assert metadata["source"] == "test"
    assert len(result) == 2
    assert result["value"].tolist() == [15, 30]


@pytest.mark.asyncio
async def test_pandas_filtered_frame():
    @queryable(frame_type="pandas")
    async def query_filtered(args: PandasQueryArgs) -> pd.DataFrame:
        data = {"id": [1, 2, 3, 4], "value": [10, 20, 30, 40]}
        df = pd.DataFrame(data)
        return df[df["value"] > args.filter_value]

    result = await query_filtered(PandasQueryArgs(filter_value=25))
    assert isinstance(result, pd.DataFrame)
    assert len(result) == 2  # Only values > 25
    assert result["value"].tolist() == [30, 40]
