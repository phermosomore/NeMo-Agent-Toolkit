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
            target_path = Path(path)
            if not target_path.is_absolute():
                target_path = root_path / target_path
            
            # Normalize operation string
            op = operation.lower().strip()

            # --- OPERATION: READ ---
            if op == "read":
                if not target_path.exists():
                    return f"Error: File not found at {target_path}"
                if target_path.is_dir():
                    return f"Error: {target_path} is a directory. Use 'list' to view contents."
                
                # Return file content
                return target_path.read_text(encoding='utf-8')

            # --- OPERATION: WRITE ---
            elif op == "write":
                # Automatically create parent directories if missing
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_text(content, encoding='utf-8')
                return f"Success: File successfully written to {target_path}"

            # --- OPERATION: LIST ---
            elif op == "list":
                if not target_path.exists():
                    return f"Error: Path not found at {target_path}"
                if not target_path.is_dir():
                    return f"Error: {target_path} is a file, not a directory."
                
                items = os.listdir(target_path)
                return f"Contents of {target_path}:\n" + "\n".join(items)

            # --- OPERATION: MKDIR ---
            elif op == "mkdir":
                target_path.mkdir(parents=True, exist_ok=True)
                return f"Success: Directory created at {target_path}"

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