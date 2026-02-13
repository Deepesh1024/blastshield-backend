"""
Call Graph Data Models — Graph structure for inter-function/inter-module relationships.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class CallType(str, Enum):
    """Type of call edge."""

    DIRECT = "direct"
    IMPORT = "import"
    METHOD = "method"
    CALLBACK = "callback"


class CallGraphNode(BaseModel):
    """A node in the call graph (function or module)."""

    id: str = Field(..., description="Unique node ID: 'module::function'")
    module: str
    function: str
    is_async: bool = False
    is_entry_point: bool = Field(
        default=False,
        description="True if this is an API handler / main / CLI entry",
    )
    reads_shared_state: list[str] = Field(default_factory=list)
    writes_shared_state: list[str] = Field(default_factory=list)
    line: int = 0


class CallGraphEdge(BaseModel):
    """An edge in the call graph (caller → callee)."""

    source: str = Field(..., description="Caller node ID")
    target: str = Field(..., description="Callee node ID")
    call_type: CallType = CallType.DIRECT
    async_boundary_crossing: bool = Field(
        default=False,
        description="True if edge crosses async/sync boundary",
    )
    line: int = Field(default=0, description="Line of the call site")


class CallGraph(BaseModel):
    """Complete call graph for a set of modules."""

    nodes: dict[str, CallGraphNode] = Field(default_factory=dict)
    edges: list[CallGraphEdge] = Field(default_factory=list)

    def get_neighbors(self, node_id: str) -> list[str]:
        """Get all direct callees of a node."""
        return [e.target for e in self.edges if e.source == node_id]

    def get_callers(self, node_id: str) -> list[str]:
        """Get all direct callers of a node."""
        return [e.source for e in self.edges if e.target == node_id]

    def get_blast_radius(self, node_id: str) -> int:
        """BFS depth from node through all reachable callees."""
        visited: set[str] = set()
        queue = [node_id]
        depth = 0
        while queue:
            next_queue: list[str] = []
            for nid in queue:
                if nid in visited:
                    continue
                visited.add(nid)
                next_queue.extend(self.get_neighbors(nid))
            queue = next_queue
            if queue:
                depth += 1
        return depth

    def get_max_depth(self) -> int:
        """Get the maximum blast radius across all nodes."""
        if not self.nodes:
            return 0
        return max(self.get_blast_radius(nid) for nid in self.nodes)

    def get_subgraph(self, node_ids: set[str]) -> "CallGraph":
        """Extract a subgraph containing only the specified nodes and their edges."""
        sub_nodes = {nid: n for nid, n in self.nodes.items() if nid in node_ids}
        sub_edges = [
            e
            for e in self.edges
            if e.source in node_ids and e.target in node_ids
        ]
        return CallGraph(nodes=sub_nodes, edges=sub_edges)

    def get_affected_subgraph(self, violation_node_ids: set[str], hops: int = 1) -> "CallGraph":
        """Get subgraph around violation nodes, expanding by N hops."""
        expanded: set[str] = set(violation_node_ids)
        frontier = set(violation_node_ids)
        for _ in range(hops):
            next_frontier: set[str] = set()
            for nid in frontier:
                next_frontier.update(self.get_neighbors(nid))
                next_frontier.update(self.get_callers(nid))
            expanded.update(next_frontier)
            frontier = next_frontier - expanded
        return self.get_subgraph(expanded)
