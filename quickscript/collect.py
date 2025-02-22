import inspect
import sys
from typing import Callable, List, Optional, Dict
from pathlib import Path
import importlib.util


class QuickScriptCollection:
    def __init__(self, name: str):
        # Hold references to functions by category.
        self.queryables: List[Callable] = []
        self.mutatables: List[Callable] = []
        self.scripts: List[Callable] = []
        self.name = name

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"QuickScriptCollection(name={self.name}, queryables={len(self.queryables)}, mutatables={len(self.mutatables)}, scripts={len(self.scripts)})"

    def add(self, func: Callable) -> None:
        """Add a function if it appears to be part of the QuickScript ecosystem."""
        sig = inspect.signature(func)
        # Only add if function is decorated (has __qs_metadata__) or looks like a script (has a `cli_args` parameter)
        if not hasattr(func, "__qs_metadata__") and "cli_args" not in sig.parameters:
            return

        # If the function takes a CLI argument, classify it as a script.
        if "cli_args" in sig.parameters:
            self.scripts.append(func)
        elif func.__qs_mode__ == "queryable":
            self.queryables.append(func)
        elif func.__qs_mode__ == "mutatable":
            self.mutatables.append(func)

    def add_collection(self, collection: "QuickScriptCollection") -> None:
        """Add the contents of another collection."""
        self.queryables.extend(collection.queryables)
        self.mutatables.extend(collection.mutatables)
        self.scripts.extend(collection.scripts)

    def bundle(self, *collections: "QuickScriptCollection") -> "QuickScriptCollection":
        """Combine this collection with one or more other collections and return a bundled collection."""
        bundled = QuickScriptCollection(
            name=f"{self.name} + {', '.join([c.name for c in collections])}"
        )
        bundled.add_collection(self)
        for coll in collections:
            bundled.add_collection(coll)
        return bundled

    def filter_by_namespace(
        self, namespace: str, category: Optional[str] = None
    ) -> List[Callable]:
        """
        Return all functions that have metadata for the provided namespace.
        Optionally limit the result to one of the recognized categories ('queryable', 'mutatable', or 'script').
        """
        result = []
        for func in self.queryables + self.mutatables + self.scripts:
            if hasattr(func, "__qs_metadata__"):
                meta: Dict = func.__qs_metadata__
                if namespace in meta:
                    result.append(func)
        if category:
            category = category.lower()
            if category == "queryable":
                result = [f for f in result if f in self.queryables]
            elif category == "mutatable":
                result = [f for f in result if f in self.mutatables]
            elif category == "script":
                result = [f for f in result if f in self.scripts]
        return result


def collect_from_file(file: str) -> QuickScriptCollection:
    """
    Collect functions from a single file.
    """
    file = Path(file)

    collection = QuickScriptCollection(name=file.stem)
    spec = importlib.util.spec_from_file_location(file.stem, str(file))
    if spec and spec.loader:
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception:
            # Skip files that fail to import.
            return collection
        for _, obj in inspect.getmembers(module):
            if inspect.isfunction(obj) and hasattr(obj, "__qs_metadata__"):
                collection.add(obj)
                # We need to add to modules since strawberry (graphql) needs to find the module.
                # TODO: Find a way to avoid adding to sys.modules completely.
                sys.modules[module.__name__] = module
    return collection


def collect_from_dir(directory: str) -> QuickScriptCollection:
    """
    Traverse a directory (recursively) to find and import Python files and collect any function
    that is part of QuickScript (i.e. decorated with our decorators or accepting CLI args).
    """
    collection = QuickScriptCollection(name=directory)
    base_path = Path(directory)
    for py_file in base_path.rglob("*.py"):
        file_collection = collect_from_file(py_file)
        collection.add_collection(file_collection)
    return collection
