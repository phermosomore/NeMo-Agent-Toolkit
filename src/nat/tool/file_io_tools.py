# SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import logging
import os
from pathlib import Path
from typing import Optional

from pydantic import Field

from nat.builder.builder import Builder
from nat.builder.function_info import FunctionInfo
from nat.cli.register_workflow import register_function
from nat.data_models.function import FunctionBaseConfig

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------------
# 1. Configuration Class
#    The 'name' defined here becomes the '_type' you use in config.yaml
# -------------------------------------------------------------------------
class FileIOWorkflowConfig(FunctionBaseConfig, name="file_io"):
    """Configuration for the File I/O workflow."""
    root_dir: str = Field(
        description="Root directory for file operations. Acts as a safety sandbox.", 
        default="/workspace"
    )

# -------------------------------------------------------------------------
# 2. Function Implementation
# -------------------------------------------------------------------------
@register_function(config_type=FileIOWorkflowConfig)
async def file_io_function(config: FileIOWorkflowConfig, builder: Builder):
    """
    A robust File I/O tool allowing the Agent to Read, Write, List, and Mkdir.
    """

    # Ensure the root directory exists
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

    # This inner function is what the LLM actually calls
    async def _execute_io(operation: str, path: str, content: str = "") -> str:
        """
        Perform file system operations.
        
        Args:
            operation: The action to perform. Valid options: 'read', 'write', 'list', 'mkdir'.
            path: The file or directory path (absolute or relative to root).
            content: The text content to write (Required only for 'write' operation).
        """
        logger.info(f"FileIO Request - Op: {operation}, Path: {path}")

        try:
            # Resolve the path safely
            input_path = Path(path)

            # Users/agents may provide sandbox paths like "/workspace/foo.txt".
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
                return (
                    f"Error: Invalid path '{path}'. Use a relative path under root_dir "
                    f"('{config.root_dir}'), e.g. 'generated_files/output.txt'."
                )
            
            # Normalize operation string
            op = operation.lower().strip()

            # --- OPERATION: READ ---
            if op == "read":
                if not target_path.exists():
                    return f"Error: File not found at {_display_path(target_path, path)}"
                if target_path.is_dir():
                    return f"Error: {_display_path(target_path, path)} is a directory. Use 'list' to view contents."
                
                # Return file content
                return target_path.read_text(encoding='utf-8')

            # --- OPERATION: WRITE ---
            elif op == "write":
                # Automatically create parent directories if missing
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_text(content, encoding='utf-8')
                return f"Success: File successfully written to {_display_path(target_path, path)}"

            # --- OPERATION: LIST ---
            elif op == "list":
                if not target_path.exists():
                    return f"Error: Path not found at {_display_path(target_path, path)}"
                if not target_path.is_dir():
                    return f"Error: {_display_path(target_path, path)} is a file, not a directory."
                
                items = os.listdir(target_path)
                return f"Contents of {_display_path(target_path, path)}:\n" + "\n".join(items)

            # --- OPERATION: MKDIR ---
            elif op == "mkdir":
                target_path.mkdir(parents=True, exist_ok=True)
                return f"Success: Directory created at {_display_path(target_path, path)}"

            else:
                return f"Error: Unknown operation '{operation}'. Supported operations: read, write, list, mkdir."

        except Exception as e:
            logger.error(f"FileIO Error: {e}")
            return f"System Error executing {operation}: {str(e)}"

    # Yield the function info so the Agent can discover it
    yield FunctionInfo.from_fn(
        _execute_io,
        description=(
            "General purpose File I/O tool. Use this to READ files, WRITE text/code to files, "
            "LIST directory contents, or create directories (MKDIR). "
            "Arguments: 'operation' (read/write/list/mkdir), 'path' (filepath), and 'content' (only for write)."
        )
    )