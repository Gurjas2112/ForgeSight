"""
Train/serve PARITY: re-exports the runtime context-block serializer so SFT samples are built with
byte-identical formatting to inference (sft-dataset-spec.md §4). Single source of truth =
backend/agent/prompt_builder.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.agent.prompt_builder import (  # noqa: E402,F401
    build_context, citations_block, equipment_header,
)

__all__ = ["build_context", "citations_block", "equipment_header"]
