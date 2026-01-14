# SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Jupyter Notebook manipulation tools for NeMo Agent Toolkit.

This module provides tools for creating, reading, writing, and executing
Jupyter Notebooks programmatically using the nbformat library.
"""

import json
import logging
import ast
from pathlib import Path
from typing import Literal

from pydantic import Field

from nat.builder.builder import Builder
from nat.builder.function_info import FunctionInfo
from nat.cli.register_workflow import register_function
from nat.data_models.function import FunctionBaseConfig

logger = logging.getLogger(__name__)


# -------------------------------------------------------------------------
# Configuration Class
# -------------------------------------------------------------------------

class NotebookToolConfig(FunctionBaseConfig, name="notebook"):
    """Configuration for the Jupyter Notebook tool.

    Provides operations for creating, reading, writing, executing, and validating
    Jupyter Notebooks programmatically.
    """
    root_dir: str = Field(
        default="/workspace",
        description="Root directory for notebook operations. Acts as a safety sandbox."
    )
    default_kernel: str = Field(
        default="python3",
        description="Default kernel name for new notebooks"
    )


# -------------------------------------------------------------------------
# Function Implementation
# -------------------------------------------------------------------------

@register_function(config_type=NotebookToolConfig)
async def notebook_tool(config: NotebookToolConfig, builder: Builder):
    """A Jupyter Notebook manipulation tool for creating, reading, and managing .ipynb files."""

    import nbformat
    from nbformat.v4 import new_code_cell
    from nbformat.v4 import new_markdown_cell
    from nbformat.v4 import new_notebook

    root_path = Path(config.root_dir)
    root_path.mkdir(parents=True, exist_ok=True)

    def _display_path(path: Path, requested_path: str) -> str:
        """Format a path for LLM-facing messages.

        - If the agent used the sandbox-style alias (requested path starts with '/workspace'),
          respond in that same '/workspace/...' style.
        - Otherwise, return the default local filesystem path (resolved under root_dir).
        """
        if requested_path.strip().startswith("/workspace"):
            root_resolved = root_path.resolve()
            path_resolved = path.resolve()
            if path_resolved.is_relative_to(root_resolved):
                rel = path_resolved.relative_to(root_resolved)
                rel_str = "" if rel == Path(".") else rel.as_posix()
                return f"/workspace/{rel_str}".rstrip("/")
        return str(path)

    def _resolve_path(path: str) -> Path:
        """Resolve and validate a notebook path."""
        input_path = Path(path)

        # Users/agents may provide sandbox paths like "/workspace/foo.ipynb".
        # This tool operates on the LOCAL filesystem, where "/workspace" may not exist.
        # Remap "/workspace/..." to be relative to configured root_dir.
        if input_path.is_absolute() and len(input_path.parts) >= 2 and input_path.parts[1] == "workspace":
            remapped = Path(*input_path.parts[2:])
            # Common agent mistake: using "/workspace/<root_dir>/..." where /workspace already maps to root_dir.
            # Avoid duplicating root_dir by stripping it if present.
            root_rel = Path(config.root_dir)
            if not root_rel.is_absolute() and remapped.parts[: len(root_rel.parts)] == root_rel.parts:
                remapped = Path(*remapped.parts[len(root_rel.parts) :])
            input_path = remapped

        if not input_path.is_absolute():
            target_path = root_path / input_path
        else:
            target_path = input_path

        # Enforce sandboxing: path must remain within root_dir.
        root_resolved = root_path.resolve()
        target_resolved = target_path.resolve()
        if not target_resolved.is_relative_to(root_resolved):
            raise ValueError(
                f"Invalid path '{path}'. Use a relative path under root_dir "
                f"('{config.root_dir}'), e.g. 'generated_files/notebook.ipynb'."
            )

        return target_path

    def _ensure_ipynb_extension(path: Path) -> Path:
        """Ensure the path has .ipynb extension."""
        if path.suffix.lower() != '.ipynb':
            path = path.with_suffix('.ipynb')
        return path

    def _get_default_metadata() -> dict:
        """Get default notebook metadata."""
        return {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": config.default_kernel
            },
            "language_info": {
                "name": "python",
                "version": "3.10.0",
                "mimetype": "text/x-python",
                "file_extension": ".py"
            }
        }

    async def _notebook_operation(
        operation: str,
        path: str = "",
        cells: str = "[]",
        position: int = -1,
        timeout: int = 600,
        save_output: bool = True,
        include_outputs: bool = True
    ) -> str:
        """
        Perform Jupyter Notebook operations.

        Args:
            operation: The action to perform. Valid options:
                - 'create': Create a new notebook with optional cells
                - 'read': Read and display notebook contents
                - 'add_cells': Add cells to an existing notebook
                - 'execute': Execute all cells in the notebook
                - 'validate': Validate notebook format
                - 'clear_outputs': Clear all cell outputs
            path: The notebook file path (should end with .ipynb)
            cells: JSON string of cells array. Each cell needs 'cell_type' (code/markdown) and 'source'.
                   Example: '[{"cell_type": "markdown", "source": "# Title"}, {"cell_type": "code", "source": "print(1)"}]'
            position: For 'add_cells': position to insert cells (-1 means append to end)
            timeout: For 'execute': timeout in seconds for each cell execution
            save_output: For 'execute': whether to save notebook with outputs
            include_outputs: For 'read': whether to include cell outputs in response
        """
        logger.info(f"Notebook operation: {operation} on {path}")

        try:
            # Some LLMs / agents incorrectly wrap the whole argument dict into the `operation` field
            # (e.g., operation="{'operation':'create','path':'/workspace/x.ipynb',...}") which then
            # causes schema validation errors and missing `path`. Be permissive here and unpack.
            if (not path) and isinstance(operation, str):
                candidate = operation.strip()
                if (candidate.startswith("{") and "path" in candidate and "operation" in candidate) or (
                    candidate.startswith("{'") and "path" in candidate and "operation" in candidate
                ):
                    unpacked: dict | None = None
                    try:
                        unpacked = json.loads(candidate)
                    except Exception:
                        try:
                            unpacked = ast.literal_eval(candidate)
                        except Exception:
                            unpacked = None

                    if isinstance(unpacked, dict):
                        operation = str(unpacked.get("operation", operation))
                        path = str(unpacked.get("path", path))
                        cells = str(unpacked.get("cells", cells))
                        position = int(unpacked.get("position", position))
                        timeout = int(unpacked.get("timeout", timeout))
                        save_output = bool(unpacked.get("save_output", save_output))
                        include_outputs = bool(unpacked.get("include_outputs", include_outputs))

            op = str(operation).lower().strip()
            if op not in {"create", "read", "add_cells", "execute", "validate", "clear_outputs"}:
                return (
                    f"Error: Unknown operation '{operation}'. "
                    "Valid operations: create, read, add_cells, execute, validate, clear_outputs"
                )

            if not str(path).strip():
                return "Error: Missing required argument 'path' (e.g. '/workspace/my_notebook.ipynb' or 'my_notebook.ipynb')."

            target_path = _resolve_path(path)
            target_path = _ensure_ipynb_extension(target_path)

            # Parse cells JSON if provided
            def _parse_cells(value: object) -> list[dict]:
                """Parse notebook cells from JSON or Python-literal list.

                Agents sometimes provide JSON-ish strings with unescaped control characters (e.g., raw
                newlines inside JSON strings). We accept:
                - Proper JSON (preferred)
                - JSON with control characters via strict=False
                - Python literal lists via ast.literal_eval (common when single quotes are used)
                """
                if value is None:
                    return []
                if isinstance(value, list):
                    return value
                if not isinstance(value, str):
                    raise ValueError(f"cells must be a JSON string or list, got: {type(value).__name__}")

                text = value.strip()
                if (not text) or text == "[]":
                    return []

                last_error: Exception | None = None
                for parser in (
                    lambda s: json.loads(s),
                    lambda s: json.loads(s, strict=False),
                    lambda s: ast.literal_eval(s),
                ):
                    try:
                        parsed = parser(text)
                        if parsed is None:
                            return []
                        if not isinstance(parsed, list):
                            raise ValueError(f"cells must decode to a list, got: {type(parsed).__name__}")
                        return parsed
                    except Exception as e:
                        last_error = e
                        continue

                raise ValueError(str(last_error) if last_error else "Unable to parse cells")

            try:
                cells_list = _parse_cells(cells)
            except Exception as e:
                return f"Error: Invalid cells format - {str(e)}"

            # --- OPERATION: CREATE ---
            if op == "create":
                target_path.parent.mkdir(parents=True, exist_ok=True)

                nb = new_notebook()
                nb.metadata.update(_get_default_metadata())

                for cell_info in cells_list:
                    cell_type = cell_info.get("cell_type", "code")
                    source = cell_info.get("source", "")
                    if cell_type == "code":
                        nb.cells.append(new_code_cell(source=source))
                    else:
                        nb.cells.append(new_markdown_cell(source=source))

                nbformat.validate(nb)

                with open(target_path, 'w', encoding='utf-8') as f:
                    nbformat.write(nb, f)

                cell_summary = f"{len(cells_list)} cells" if cells_list else "no cells"
                return f"Success: Notebook created at {_display_path(target_path, path)} with {cell_summary}."

            # --- OPERATION: READ ---
            elif op == "read":
                if not target_path.exists():
                    return f"Error: Notebook not found at {_display_path(target_path, path)}"

                with open(target_path, 'r', encoding='utf-8') as f:
                    nb = nbformat.read(f, as_version=4)

                result = {
                    "path": _display_path(target_path, path),
                    "nbformat": f"{nb.nbformat}.{nb.nbformat_minor}",
                    "kernel": nb.metadata.get("kernelspec", {}).get("name", "unknown"),
                    "cell_count": len(nb.cells),
                    "cells": []
                }

                for i, cell in enumerate(nb.cells):
                    cell_info = {
                        "index": i,
                        "cell_type": cell.cell_type,
                        "source": cell.source
                    }

                    if include_outputs and cell.cell_type == "code":
                        outputs = []
                        for output in cell.get("outputs", []):
                            output_info = {"output_type": output.get("output_type", "unknown")}
                            if "text" in output:
                                output_info["text"] = output["text"]
                            elif "data" in output:
                                output_info["data_types"] = list(output["data"].keys())
                                if "text/plain" in output["data"]:
                                    output_info["text"] = output["data"]["text/plain"]
                            outputs.append(output_info)
                        cell_info["outputs"] = outputs
                        cell_info["execution_count"] = cell.get("execution_count")

                    result["cells"].append(cell_info)

                return json.dumps(result, indent=2)

            # --- OPERATION: ADD_CELLS ---
            elif op == "add_cells":
                if not target_path.exists():
                    return f"Error: Notebook not found at {_display_path(target_path, path)}"

                with open(target_path, 'r', encoding='utf-8') as f:
                    nb = nbformat.read(f, as_version=4)

                new_cells = []
                for cell_info in cells_list:
                    cell_type = cell_info.get("cell_type", "code")
                    source = cell_info.get("source", "")
                    if cell_type == "code":
                        new_cells.append(new_code_cell(source=source))
                    else:
                        new_cells.append(new_markdown_cell(source=source))

                if position >= 0:
                    pos = min(position, len(nb.cells))
                    for i, cell in enumerate(new_cells):
                        nb.cells.insert(pos + i, cell)
                else:
                    nb.cells.extend(new_cells)

                nbformat.validate(nb)

                with open(target_path, 'w', encoding='utf-8') as f:
                    nbformat.write(nb, f)

                position_desc = f"at position {position}" if position >= 0 else "at the end"
                return f"Success: Added {len(cells_list)} cells {position_desc}. Notebook now has {len(nb.cells)} cells."

            # --- OPERATION: EXECUTE ---
            elif op == "execute":
                try:
                    from nbclient import NotebookClient
                    from nbclient.exceptions import CellExecutionError
                except ImportError:
                    return ("Error: nbclient is not installed. Install it with: pip install nbclient\n"
                            "This is required for notebook execution.")

                if not target_path.exists():
                    return f"Error: Notebook not found at {_display_path(target_path, path)}"

                with open(target_path, 'r', encoding='utf-8') as f:
                    nb = nbformat.read(f, as_version=4)

                client = NotebookClient(
                    nb,
                    timeout=timeout,
                    kernel_name=nb.metadata.get("kernelspec", {}).get("name", config.default_kernel)
                )

                execution_errors = []
                try:
                    await client.async_execute()
                except CellExecutionError as e:
                    execution_errors.append({
                        "cell_index": getattr(e, 'cell_index', "unknown"),
                        "error_type": type(e).__name__,
                        "message": str(e)
                    })

                if save_output:
                    with open(target_path, 'w', encoding='utf-8') as f:
                        nbformat.write(nb, f)
                    save_msg = f"Notebook saved to {_display_path(target_path, path)}"
                else:
                    save_msg = "Notebook not saved (save_output=False)"

                if execution_errors:
                    error_details = json.dumps(execution_errors, indent=2)
                    return f"Warning: Notebook executed with errors.\n{save_msg}\n\nErrors:\n{error_details}"
                else:
                    return f"Success: All {len(nb.cells)} cells executed successfully.\n{save_msg}"

            # --- OPERATION: VALIDATE ---
            elif op == "validate":
                if not target_path.exists():
                    return f"Error: Notebook not found at {_display_path(target_path, path)}"

                with open(target_path, 'r', encoding='utf-8') as f:
                    nb = nbformat.read(f, as_version=4)

                try:
                    nbformat.validate(nb)
                    return (f"Success: Notebook at {_display_path(target_path, path)} is valid.\n"
                            f"Format: nbformat {nb.nbformat}.{nb.nbformat_minor}\n"
                            f"Cells: {len(nb.cells)}\n"
                            f"Kernel: {nb.metadata.get('kernelspec', {}).get('name', 'unknown')}")
                except nbformat.ValidationError as e:
                    return f"Invalid: Notebook validation failed.\nError: {str(e)}"

            # --- OPERATION: CLEAR_OUTPUTS ---
            elif op == "clear_outputs":
                if not target_path.exists():
                    return f"Error: Notebook not found at {_display_path(target_path, path)}"

                with open(target_path, 'r', encoding='utf-8') as f:
                    nb = nbformat.read(f, as_version=4)

                cells_cleared = 0
                for cell in nb.cells:
                    if cell.cell_type == "code":
                        cell["outputs"] = []
                        cell["execution_count"] = None
                        cells_cleared += 1

                with open(target_path, 'w', encoding='utf-8') as f:
                    nbformat.write(nb, f)

                return f"Success: Cleared outputs from {cells_cleared} code cells in {_display_path(target_path, path)}"

            else:
                return (f"Error: Unknown operation '{operation}'. "
                        "Valid operations: create, read, add_cells, execute, validate, clear_outputs")

        except json.JSONDecodeError as e:
            return f"Error: Invalid JSON in notebook file - {str(e)}"
        except Exception as e:
            logger.error(f"Notebook operation error: {e}")
            return f"Error during {operation}: {str(e)}"

    yield FunctionInfo.from_fn(
        _notebook_operation,
        description=(
            "Jupyter Notebook manipulation tool for creating, reading, and managing .ipynb files. "
            "Operations: 'create' (new notebook with cells), 'read' (inspect contents), "
            "'add_cells' (append/insert cells), 'execute' (run all cells), "
            "'validate' (check format), 'clear_outputs' (remove cell outputs). "
            "Cells format: JSON array string like '[{\"cell_type\": \"markdown\", \"source\": \"# Title\"}, "
            "{\"cell_type\": \"code\", \"source\": \"print(1)\"}]'. "
            "The tool is also tolerant of Python-literal lists (single quotes) and JSON strings containing "
            "unescaped newlines."
        )
    )
