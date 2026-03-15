#!/usr/bin/env python3
"""
pzctl - CLI tool for PZ (Explanatory Note) Platform.

Commands:
    status      - Show project status
    validate    - Validate project data
    list        - List objects by class
    show        - Show object details
    classes     - List available classes
    graph       - Show graph statistics and cycles
    impact      - Impact analysis for an object
    deps        - Show dependencies of an object
    dot         - Export graph to Graphviz DOT format
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.loader import ProjectData
from core.validator import Validator
from core.graph import CalculationGraph, CycleType
from core.classes import CLASSES_REGISTRY, CLASS_FILE_NAMES


def cmd_status(args: argparse.Namespace) -> int:
    """Show project status."""
    project_path = args.project or Path.cwd()
    project = ProjectData(project_path)
    results = project.load_all()
    
    print(f"\n=== Project Status ===")
    print(f"Path: {project.project_path}")
    print(f"Classes path: {project.classes_path}")
    print()
    
    total = 0
    for class_name, result in results.items():
        loaded = result['loaded']
        errors = len(result['errors'])
        total += loaded
        if loaded > 0 or errors > 0:
            status = 'OK' if errors == 0 else 'ERRORS'
            print(f"  {class_name}: {loaded} objects [{status}]")
            for err in result['errors'][:3]:  # Show first 3 errors
                print(f"    - {err}")
    
    print(f"\nTotal objects: {total}")
    print(f"Classes path exists: {project.classes_path.exists()}")
    
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate project data."""
    project_path = args.project or Path.cwd()
    project = ProjectData(project_path)
    project.load_all()
    
    validator = Validator(project)
    result = validator.validate_all(fix=args.fix)
    
    print(f"\n=== Validation Result ===")
    print(f"Valid: {result.valid}")
    
    if result.errors:
        print(f"\nErrors ({len(result.errors)}):")
        for err in result.errors[:10]:
            print(f"  ✗ {err}")
    
    if result.warnings:
        print(f"\nWarnings ({len(result.warnings)}):")
        for warn in result.warnings[:10]:
            print(f"  ⚠ {warn}")
    
    if result.fixed:
        print(f"\nFixed ({len(result.fixed)}):")
        for fix in result.fixed[:10]:
            print(f"  ✓ {fix}")
    
    # Check unique IDs
    id_result = validator.validate_ids_unique()
    if not id_result.valid:
        print(f"\nID Errors:")
        for err in id_result.errors:
            print(f"  ✗ {err}")
    
    return 0 if result.valid else 1


def cmd_list(args: argparse.Namespace) -> int:
    """List objects by class."""
    project_path = args.project or Path.cwd()
    project = ProjectData(project_path)
    project.load_all()
    
    class_name = args.class_name
    
    if class_name:
        if class_name not in CLASSES_REGISTRY:
            print(f"Unknown class: {class_name}")
            print(f"Available: {', '.join(CLASSES_REGISTRY.keys())}")
            return 1
        
        objects = project.get_all(class_name)
        print(f"\n=== {class_name} ({len(objects)} objects) ===")
        for obj_id, obj in objects.items():
            name = getattr(obj, 'name', None) or getattr(obj, 'title', None) or ''
            if name:
                print(f"  {obj_id}: {name}")
            else:
                print(f"  {obj_id}")
    else:
        print("\n=== All Objects ===")
        stats = project.stats()
        for cn, count in stats.items():
            if count > 0:
                print(f"  {cn}: {count}")
    
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    """Show object details."""
    project_path = args.project or Path.cwd()
    project = ProjectData(project_path)
    project.load_all()
    
    obj_id = args.object_id
    obj = project.get(obj_id)
    
    if obj is None:
        print(f"Object not found: {obj_id}")
        return 1
    
    class_name = project.get_class_name(obj_id)
    print(f"\n=== {obj_id} ({class_name}) ===")
    
    data = obj.model_dump(mode='json')
    print(json.dumps(data, ensure_ascii=False, indent=2))
    
    return 0


def cmd_classes(args: argparse.Namespace) -> int:
    """List available classes."""
    print("\n=== Available Classes ===")
    for class_name, model_class in CLASSES_REGISTRY.items():
        file_name = CLASS_FILE_NAMES.get(class_name, f"{class_name}.json")
        print(f"  {class_name:25} -> {file_name}")
    
    return 0


def cmd_graph(args: argparse.Namespace) -> int:
    """Show graph statistics and cycles."""
    project_path = args.project or Path.cwd()
    project = ProjectData(project_path)
    project.load_all()
    
    graph = CalculationGraph(project)
    graph.build()
    
    stats = graph.stats()
    
    print(f"\n=== Graph Statistics ===")
    print(f"Total nodes: {stats.total_nodes}")
    print(f"Total edges: {stats.total_edges}")
    print(f"Logical cycles: {stats.cycles_count}")
    print(f"Unlinked nodes: {stats.unlinked_nodes}")
    
    print(f"\n=== Nodes by Type ===")
    for node_type, count in stats.nodes_by_type.items():
        print(f"  {node_type.value}: {count}")
    
    # Show cycles
    cycles = graph.find_cycles()
    if cycles:
        print(f"\n=== Cycles ({len(cycles)}) ===")
        for i, cycle in enumerate(cycles, 1):
            cycle_type_str = "Итерационный" if cycle.cycle_type == CycleType.ITERATIVE else "ОШИБКА"
            print(f"\n  Cycle {i} [{cycle_type_str}]:")
            print(f"    {cycle.description}")
    
    # Show topological order if no logical cycles
    if stats.cycles_count == 0:
        order = graph.topological_order()
        if order:
            print(f"\n=== Calculation Order ===")
            for i, node_id in enumerate(order[:20], 1):  # Show first 20
                node = graph.get_node(node_id)
                print(f"  {i}. {node_id} ({node.class_name})")
            if len(order) > 20:
                print(f"  ... and {len(order) - 20} more")
    
    return 0


