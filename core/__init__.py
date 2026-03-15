"""
Core library for PZ Platform orchestrator.
Contains data classes, loader, validator, and graph utilities.
"""

from .classes import (
    Metadata,
    RegulatoryFramework,
    InputData,
    ReferenceData,
    DocumentStructure,
    Method,
    Formula,
    Assumption,
    DesignDecision,
    IntermediateResult,
    FinalResult,
    ComparisonData,
    Guideline,
    Reference,
    MiscData,
    CLASSES_REGISTRY,
    CLASS_FILE_NAMES,
)

from .loader import ProjectData, load_project
from .validator import Validator, ValidationResult, validate_project
from .graph import (
    CalculationGraph,
    GraphNode,
    GraphStats,
    NodeType,
    CycleType,
    Cycle,
    ImpactResult,
)

__all__ = [
    # Classes
    "Metadata",
    "RegulatoryFramework", 
    "InputData",
    "ReferenceData",
    "DocumentStructure",
    "Method",
    "Formula",
    "Assumption",
    "DesignDecision",
    "IntermediateResult",
    "FinalResult",
    "ComparisonData",
    "Guideline",
    "Reference",
    "MiscData",
    "CLASSES_REGISTRY",
    "CLASS_FILE_NAMES",
    # Loader
    "ProjectData",
    "load_project",
    # Validator
    "Validator",
    "ValidationResult",
    "validate_project",
    # Graph
    "CalculationGraph",
    "GraphNode",
    "GraphStats",
    "NodeType",
    "CycleType",
    "Cycle",
    "ImpactResult",
]
