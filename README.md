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
  - **Queryables:** For fetching and validating data (JSON, DB records, file inputs) using Pydantic models.
  - **Mutatables:** For actions with side effects like POST requests, notifications, or updating external systems.

- **CLI Integration:**
  Automatically build command-line interfaces from your Pydantic models.

- **LLM-Friendly:**
  Its brevity and rich docstrings make it ideal as context for large language models (LLMs), ensuring consistent patterns in generated code.

- **Lightweight & Extensible:**
  No bloat—just the essentials, with optional features that you can integrate as your project grows.

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

## Upcoming Features 🔮

- **Auto-Bundling with Docker:**
  Support for top-of-file pragmas to automatically bundle your script with Docker for seamless serverless deployment.

- **DAG Tracking:**
  Optional dependency tracking for queryables, mutatables, and the introduction of a `@step` decorator to define execution flows.

- **Frontend Conversion:**
  Easily convert your single-file script into a lightweight frontend, opening the door to interactive applications.

---

## Getting Started 📦

1. **Clone the Repository:**

   ```bash
   git clone https://github.com/yourusername/quickscript.git
   cd quickscript
   ```

2. **Integrate quickscript in Your Project:**

   Simply copy the `quickscript.py` file into your project directory and import the decorators as needed:

   ```python
   from quickscript import queryable, mutatable, script
   ```

3. **Write Your Script:**

   Here’s a minimal example to get you started:

   ```python
   from pydantic import BaseModel, Field
   from quickscript import script, queryable, mutatable

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

4. **Run Your Script:**

   ```bash
   python your_script.py --input_file data.txt --mode fast
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

This project is licensed under the [MIT License](LICENSE) © 2025 Your Name

---

Made with ❤️ by [PSU3D0](https://github.com/PSU3D0) @ [Coltec](https://coltec.ai)
*Simple, safe, and supercharged scripting in a single file!*
