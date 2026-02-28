"""
BlastShield — Infinite loop detection rule.

Walks the tree-sitter AST to find:
  1. `while True` without break / return / raise in body
  2. `for` over known infinite iterators (itertools.count, itertools.repeat, iter(int,1))
"""

from __future__ import annotations

from tree_sitter import Node, Tree


# itertools calls that produce infinite iterators
_INFINITE_ITERATORS = {"count", "repeat"}


def _node_text(node: Node, source: bytes) -> str:
    """Extract source text for a node."""
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _has_exit_statement(node: Node) -> bool:
    """Check whether a node's subtree contains break / return / raise."""
    if node.type in ("break_statement", "return_statement", "raise_statement"):
        return True
    for child in node.children:
        if _has_exit_statement(child):
            return True
    return False


def _is_true_literal(node: Node, source: bytes) -> bool:
    """Check if a node is the boolean literal True."""
    return node.type == "true" or _node_text(node, source) == "True"


def _is_infinite_iterator_call(node: Node, source: bytes) -> bool:
    """Check if a node is a call to a known infinite iterator."""
    if node.type != "call":
        return False
    func = node.child_by_field_name("function")
    if func is None:
        return False
    text = _node_text(func, source)
    # itertools.count() / itertools.repeat()
    if "." in text:
        parts = text.rsplit(".", 1)
        if parts[0] in ("itertools",) and parts[1] in _INFINITE_ITERATORS:
            return True
    # bare count() / repeat() after `from itertools import count`
    if text in _INFINITE_ITERATORS:
        return True
    # iter(int, 1) sentinel form
    if text == "iter" and node.child_by_field_name("arguments"):
        args = node.child_by_field_name("arguments")
        # iter(callable, sentinel) has 2 args → infinite
        arg_nodes = [c for c in args.children if c.type not in ("(", ")", ",")]
        if len(arg_nodes) == 2:
            return True
    return False


def detect_infinite_loops(tree: Tree, source: bytes) -> list[dict]:
    """Detect potential infinite loops in a parsed Python AST.

    Returns a list of dicts with keys: line_start, line_end, evidence.
    """
    risks: list[dict] = []

    def _walk(node: Node) -> None:
        # --- while True without exit ---
        if node.type == "while_statement":
            condition = node.child_by_field_name("condition")
            body = node.child_by_field_name("body")
            if condition and _is_true_literal(condition, source):
                if body and not _has_exit_statement(body):
                    risks.append({
                        "line_start": node.start_point[0] + 1,
                        "line_end": node.end_point[0] + 1,
                        "evidence": (
                            "`while True` loop without break/return/raise — "
                            "will run indefinitely and exhaust CPU"
                        ),
                    })

        # --- for over infinite iterator ---
        if node.type == "for_statement":
            iter_node = node.child_by_field_name("right")
            body = node.child_by_field_name("body")
            if iter_node and _is_infinite_iterator_call(iter_node, source):
                if body and not _has_exit_statement(body):
                    risks.append({
                        "line_start": node.start_point[0] + 1,
                        "line_end": node.end_point[0] + 1,
                        "evidence": (
                            f"`for` loop over infinite iterator "
                            f"`{_node_text(iter_node, source)}` without break — "
                            "will never terminate"
                        ),
                    })

        for child in node.children:
            _walk(child)

    _walk(tree.root_node)
    return risks
