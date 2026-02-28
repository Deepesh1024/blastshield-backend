"""
BlastShield — Python source parser using tree-sitter.
"""

from __future__ import annotations

import tree_sitter_python as tspython
from tree_sitter import Language, Parser


PY_LANGUAGE = Language(tspython.language())


class PythonParser:
    """Thin wrapper around tree-sitter for Python source code."""

    def __init__(self) -> None:
        self._parser = Parser(PY_LANGUAGE)

    def parse(self, code: str) -> tuple:
        """Parse Python source and return (tree, source_bytes).

        Raises ValueError if the code cannot be parsed.
        """
        source_bytes = code.encode("utf-8")
        tree = self._parser.parse(source_bytes)
        if tree.root_node.has_error:
            raise ValueError("Failed to parse Python source code")
        return tree, source_bytes
