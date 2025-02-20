import sys
from unittest import mock
import os
import runpy

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_sample_usage():
    with mock.patch(
        "sys.argv", ["quickscript.py", "--input_file=test.py", "--mode", "fast"]
    ):
        with mock.patch("builtins.print") as mock_print:
            result = runpy.run_module("quickscript", run_name="__main__")

    assert mock_print.call_count == 1
    assert mock_print.call_args[0][0] == "CLI args: input_file='test.py' mode='fast'"
