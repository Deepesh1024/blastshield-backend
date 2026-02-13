"""
Tests for Call Graph Builder — verify graph construction and blast radius.
"""

from app.core.ast_parser import parse_python
from app.core.call_graph import build_call_graph


def test_builds_graph_nodes(sample_python_code):
    module_ast = parse_python(sample_python_code, "test.py")
    graph = build_call_graph({"test.py": module_ast})
    assert len(graph.nodes) > 0
    node_funcs = {n.function for n in graph.nodes.values()}
    assert "process_file" in node_funcs
    assert "execute_code" in node_funcs
    assert "fetch_data" in node_funcs


def test_blast_radius_computed(sample_python_code):
    module_ast = parse_python(sample_python_code, "test.py")
    graph = build_call_graph({"test.py": module_ast})
    for node_id in graph.nodes:
        radius = graph.get_blast_radius(node_id)
        assert radius >= 0


def test_subgraph_extraction(sample_python_code):
    module_ast = parse_python(sample_python_code, "test.py")
    graph = build_call_graph({"test.py": module_ast})
    if graph.nodes:
        first_id = next(iter(graph.nodes))
        subgraph = graph.get_subgraph({first_id})
        assert len(subgraph.nodes) == 1


def test_async_detection(sample_python_code):
    module_ast = parse_python(sample_python_code, "test.py")
    graph = build_call_graph({"test.py": module_ast})
    async_nodes = [n for n in graph.nodes.values() if n.is_async]
    assert len(async_nodes) > 0


def test_multimodule_graph():
    """Test graph across two modules."""
    mod_a = parse_python('''
def helper():
    return 42

def main():
    return helper()
''', "a.py")

    mod_b = parse_python('''
from a import helper

def process():
    return helper()
''', "b.py")

    graph = build_call_graph({"a.py": mod_a, "b.py": mod_b})
    assert len(graph.nodes) >= 3  # helper, main, process
