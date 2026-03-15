"""
Calculation graph for PZ data classes.
Provides dependency tracking, cycle detection, impact analysis, and topological sorting.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from collections import defaultdict

from .loader import ProjectData
from .classes import BaseModel, LinkReference


class NodeType(str, Enum):
    """Types of nodes in calculation graph."""
    INPUT = "input"           # Input data (class 3)
    REFERENCE = "reference"   # Reference data (class 4)
    METHOD = "method"         # Calculation method (class 6)
    FORMULA = "formula"       # Formula (class 7)
    INTERMEDIATE = "intermediate"  # Intermediate result (class 10)
    FINAL = "final"           # Final result (class 11)
    DECISION = "decision"     # Design decision (class 9)
    OTHER = "other"           # Other classes


class CycleType(str, Enum):
    """Types of cycles in graph."""
    ITERATIVE = "iterative"   # Intentional iteration (acceptable)
    LOGICAL = "logical"       # Logical error (unacceptable)


@dataclass
class GraphNode:
    """Node in calculation graph."""
    id: str
    class_name: str
    node_type: NodeType
    obj: BaseModel
    outgoing: list[str] = field(default_factory=list)  # IDs this node points to
    incoming: list[str] = field(default_factory=list)  # IDs that point to this node


@dataclass
class Cycle:
    """Detected cycle in graph."""
    path: list[str]           # List of node IDs in cycle
    cycle_type: CycleType     # Type of cycle
    description: str          # Human-readable description


@dataclass
class ImpactResult:
    """Result of impact analysis."""
    source_id: str
    affected_ids: list[str]   # All nodes affected by changes to source
    direct_deps: list[str]    # Direct dependencies
    impact_tree: dict         # Nested tree of dependencies


@dataclass
class GraphStats:
    """Statistics about the graph."""
    total_nodes: int
    total_edges: int
    nodes_by_type: dict[NodeType, int]
    cycles_count: int
    unlinked_nodes: int


class CalculationGraph:
    """
    Dependency graph for PZ calculation objects.
    
    Provides:
    - Graph construction from ProjectData
    - Cycle detection
    - Impact analysis (tracing dependencies)
    - Topological sorting for calculation order
    - Export to Graphviz DOT and Markdown
    """
    
    # Mapping from class names to node types
    CLASS_TO_TYPE: dict[str, NodeType] = {
        "input_data": NodeType.INPUT,
        "reference_data": NodeType.REFERENCE,
        "methods": NodeType.METHOD,
        "formulas": NodeType.FORMULA,
        "intermediate_results": NodeType.INTERMEDIATE,
        "final_results": NodeType.FINAL,
        "design_decisions": NodeType.DECISION,
    }
    
    def __init__(self, project_data: ProjectData):
        """
        Initialize graph with project data.
        
        Args:
            project_data: ProjectData instance with loaded objects
        """
        self.project = project_data
        self._nodes: dict[str, GraphNode] = {}
        self._built = False
        self._cycles: list[Cycle] = []
    
    def build(self) -> None:
        """
        Build the dependency graph from project data.
        
        Creates nodes for all objects and edges based on:
        - links[].id
        - inputs[].id
        - outputs[].id
        - variables[].id
        - method_ref
        - used_in[]
        - based_on[].id
        - formulas[]
        - assumptions[]
        - submethods[]
        """
        self._nodes.clear()
        self._cycles.clear()
        
        # Create nodes for all objects
        for obj_id, (class_name, obj) in self.project._index.items():
            node_type = self.CLASS_TO_TYPE.get(class_name, NodeType.OTHER)
            self._nodes[obj_id] = GraphNode(
                id=obj_id,
                class_name=class_name,
                node_type=node_type,
                obj=obj,
            )
        
        # Build edges from link fields
        for obj_id, (class_name, obj) in self.project._index.items():
            target_ids = self._extract_link_ids(obj)
            
            for target_id in target_ids:
                # Check if target exists
                if target_id in self._nodes:
                    self._nodes[obj_id].outgoing.append(target_id)
                    self._nodes[target_id].incoming.append(obj_id)
        
        self._built = True
    
    def _extract_link_ids(self, obj: BaseModel) -> list[str]:
        """
        Extract all link IDs from an object.
        
        Handles various link field formats:
        - links: list[LinkReference]
        - inputs/outputs: list[LinkReference]
        - variables: list[FormulaVariable]
        - method_ref: str
        - used_in: list[str]
        - based_on: list[LinkReference]
        - formulas: list[str]
        - assumptions: list[str]
        - submethods: list[str]
        """
        ids = []
        
        # Get object dict
        obj_dict = obj.model_dump()
        
        # LinkReference lists
        for field_name in ['links', 'inputs', 'outputs', 'based_on', 'content_refs', 'related_objects']:
            if field_name in obj_dict:
                for link in obj_dict[field_name]:
                    if isinstance(link, dict) and 'id' in link:
                        ids.append(link['id'])
                    elif isinstance(link, str):
                        ids.append(link)
        
        # String lists
        for field_name in ['formulas', 'assumptions', 'submethods', 'used_in']:
            if field_name in obj_dict:
                for item in obj_dict[field_name]:
                    if isinstance(item, str):
                        ids.append(item)
        
        # Formula variables
        if 'variables' in obj_dict:
            for var in obj_dict['variables']:
                if isinstance(var, dict) and 'id' in var:
                    ids.append(var['id'])
        
        # Single string references
        for field_name in ['method_ref', 'source_ref']:
            if field_name in obj_dict:
                val = obj_dict[field_name]
                if isinstance(val, str) and val:
                    ids.append(val)
        
        return ids
    
    def find_cycles(self) -> list[Cycle]:
        """
        Detect cycles in the dependency graph.
        
        Uses DFS with color marking:
        - white: unvisited
        - gray: in progress
        - black: completed
        
        Returns:
            List of detected Cycle objects
        """
        if not self._built:
            self.build()
        
        self._cycles.clear()
        
        # Colors: 0=white, 1=gray, 2=black
        colors: dict[str, int] = {node_id: 0 for node_id in self._nodes}
        
        def dfs(node_id: str, path: list[str]) -> Optional[list[str]]:
            colors[node_id] = 1  # Gray
            path.append(node_id)
            
            for neighbor_id in self._nodes[node_id].outgoing:
                if colors[neighbor_id] == 1:  # Gray - cycle found
                    # Extract cycle
                    cycle_start = path.index(neighbor_id)
                    return path[cycle_start:]
                elif colors[neighbor_id] == 0:  # White
                    result = dfs(neighbor_id, path)
                    if result:
                        return result
            
            path.pop()
            colors[node_id] = 2  # Black
            return None
        
        # Check all nodes
        for node_id in self._nodes:
            if colors[node_id] == 0:
                cycle_path = dfs(node_id, [])
                if cycle_path:
                    # Determine cycle type
                    cycle_type = self._classify_cycle(cycle_path)
                    self._cycles.append(Cycle(
                        path=cycle_path,
                        cycle_type=cycle_type,
                        description=self._describe_cycle(cycle_path, cycle_type)
                    ))
        
        return self._cycles
    
    def _classify_cycle(self, cycle_path: list[str]) -> CycleType:
        """
        Classify a cycle as iterative or logical error.
        
        Iterative cycles involve methods/formulas that are designed
        for iterative calculation (e.g., convergence loops).
        """
        for node_id in cycle_path:
            node = self._nodes.get(node_id)
            if node and node.node_type in (NodeType.METHOD, NodeType.FORMULA):
                # Methods and formulas may be iterative
                return CycleType.ITERATIVE
        return CycleType.LOGICAL
    
    def _describe_cycle(self, cycle_path: list[str], cycle_type: CycleType) -> str:
        """Generate human-readable description of a cycle."""
        cycle_str = " → ".join(cycle_path)
        if cycle_type == CycleType.ITERATIVE:
            return f"Итерационный цикл: {cycle_str}"
        return f"Логическая ошибка (цикл): {cycle_str}"
    
    def impact_analysis(self, obj_id: str) -> Optional[ImpactResult]:
        """
        Perform impact analysis for an object.
        
        Finds all objects that depend on the given object (directly or indirectly).
        
        Args:
            obj_id: ID of the source object
            
        Returns:
            ImpactResult with affected objects, or None if object not found
        """
        if not self._built:
            self.build()
        
        if obj_id not in self._nodes:
            return None
        
        # BFS to find all dependents (follow incoming edges)
        visited = set()
        queue = [obj_id]
        direct_deps = []
        
        while queue:
            current = queue.pop(0)
            
            for dependent_id in self._nodes[current].incoming:
                if dependent_id not in visited:
                    visited.add(dependent_id)
                    if current == obj_id:
                        direct_deps.append(dependent_id)
                    queue.append(dependent_id)
        
        # Build impact tree
        impact_tree = self._build_impact_tree(obj_id)
        
        return ImpactResult(
            source_id=obj_id,
            affected_ids=list(visited),
            direct_deps=direct_deps,
            impact_tree=impact_tree
        )
    
    def _build_impact_tree(self, obj_id: str, visited: Optional[set] = None) -> dict:
        """Build nested tree of dependencies."""
        if visited is None:
            visited = set()
        
        if obj_id in visited:
            return {}
        
        visited.add(obj_id)
        
        tree = {}
        for dependent_id in self._nodes[obj_id].incoming:
            tree[dependent_id] = self._build_impact_tree(dependent_id, visited)
        
        return tree
    
    def dependencies_of(self, obj_id: str) -> Optional[list[str]]:
        """
        Get all objects that this object depends on (predecessors).
        
        Args:
            obj_id: ID of the object
            
        Returns:
            List of predecessor IDs, or None if object not found
        """
        if not self._built:
            self.build()
        
        if obj_id not in self._nodes:
            return None
        
        # BFS following outgoing edges (reverse of impact analysis)
        visited = set()
        queue = [obj_id]
        
        while queue:
            current = queue.pop(0)
            
            for dep_id in self._nodes[current].outgoing:
                if dep_id not in visited:
                    visited.add(dep_id)
                    queue.append(dep_id)
        
        return list(visited)
    
    def topological_order(self) -> Optional[list[str]]:
        """
        Compute topological ordering of nodes.
        
        Objects with no dependencies come first.
        Useful for determining calculation order.
        
        Returns:
            List of node IDs in topological order, or None if cycles exist
        """
        if not self._built:
            self.build()
        
        # Check for cycles first
        if not self._cycles:
            self.find_cycles()
        
        # Cannot do topological sort with logical cycles
        for cycle in self._cycles:
            if cycle.cycle_type == CycleType.LOGICAL:
                return None
        
        # Kahn's algorithm
        in_degree = {node_id: len(node.incoming) for node_id, node in self._nodes.items()}
        queue = [node_id for node_id, degree in in_degree.items() if degree == 0]
        result = []
        
        while queue:
            node_id = queue.pop(0)
            result.append(node_id)
            
            for dependent_id in self._nodes[node_id].incoming:
                in_degree[dependent_id] -= 1
                if in_degree[dependent_id] == 0:
                    queue.append(dependent_id)
        
        return result if len(result) == len(self._nodes) else None
    
    def stats(self) -> GraphStats:
        """
        Get statistics about the graph.
        
        Returns:
            GraphStats with counts and metrics
        """
        if not self._built:
            self.build()
        
        # Count edges
        total_edges = sum(len(node.outgoing) for node in self._nodes.values())
        
        # Count by type
        nodes_by_type: dict[NodeType, int] = defaultdict(int)
        for node in self._nodes.values():
            nodes_by_type[node.node_type] += 1
        
        # Count unlinked nodes
        unlinked = sum(
            1 for node in self._nodes.values()
            if not node.incoming and not node.outgoing
        )
        
        # Detect cycles if not done
        if not self._cycles:
            self.find_cycles()
        
        return GraphStats(
            total_nodes=len(self._nodes),
            total_edges=total_edges,
            nodes_by_type=dict(nodes_by_type),
            cycles_count=len([c for c in self._cycles if c.cycle_type == CycleType.LOGICAL]),
            unlinked_nodes=unlinked
        )
    
    def export_dot(self, title: str = "Calculation Graph") -> str:
        """
        Export graph to Graphviz DOT format.
        
        Args:
            title: Graph title
            
        Returns:
            DOT format string
        """
        if not self._built:
            self.build()
        
        lines = [
            'digraph "CalculationGraph" {',
            f'    label="{title}";',
            '    labelloc="t";',
            '    rankdir="LR";',
            '',
            '    // Node styles',
            '    node [shape=box, style=filled];',
            '',
        ]
        
        # Node type colors
        type_colors = {
            NodeType.INPUT: "#90EE90",      # Light green
            NodeType.REFERENCE: "#87CEEB",  # Light blue
            NodeType.METHOD: "#FFD700",     # Gold
            NodeType.FORMULA: "#FFA500",    # Orange
            NodeType.INTERMEDIATE: "#DDA0DD",  # Plum
            NodeType.FINAL: "#FF6347",      # Tomato
            NodeType.DECISION: "#98FB98",   # Pale green
            NodeType.OTHER: "#D3D3D3",      # Light gray
        }
        
        # Define nodes
        lines.append('    // Nodes')
        for node_id, node in self._nodes.items():
            color = type_colors.get(node.node_type, "#D3D3D3")
            label = f"{node_id}\\n({node.class_name})"
            lines.append(f'    "{node_id}" [label="{label}", fillcolor="{color}"];')
        
        lines.append('')
        lines.append('    // Edges')
        
        # Define edges
        for node_id, node in self._nodes.items():
            for target_id in node.outgoing:
                lines.append(f'    "{node_id}" -> "{target_id}";')
        
        lines.append('}')
        
        return '\n'.join(lines)
    
    def to_markdown(self) -> str:
        """
        Generate Markdown report of the graph.
        
        Returns:
            Markdown formatted string
        """
        if not self._built:
            self.build()
        
        stats = self.stats()
        
        lines = [
            "# Граф расчётов",
            "",
            "## Статистика",
            "",
            f"- **Всего узлов:** {stats.total_nodes}",
            f"- **Всего связей:** {stats.total_edges}",
            f"- **Циклов (ошибок):** {stats.cycles_count}",
            f"- **Изолированных узлов:** {stats.unlinked_nodes}",
            "",
            "### Узлы по типам",
            "",
        ]
        
        for node_type, count in stats.nodes_by_type.items():
            lines.append(f"- {node_type.value}: {count}")
        
        # Cycles
        if self._cycles:
            lines.extend([
                "",
                "## Обнаруженные циклы",
                "",
            ])
            for i, cycle in enumerate(self._cycles, 1):
                lines.append(f"### Цикл {i}: {cycle.cycle_type.value}")
                lines.append("")
                lines.append(f"**Описание:** {cycle.description}")
                lines.append("")
                lines.append("**Путь:**")
                lines.append("```")
                lines.append(" → ".join(cycle.path))
                lines.append("```")
                lines.append("")
        
        # Topological order
        order = self.topological_order()
        if order:
            lines.extend([
                "",
                "## Порядок вычислений (топологический)",
                "",
            ])
            for i, node_id in enumerate(order, 1):
                node = self._nodes[node_id]
                lines.append(f"{i}. `{node_id}` ({node.class_name})")
        
        return '\n'.join(lines)
    
    def get_node(self, obj_id: str) -> Optional[GraphNode]:
        """
        Get graph node by object ID.
        
        Args:
            obj_id: Object identifier
            
        Returns:
            GraphNode or None if not found
        """
        return self._nodes.get(obj_id)
    
    @property
    def nodes(self) -> dict[str, GraphNode]:
        """Get all nodes in the graph."""
        return self._nodes
    
    @property
    def cycles(self) -> list[Cycle]:
        """Get detected cycles."""
        return self._cycles