<div align="center">
  <h1 style="color:#4F46E5;">quickscript</h1>
  <p>
    <strong>A one-file microframework for robust, single-file agent and utility scripts</strong> ⚡️🚀
  </p>
  <!-- <img alt="quickscript banner" src="https://via.placeholder.com/600x150?text=quickscript" /> -->

</div>

[![pypi](https://img.shields.io/pypi/v/quickscript.svg)](https://pypi.org/project/quickscript/)
[![python](https://img.shields.io/pypi/pyversions/quickscript.svg)](https://pypi.org/project/quickscript/)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![codecov](https://codecov.io/gh/PSU3D0/quickscript/branch/main/graphs/badge.svg)](https://codecov.io/github/PSU3D0/quickscript)

---

## Overview 🌟

**quickscript** is an opinionated microframework designed for **single-file agent/worker scripts**. It provides robust guardrails for the trickiest parts of scripting—such as querying external data, mutating state, and handling side effects—while remaining as lightweight and flexible as possible. With a **pydantic-first** approach, your scripts become self-documenting, type-safe, and even serializable—unlocking powerful possibilities like automatic spec generation and easy frontend conversion.

### Who is this for?

1. You're using pydantic as either a first or second-order dependency in your project
2. You use LLM's or agent systems to heavily automate your coding workflow
3. You want to ensure your scripts have strong type safety, particularly around consequential actions like data mutation, side effects, and external interactions
4. You want to minimize abstractions and dependency overhead.


---

## Features ✨

- **Single-File Simplicity:**
  Everything you need is bundled in one compact file, making it perfect for quick experiments or production-ready utilities.

- **Guarded Queryables & Mutatables:**
  - **Queryables:** Fetch and validate data (JSON, DB records, file inputs) using Pydantic models.
  - **Mutatables:** Execute actions with side effects like POST requests, notifications, or updating external systems.

- **Dataframe Integration:**
  - First-class support for Pandas, Polars, and PyArrow DataFrames.
  - Automatically validate the return type of your functions against the specified dataframe type.

- **CLI Integration:**
  Automatically build command-line interfaces from your Pydantic models.

- **LLM-Friendly:**
  Its brevity and rich docstrings make it ideal as context for large language models (LLMs), ensuring consistent patterns in generated code. Add this script as read-only context to **aider** or **cursor** to guide the LLM on usage

- **Lightweight & Extensible:**
  No bloat—just the essentials, with optional features you can integrate as your project grows.


### Implications

- All data fetching, mutation, and side effects have explicit interfaces with optional runtime typechecking.
- Your script arguments could be **exposed as a tool to LLMs**
- Decorator usage can be "discovered" to automatically generate complete documentation, including types.
- Scripts can be organized into **collections** and exposed to frontend frameworks in a myriad of ways.


---

## Real-World Use Cases 🚀

- **Data Processing Pipelines:**
  Build single-file scripts that retrieve, validate, and process data using familiar libraries like pandas, polars, or pyarrow.

- **Microservices & API Agents:**
  Quickly spin up agents to handle API calls, manage notifications, or update databases with robust runtime checks.

- **Automation & DevOps Utilities:**
  Create deployment scripts, system monitoring agents, or file processors that are both lightweight and safe to run in production.

- **Rapid Prototyping:**
  Experiment with new ideas without the overhead of a full-fledged framework—get feedback fast and iterate.

- **LLM Assisted Development:**
  Use quickscript as a template for LLMs to generate or enhance single-file scripts, ensuring consistency in coding patterns.

---

## Getting Started 📦

1. **Clone the Repository:**

   ```bash
   git clone https://github.com/PSU3D0/quickscript.git
   cd quickscript
   ```

2. **Integrate quickscript in Your Project:**

   Simply copy the `quickscript.py` file into your project directory and import the decorators as needed:

   ```python
   from quickscript import queryable, mutatable, script
   ```

3. **Write Your Script:**

   Here are several salient code examples demonstrating different capabilities of quickscript:

   ### Example 1: Basic Script Usage

   ```python
   from pydantic import BaseModel, Field
   from quickscript import script

   class CLIArgs(BaseModel):
       """
       Command-line arguments for the script.
       """
       input_file: str = Field("default.txt", description="Path to the input file")
       mode: str = Field(..., description="Operation mode", example="fast")

   @script(arg_parser_model=CLIArgs)
   def main(cli_args: CLIArgs, logger):
       logger.info(f"Running in {cli_args.mode} mode with file: {cli_args.input_file}")
       print(f"CLI args: {cli_args}")

   if __name__ == "__main__":
       main()
   ```

   ### Example 2: Defining a Queryable Function

   ```python
   from pydantic import BaseModel
   from quickscript import queryable

   class DataQueryArgs(BaseModel):
       query: str

   @queryable
   async def fetch_data(args: DataQueryArgs) -> "pandas.DataFrame":
       import pandas as pd
       # Simulate fetching data based on a query
       data = {"id": [1, 2, 3], "value": ["A", "B", "C"]}
       df = pd.DataFrame(data)
       return df

   # To use:
   # import asyncio
   # asyncio.run(fetch_data(DataQueryArgs(query="select * from table")))
   ```

   ### Example 3: Creating a Mutatable Function

   ```python
   from pydantic import BaseModel
   from quickscript import mutatable

   class UpdateArgs(BaseModel):
       record_id: int
       status: str

   class UpdateResult(BaseModel):
       success: bool
       message: str

   @mutatable
   async def update_record(args: UpdateArgs) -> UpdateResult:
       # Simulate an update operation (e.g., a POST request)
       return UpdateResult(success=True, message=f"Record {args.record_id} updated to {args.status}")

   # To use:
   # import asyncio
   async def my_function_that_does_anything():
      result = await update_record(UpdateArgs(record_id=42, status="active"))
      print(result)
   ```

4. **Run Your Script:**

   ```bash
   python your_script.py --input_file data.txt --mode fast
   ```

---


## DataFrame Integration with Pandas, Polars, and PyArrow 🚀

**quickscript** seamlessly integrates with popular data processing libraries, ensuring that your data retrieval functions are type-safe and production-ready. With the `@queryable` decorator, you can enforce that your functions return the correct frame-like object—whether it’s a Pandas DataFrame, a Polars DataFrame, or a PyArrow Table.

> **Tip:** To use these integrations, make sure to install the necessary libraries:
>
> ```bash
> pip install pandas polars pyarrow
> ```

### Example: Pandas Integration

```python
from pydantic import BaseModel
from quickscript import queryable

class PandasQueryArgs(BaseModel):
    filter_value: int

@queryable
async def fetch_pandas_data(args: PandasQueryArgs) -> "pandas.DataFrame":
    import pandas as pd
    # Simulate fetching data and applying a filter using Pandas
    data = {
        "id": [1, 2, 3, 4],
        "value": [10, 20, 30, 40]
    }
    df = pd.DataFrame(data)
    return df[df["value"] > args.filter_value]

# Usage:
# import asyncio
# asyncio.run(fetch_pandas_data(PandasQueryArgs(filter_value=25)))
```

### Example: Polars Integration

```python
from pydantic import BaseModel
from quickscript import queryable

class PolarsQueryArgs(BaseModel):
    min_value: int

@queryable
async def fetch_polars_data(args: PolarsQueryArgs) -> "polars.DataFrame":
    import polars as pl
    # Simulate fetching data and filtering using Polars
    data = {
        "id": [1, 2, 3, 4],
        "value": [15, 25, 35, 45]
    }
    df = pl.DataFrame(data)
    return df.filter(pl.col("value") > args.min_value)

# Usage:
# import asyncio
# asyncio.run(fetch_polars_data(PolarsQueryArgs(min_value=30)))
```

### Example: PyArrow Integration

```python
from pydantic import BaseModel
from quickscript import queryable

class ArrowQueryArgs(BaseModel):
    key: str

@queryable
async def fetch_arrow_data(args: ArrowQueryArgs) -> "pyarrow.Table":
    import pyarrow as pa
    # Simulate creating a table with PyArrow
    data = {
        "name": ["Alice", "Bob", "Charlie"],
        "key": [args.key, args.key * 2, args.key * 3]
    }
    table = pa.table(data)
    return table

# Usage:
# import asyncio
# asyncio.run(fetch_arrow_data(ArrowQueryArgs(key="A")))
```

---


## Why quickscript? 🤔

Large language models are awesome at drafting code quickly, but often have substantial variance in the quality and style of the code they generate, particularly as it pertains to **fetching/mutating data** and handling **side effects**.

For engineers who are using LLM's or agent systems to produce scripts in large volumes, quickscript provides a minimal (1 file, 1 dependency) framework to **guide** language models towards producing more reliable, robust, and performant scripts.

- **Efficiency:**
  A minimal framework means less overhead and faster prototyping.

- **Robustness:**
  Built-in type checking, dependency validation, and environment variable checks catch errors early.

- **Versatility:**
  Simplicity and flexibility make quickscript perfect for everything from quick utility scripts to chaining together more complex agent-based workflows.

- **Developer-Friendly:**
  Rich documentation and clear patterns let you focus on your business logic.

---

## Contributing & Feedback 💬

Contributions, suggestions, and bug reports are very welcome! Please open an issue or submit a pull request. Let’s build something awesome together!

<div align="center">
  <img src="https://img.shields.io/badge/Happy_Coding-💻-brightgreen" alt="Happy Coding">
</div>

---

## License 📄

This project is licensed under the [MIT License](LICENSE) © 2025 Frankie Colson

---

Made with ❤️ by [PSU3D0](https://github.com/PSU3D0) @ [Coltec](https://coltec.ai)
*Simple, safe, and supercharged scripting in a single file!*
