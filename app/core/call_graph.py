"""
Call Graph Builder — Constructs inter-function/inter-module call graphs.

Takes a dict of ModuleAST objects and produces a CallGraph with nodes (functions)
and edges (calls/imports), tracking async boundary crossings and shared state access.
"""

from __future__ import annotations

from app.models.ast_models import ModuleAST
from app.models.graph_models import CallGraph, CallGraphEdge, CallGraphNode, CallType


def _make_node_id(module: str, function: str) -> str:
    """Create a unique node ID."""
    return f"{module}::{function}"


def build_call_graph(modules: dict[str, ModuleAST]) -> CallGraph:
    """
    Build a call graph from parsed modules.

    Args:
        modules: Dict mapping file_path -> ModuleAST.

    Returns:
        CallGraph with nodes and edges.
    """
    graph = CallGraph()

    # --- Phase 1: Create nodes ---
    # Map short function names to their full node IDs for cross-module resolution
    name_to_nodes: dict[str, list[str]] = {}

    for file_path, module_ast in modules.items():
        module_name = file_path

        # Top-level functions
        for func in module_ast.functions:
            node_id = _make_node_id(module_name, func.name)
            is_entry = _is_entry_point(func.name, func.decorators)

            graph.nodes[node_id] = CallGraphNode(
                id=node_id,
                module=module_name,
                function=func.name,
                is_async=func.is_async,
                is_entry_point=is_entry,
                reads_shared_state=func.reads_globals,
                writes_shared_state=func.writes_globals,
                line=func.line,
            )
            name_to_nodes.setdefault(func.name, []).append(node_id)

        # Class methods
        for cls in module_ast.classes:
            for method in cls.methods:
                qualified = f"{cls.name}.{method.name}"
                node_id = _make_node_id(module_name, qualified)

                graph.nodes[node_id] = CallGraphNode(
                    id=node_id,
                    module=module_name,
                    function=qualified,
                    is_async=method.is_async,
                    is_entry_point=_is_entry_point(method.name, method.decorators),
                    reads_shared_state=method.reads_globals,
                    writes_shared_state=method.writes_globals,
                    line=method.line,
                )
                name_to_nodes.setdefault(qualified, []).append(node_id)
                name_to_nodes.setdefault(method.name, []).append(node_id)

    # --- Phase 2: Create edges ---
    for file_path, module_ast in modules.items():
        module_name = file_path

        # Build import alias map for this module
        import_map: dict[str, str] = {}
        for imp in module_ast.imports:
            if imp.is_from_import:
                for name in imp.names:
                    import_map[name] = imp.module
            else:
                if imp.alias:
                    import_map[imp.alias] = imp.module
                else:
                    import_map[imp.module] = imp.module

        # Process function calls
        all_funcs = list(module_ast.functions)
        for cls in module_ast.classes:
            all_funcs.extend(cls.methods)

        for func in all_funcs:
            caller_name = func.qualified_name or func.name
            caller_id = _make_node_id(module_name, caller_name)

            if caller_id not in graph.nodes:
                continue

            caller_node = graph.nodes[caller_id]

            for call_name in func.calls:
                callee_ids = _resolve_callee(
                    call_name, module_name, name_to_nodes, import_map, modules
                )
                for callee_id in callee_ids:
                    if callee_id in graph.nodes:
                        callee_node = graph.nodes[callee_id]
                        async_crossing = caller_node.is_async != callee_node.is_async

                        graph.edges.append(
                            CallGraphEdge(
                                source=caller_id,
                                target=callee_id,
                                call_type=CallType.DIRECT,
                                async_boundary_crossing=async_crossing,
                            )
                        )

    # --- Phase 3: Import edges ---
    for file_path, module_ast in modules.items():
        module_name = file_path
        for imp in module_ast.imports:
            if imp.is_from_import:
                # Find target module
                for target_path, target_ast in modules.items():
                    if target_path == file_path:
                        continue
                    if _module_matches(imp.module, target_path):
                        for name in imp.names:
                            source_id = _make_node_id(module_name, name)
                            target_id = _make_node_id(target_path, name)
                            if target_id in graph.nodes:
                                graph.edges.append(
                                    CallGraphEdge(
                                        source=source_id if source_id in graph.nodes else _make_node_id(module_name, "__module__"),
                                        target=target_id,
                                        call_type=CallType.IMPORT,
                                        line=imp.line,
                                    )
                                )

    return graph


def _is_entry_point(func_name: str, decorators: list[str]) -> bool:
    """Detect if a function is an API entry point."""
    entry_decorators = {
        "app.route", "app.get", "app.post", "app.put", "app.delete", "app.patch",
        "router.get", "router.post", "router.put", "router.delete", "router.patch",
        "route", "get", "post", "put", "delete",
    }
    if func_name in ("main", "__main__"):
        return True
    return any(d.lower() in entry_decorators for d in decorators)


def _resolve_callee(
    call_name: str,
    current_module: str,
    name_to_nodes: dict[str, list[str]],
    import_map: dict[str, str],
    modules: dict[str, ModuleAST],
) -> list[str]:
    """Resolve a call name to potential callee node IDs."""
    # Direct match in same module
    node_id = _make_node_id(current_module, call_name)
    if call_name in name_to_nodes:
        # Prefer same-module match
        same_module = [nid for nid in name_to_nodes[call_name] if nid.startswith(current_module)]
        if same_module:
            return same_module
        return name_to_nodes[call_name][:1]  # First match from other modules

    # Dotted call: module.func or class.method
    if "." in call_name:
        parts = call_name.split(".")
        # Try resolving first part as import
        if parts[0] in import_map:
            imported_module = import_map[parts[0]]
            for path in modules:
                if _module_matches(imported_module, path):
                    target_id = _make_node_id(path, parts[-1])
                    return [target_id]

        # Try as class.method
        if call_name in name_to_nodes:
            return name_to_nodes[call_name][:1]

    return []


def _module_matches(module_name: str, file_path: str) -> bool:
    """Check if a module name matches a file path."""
    # Simple heuristic: check if module name parts appear in file path
    normalized = file_path.replace("/", ".").replace("\\", ".").replace(".py", "")
    return module_name in normalized or normalized.endswith(module_name)
