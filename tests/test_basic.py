import sys
import os
import logging
import pytest
from pydantic import BaseModel, Field
import pandas as pd
from unittest import mock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from quickscript import queryable, mutatable, script, get_script_logger, get_script_args


# -----------------------------------------------------------------------------
# Dummy Models for Testing
# -----------------------------------------------------------------------------
class DummyArgs(BaseModel):
    num: int


class DummyResult(BaseModel):
    result: int


class InputModel(BaseModel):
    value: int


class OutputModel(BaseModel):
    output: int


# -----------------------------------------------------------------------------
# Test 1: Queryable function that returns a valid BaseModel ("model") result.
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_queryable_valid_model_return():
    @queryable()
    async def dummy_query(args: DummyArgs) -> DummyResult:
        return DummyResult(result=args.num * 2)

    args = DummyArgs(num=5)
    result = await dummy_query(args)
    assert isinstance(result, DummyResult)
    assert result.result == 10


@pytest.mark.asyncio
async def test_queryable_with_env_var_requirements():
    @queryable(env_vars={"TEST_ENV_VAR": int})
    async def query_with_env_var(args: DummyArgs) -> DummyResult:
        return DummyResult(result=args.num * 2)

    with pytest.raises(EnvironmentError) as excinfo:
        await query_with_env_var(DummyArgs(num=1))
    assert "TEST_ENV_VAR" in str(excinfo.value)

    @queryable(env_vars={"TEST_ENV_VAR": int})
    async def query_with_invalid_type(args: DummyArgs) -> DummyResult:
        return DummyResult(result=args.num * 2)

    with mock.patch.dict(os.environ, {"TEST_ENV_VAR": "not_an_int"}):
        with pytest.raises(ValueError) as excinfo:
            await query_with_invalid_type(DummyArgs(num=1))
        assert "TEST_ENV_VAR" in str(excinfo.value)


# -----------------------------------------------------------------------------
# Test 2: Queryable function called with an invalid positional argument type.
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_queryable_invalid_positional_type():
    @queryable()
    async def dummy_query(args: DummyArgs) -> DummyResult:
        return DummyResult(result=args.num * 2)

    # Passing a plain dict instead of a DummyArgs instance
    with pytest.raises(TypeError) as excinfo:
        await dummy_query({"num": 5})
    assert "must be an instance of" in str(excinfo.value)


# -----------------------------------------------------------------------------
# Test 3: Queryable function missing a return annotation.
# -----------------------------------------------------------------------------
def test_queryable_missing_return_annotation():
    with pytest.raises(TypeError) as excinfo:

        @queryable()
        async def no_return(args: DummyArgs):
            return DummyResult(result=args.num)

    assert "must have a return type annotation" in str(excinfo.value)


# -----------------------------------------------------------------------------
# Test 4: Queryable function declared to return a pandas frame but returns an incorrect type.
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_queryable_incorrect_frame_return():
    @queryable()
    async def query_frame(args: DummyArgs) -> pd.DataFrame:
        # Incorrectly return a list instead of a DataFrame
        return [1, 2, 3]

    with pytest.raises(TypeError) as excinfo:
        await query_frame(DummyArgs(num=1))
    # Now expecting a generic error about a valid frame-like object
    assert "expected to return a valid frame-like object" in str(excinfo.value)


# -----------------------------------------------------------------------------
# Test 5: Queryable function correctly returning a valid pandas DataFrame.
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_queryable_valid_frame_return():
    @queryable()
    async def query_frame(args: DummyArgs) -> pd.DataFrame:
        # Return a valid DataFrame (or a tuple with optional metadata)
        df = pd.DataFrame({"num": [args.num, args.num + 1]})
        return df, {"source": "test"}

    result = await query_frame(DummyArgs(num=3))
    frame_obj = result[0] if isinstance(result, tuple) else result
    assert isinstance(frame_obj, pd.DataFrame)
    assert frame_obj["num"].tolist() == [3, 4]


