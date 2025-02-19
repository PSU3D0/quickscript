<div align="center">
  <h1 style="color:#4F46E5;">quickscript</h1>
  <p>
    <strong>A one-file microframework for robust, single-file agent and utility scripts</strong> ⚡️🚀
  </p>
  <!-- <img alt="quickscript banner" src="https://via.placeholder.com/600x150?text=quickscript" /> -->
</div>

---

## Overview 🌟

**quickscript** is an opinionated microframework designed for **single-file agent/worker scripts**. It provides robust guardrails for the trickiest parts of scripting—such as querying external data, mutating state, and handling side effects—while remaining as lightweight and flexible as possible. With a **pydantic-first** approach, your scripts become self-documenting, type-safe, and even serializable—unlocking powerful possibilities like automatic spec generation and easy frontend conversion.

---

## Features ✨

- **Single-File Simplicity:**
  Everything you need is bundled in one compact file, making it perfect for quick experiments or production-ready utilities.

- **Guarded Queryables & Mutatables:**
  - **Queryables:** Fetch and validate data (JSON, DB records, file inputs) using Pydantic models.
  - **Mutatables:** Execute actions with side effects like POST requests, notifications, or updating external systems.

- **CLI Integration:**
  Automatically build command-line interfaces from your Pydantic models.

- **LLM-Friendly:**
  Its brevity and rich docstrings make it ideal as context for large language models (LLMs), ensuring consistent patterns in generated code.

- **Lightweight & Extensible:**
  No bloat—just the essentials, with optional features you can integrate as your project grows.

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

   @queryable(frame_type="pandas")
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

   @mutatable()
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

@queryable(frame_type="pandas")
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

@queryable(frame_type="polars")
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

@queryable(frame_type="arrow")
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

- **Efficiency:**
  A minimal framework means less overhead and faster prototyping.

- **Robustness:**
  Built-in type checking, dependency validation, and environment variable checks catch errors early.

- **Versatility:**
  Perfect for everything from quick utility scripts to more complex agent workflows.

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