def cmd_impact(args: argparse.Namespace) -> int:
    """Impact analysis for an object."""
    project_path = args.project or Path.cwd()
    project = ProjectData(project_path)
    project.load_all()
    
    obj_id = args.object_id
    
    graph = CalculationGraph(project)
    graph.build()
    
    result = graph.impact_analysis(obj_id)
    
    if result is None:
        print(f"Object not found: {obj_id}")
        return 1
    
    print(f"\n=== Impact Analysis: {obj_id} ===")
    
    node = graph.get_node(obj_id)
    if node:
        print(f"Class: {node.class_name}")
        print(f"Type: {node.node_type.value}")
    
    print(f"\nDirect dependents: {len(result.direct_deps)}")
    for dep_id in result.direct_deps[:10]:
        dep_node = graph.get_node(dep_id)
        print(f"  - {dep_id} ({dep_node.class_name if dep_node else '?'})")
    
    print(f"\nAll affected objects: {len(result.affected_ids)}")
    if args.verbose:
        for dep_id in result.affected_ids:
            dep_node = graph.get_node(dep_id)
            print(f"  - {dep_id} ({dep_node.class_name if dep_node else '?'})")
    
    return 0


def cmd_deps(args: argparse.Namespace) -> int:
    """Show dependencies of an object."""
    project_path = args.project or Path.cwd()
    project = ProjectData(project_path)
    project.load_all()
    
    obj_id = args.object_id
    
    graph = CalculationGraph(project)
    graph.build()
    
    deps = graph.dependencies_of(obj_id)
    
    if deps is None:
        print(f"Object not found: {obj_id}")
        return 1
    
    node = graph.get_node(obj_id)
    print(f"\n=== Dependencies: {obj_id} ===")
    if node:
        print(f"Class: {node.class_name}")
        print(f"Type: {node.node_type.value}")
    
    print(f"\nDirect dependencies: {len(node.outgoing) if node else 0}")
    if node:
        for dep_id in node.outgoing[:10]:
            dep_node = graph.get_node(dep_id)
            print(f"  - {dep_id} ({dep_node.class_name if dep_node else '?'})")
    
    print(f"\nAll dependencies: {len(deps)}")
    if args.verbose:
        for dep_id in deps:
            dep_node = graph.get_node(dep_id)
            print(f"  - {dep_id} ({dep_node.class_name if dep_node else '?'})")
    
    return 0


def cmd_dot(args: argparse.Namespace) -> int:
    """Export graph to Graphviz DOT format."""
    project_path = args.project or Path.cwd()
    project = ProjectData(project_path)
    project.load_all()
    
    graph = CalculationGraph(project)
    graph.build()
    
    title = args.title or f"Graph: {project.project_path.name}"
    dot_content = graph.export_dot(title)
    
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(dot_content, encoding='utf-8')
        print(f"DOT file written to: {output_path}")
    else:
        print(dot_content)
    
    return 0


def main(args: Optional[list[str]] = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog='pzctl',
        description='CLI tool for PZ (Explanatory Note) Platform'
    )
    parser.add_argument(
        '-p', '--project',
        type=Path,
        help='Project directory (default: current directory)'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # status command
    subparsers.add_parser('status', help='Show project status')
    
    # validate command
    validate_parser = subparsers.add_parser('validate', help='Validate project data')
    validate_parser.add_argument('--fix', action='store_true', help='Fix missing class_name')
    
    # list command
    list_parser = subparsers.add_parser('list', help='List objects by class')
    list_parser.add_argument('class_name', nargs='?', help='Class name to list')
    
    # show command
    show_parser = subparsers.add_parser('show', help='Show object details')
    show_parser.add_argument('object_id', help='Object ID to show')
    
    # classes command
    subparsers.add_parser('classes', help='List available classes')
    
    # graph command
    subparsers.add_parser('graph', help='Show graph statistics and cycles')
    
    # impact command
    impact_parser = subparsers.add_parser('impact', help='Impact analysis for an object')
    impact_parser.add_argument('object_id', help='Object ID to analyze')
    impact_parser.add_argument('-v', '--verbose', action='store_true', help='Show all affected objects')
    
    # deps command
    deps_parser = subparsers.add_parser('deps', help='Show dependencies of an object')
    deps_parser.add_argument('object_id', help='Object ID to show dependencies')
    deps_parser.add_argument('-v', '--verbose', action='store_true', help='Show all dependencies')
    
    # dot command
    dot_parser = subparsers.add_parser('dot', help='Export graph to Graphviz DOT format')
    dot_parser.add_argument('-o', '--output', help='Output file (default: stdout)')
    dot_parser.add_argument('-t', '--title', help='Graph title')
    
    parsed = parser.parse_args(args)
    
    if parsed.command is None:
        parser.print_help()
        return 0
    
    commands = {
        'status': cmd_status,
        'validate': cmd_validate,
        'list': cmd_list,
        'show': cmd_show,
        'classes': cmd_classes,
        'graph': cmd_graph,
        'impact': cmd_impact,
        'deps': cmd_deps,
        'dot': cmd_dot,
    }
    
    return commands[parsed.command](parsed)


if __name__ == '__main__':
    sys.exit(main())