# -----------------------------------------------------------------------------
# Test 6: Queryable function returning a list of BaseModel instances.
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_queryable_model_list_return():
    @queryable()
    async def query_list(args: DummyArgs) -> list[DummyResult]:
        # Return a list of DummyResult instances
        return [DummyResult(result=args.num), DummyResult(result=args.num + 10)]

    results = await query_list(DummyArgs(num=7))
    assert isinstance(results, list)
    assert all(isinstance(item, DummyResult) for item in results)
    assert results[0].result == 7
    assert results[1].result == 17


# -----------------------------------------------------------------------------
# Test 7: Mutatable function with valid input and output.
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mutatable_valid():
    @mutatable()
    async def mutate_value(args: InputModel) -> OutputModel:
        # Simulate a side effect by just performing a calculation
        return OutputModel(output=args.value * 3)

    inp = InputModel(value=4)
    result = await mutate_value(inp)
    assert isinstance(result, OutputModel)
    assert result.output == 12


# -----------------------------------------------------------------------------
# Test 8: Mutatable function returning an invalid (non-BaseModel) result.
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mutatable_invalid_return():
    @mutatable()
    async def bad_mutation(args: InputModel) -> OutputModel:
        # Incorrectly return a plain dictionary instead of an OutputModel instance
        return {"output": args.value * 3}

    with pytest.raises(TypeError) as excinfo:
        await bad_mutation(InputModel(value=4))
    assert "must return" in str(excinfo.value)


# -----------------------------------------------------------------------------
# Test 9: Dependency checking – function requires a non-existent dependency.
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_dependencies_check():
    fake_dependency = "nonexistent_dependency_12345"

    @queryable(dependencies=[fake_dependency])
    async def query_with_dependency(args: DummyArgs) -> DummyResult:
        return DummyResult(result=args.num)

    with pytest.raises(ImportError) as excinfo:
        await query_with_dependency(DummyArgs(num=1))
    assert fake_dependency in str(excinfo.value)


# -----------------------------------------------------------------------------
# Test 10: Script decorator properly sets up CLI args and logger.
# -----------------------------------------------------------------------------
def test_script_decorator_cli_args(monkeypatch, capsys):
    # Define a CLI argument model.
    class CLIArgs(BaseModel):
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

    # Prepare fake command-line arguments.
    test_args = ["prog", "--input_file", "test.txt", "--mode", "fast"]
    monkeypatch.setattr(sys, "argv", test_args)

    called = False

    @script(arg_parser_model=CLIArgs)
    def main(cli_args: CLIArgs, logger: logging.Logger):
        nonlocal called
        called = True
        # Inside the script, we can also retrieve the context logger/args.
        ctx_logger = get_script_logger()
        ctx_args = get_script_args()
        # Check that the CLI args match our test input.
        assert cli_args.input_file == "test.txt"
        assert cli_args.mode == "fast"
        # Logger should be a Logger instance.
        assert isinstance(logger, logging.Logger)
        # The context-provided logger should be the same as the passed logger.
        assert logger is ctx_logger
        print("Script executed.")

    main()
    captured = capsys.readouterr().out
    assert "Script executed." in captured
    assert called is True


@pytest.mark.asyncio
async def test_script_decorator_cli_args_async(monkeypatch, capsys):
    # Define a CLI argument model.
    class CLIArgs(BaseModel):
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

    # Prepare fake command-line arguments.
    test_args = ["prog", "--input_file", "test.txt", "--mode", "fast"]
    monkeypatch.setattr(sys, "argv", test_args)

    called = False

    @script(arg_parser_model=CLIArgs)
    async def main(cli_args: CLIArgs, logger: logging.Logger):
        nonlocal called
        called = True
        ctx_logger = get_script_logger()
        ctx_args = get_script_args()
        assert cli_args.input_file == "test.txt"
        assert cli_args.mode == "fast"
        assert isinstance(logger, logging.Logger)
        assert logger is ctx_logger
        print("Script executed.")

    await main()
    captured = capsys.readouterr().out
    assert "Script executed." in captured
    assert called is True
