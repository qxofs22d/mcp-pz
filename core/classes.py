"""
Pydantic schemas for 15 data classes of PZ (Explanatory Note) Platform.
Based on docs/specs/classes.md specification.
"""

from typing import Any, Optional
from pydantic import BaseModel, Field
from datetime import date
from enum import Enum


# ============================================================================
# Base Models and Enums
# ============================================================================

class LinkReference(BaseModel):
    """Reference to another object with type of relationship."""
    id: str = Field(..., description="Target object ID")
    type: str = Field(..., description="Type of relationship (uses, produces, justifies, etc.)")
    class_name: Optional[str] = Field(None, description="Target class name (auto-filled by validator)")


class SourceStatus(str, Enum):
    """Status of source type for input data."""
    SURVEY = "survey"  # Изыскания
    SPECIFICATION = "specification"  # ТУ
    EXTERNAL_CALC = "external_calculation"  # Внешний расчёт
    TASK = "task"  # ТЗ
    OTHER = "other"


class DocumentStatus(str, Enum):
    """Status of document."""
    DRAFT = "draft"
    PROJECT = "project"
    APPROVED = "approved"
    SUPERSEDED = "superseded"


# ============================================================================
# Class 1: Metadata
# ============================================================================

class Metadata(BaseModel):
    """
    Document metadata - 'passport' of the parametric model.
    File: metadata.json
    """
    id: str = Field(..., description="Unique identifier (e.g., 'metadata_001')")
    project_name: str = Field(..., description="Project name")
    construction_type: Optional[str] = Field(None, description="Construction type (new, reconstruction, etc.)")
    stage: Optional[str] = Field(None, description="Stage (П, РД)")
    project_code: Optional[str] = Field(None, description="Project code")
    section_name: Optional[str] = Field(None, description="Section name")
    developer: Optional[str] = Field(None, description="Developer organization")
    issue_date: Optional[date] = Field(None, description="Issue date")
    version: Optional[str] = Field(None, description="Document version")
    status: Optional[DocumentStatus] = Field(None, description="Document status")
    authors: list[str] = Field(default_factory=list, description="List of authors")
    reviewers: list[str] = Field(default_factory=list, description="List of reviewers")
    contract_details: Optional[dict[str, Any]] = Field(None, description="Contract details")
    tz_ref: Optional[str] = Field(None, description="Reference to technical specification")
    links: list[LinkReference] = Field(default_factory=list, description="Links to related objects")
    
    class_name: str = Field(default="metadata", frozen=True)


# ============================================================================
# Class 2: Regulatory Framework
# ============================================================================

class NormativeClause(BaseModel):
    """Clause/section of a regulatory document."""
    clause_id: str = Field(..., description="Clause number")
    description: Optional[str] = Field(None, description="Brief description")
    source_ref: Optional[str] = Field(None, description="Reference to vector index")


class RegulatoryFramework(BaseModel):
    """
    Regulatory documents (SP, GOST, SanPiN, etc.).
    File: regulatory_framework.json
    """
    id: str = Field(..., description="Unique ID (e.g., 'sp_22_13330_2016')")
    designation: str = Field(..., description="Document designation (e.g., 'СП 22.13330.2016')")
    full_name: str = Field(..., description="Full name of the document")
    status: Optional[str] = Field(None, description="Status (active/superseded)")
    effective_date: Optional[date] = Field(None, description="Effective date")
    replaced_by: Optional[str] = Field(None, description="ID of replacing document")
    clauses: list[NormativeClause] = Field(default_factory=list, description="Used clauses")
    links: list[LinkReference] = Field(default_factory=list)
    
    class_name: str = Field(default="regulatory_framework", frozen=True)


# ============================================================================
# Class 3: Input Data
# ============================================================================

class InputData(BaseModel):
    """
    Input parameters from external sources (not calculated in project).
    File: input_data.json
    """
    id: str = Field(..., description="Unique identifier")
    name: str = Field(..., description="Parameter name")
    value: Any = Field(..., description="Value (number, array, etc.)")
    unit: Optional[str] = Field(None, description="Unit of measurement")
    source_type: Optional[SourceStatus] = Field(None, description="Source type")
    source_ref: Optional[str] = Field(None, description="Reference to source in vector index")
    related_objects: list[LinkReference] = Field(default_factory=list)
    comment: Optional[str] = Field(None)
    links: list[LinkReference] = Field(default_factory=list)
    
    class_name: str = Field(default="input_data", frozen=True)


# ============================================================================
# Class 4: Reference Data
# ============================================================================

class ReferenceData(BaseModel):
    """
    Tabular values, coefficients, reference data from normative documents.
    File: reference_data.json
    """
    id: str = Field(..., description="Unique identifier")
    name: str = Field(..., description="Name (e.g., 'R0 for medium sand')")
    value: Any = Field(..., description="Value(s) - number, array, or table")
    unit: Optional[str] = Field(None, description="Unit of measurement")
    source_ref: Optional[str] = Field(None, description="Reference to normative source")
    links: list[LinkReference] = Field(default_factory=list)
    
    class_name: str = Field(default="reference_data", frozen=True)


# ============================================================================
# Class 5: Document Structure
# ============================================================================

class DocumentStructure(BaseModel):
    """
    Hierarchical structure of the explanatory note.
    File: document_structure.json
    """
    id: str = Field(..., description="Node unique identifier")
    title: str = Field(..., description="Section title")
    type: str = Field(..., description="Type: chapter/section/subsection")
    phase: Optional[str] = Field(None, description="Phase: concept/calculation/implementation")
    mandatory: Optional[bool] = Field(None, description="Mandatory per PP 87")
    generation_template: Optional[str] = Field(None, description="Template reference")
    content_refs: list[LinkReference] = Field(default_factory=list, description="Content object references")
    links: list[LinkReference] = Field(default_factory=list)
    comment: Optional[str] = Field(None)
    
    class_name: str = Field(default="document_structure", frozen=True)


# ============================================================================
# Class 6: Methods
# ============================================================================

class Method(BaseModel):
    """
    Calculation methods, algorithms, procedures.
    File: methods.json
    """
    id: str = Field(..., description="Unique identifier")
    name: str = Field(..., description="Method name")
    description: Optional[str] = Field(None, description="Brief description")
    source_ref: Optional[str] = Field(None, description="Normative source reference")
    inputs: list[LinkReference] = Field(default_factory=list, description="Input data references")
    outputs: list[LinkReference] = Field(default_factory=list, description="Output result references")
    submethods: list[str] = Field(default_factory=list, description="Nested method IDs")
    assumptions: list[str] = Field(default_factory=list, description="Assumption IDs")
    formulas: list[str] = Field(default_factory=list, description="Formula IDs")
    links: list[LinkReference] = Field(default_factory=list)
    comment: Optional[str] = Field(None)
    
    class_name: str = Field(default="methods", frozen=True)


# ============================================================================
# Class 7: Formulas
# ============================================================================

class FormulaVariable(BaseModel):
    """Variable in a formula."""
    id: str = Field(..., description="Variable ID from classes 3, 4, 10, 11")
    role: str = Field(..., description="Role: input/output")


class Formula(BaseModel):
    """
    Mathematical expressions used in calculations.
    File: formulas.json
    """
    id: str = Field(..., description="Unique identifier")
    symbolic: str = Field(..., description="Symbolic representation (LaTeX)")
    description: Optional[str] = Field(None, description="Brief description")
    source_ref: Optional[str] = Field(None, description="Normative source")
    variables: list[FormulaVariable] = Field(default_factory=list)
    result_unit: Optional[str] = Field(None, description="Result unit")
    links: list[LinkReference] = Field(default_factory=list)
    comment: Optional[str] = Field(None)
    
    class_name: str = Field(default="formulas", frozen=True)


# ============================================================================
# Class 8: Assumptions
# ============================================================================

class Assumption(BaseModel):
    """
    Designer's assumptions and simplifications.
    File: assumptions.json
    """
    id: str = Field(..., description="Unique identifier")
    description: str = Field(..., description="Description of assumption")
    justification: Optional[str] = Field(None, description="Justification")
    impact: Optional[str] = Field(None, description="Impact assessment: low/medium/high")
    source_ref: Optional[str] = Field(None, description="Normative reference")
    used_in: list[str] = Field(default_factory=list, description="Method/result IDs using this")
    links: list[LinkReference] = Field(default_factory=list)
    comment: Optional[str] = Field(None)
    
    class_name: str = Field(default="assumptions", frozen=True)


# ============================================================================
# Class 9: Design Decisions
# ============================================================================

class DesignDecision(BaseModel):
    """
    Categorical and qualitative designer choices.
    File: design_decisions.json
    """
    id: str = Field(..., description="Unique identifier")
    description: str = Field(..., description="What was chosen")
    rationale: Optional[str] = Field(None, description="Justification")
    source_ref: list[str] = Field(default_factory=list, description="Normative references")
    based_on: list[LinkReference] = Field(default_factory=list, description="Supporting objects")
    links: list[LinkReference] = Field(default_factory=list)
    comment: Optional[str] = Field(None)
    
    class_name: str = Field(default="design_decisions", frozen=True)


# ============================================================================
# Class 10: Intermediate Results
# ============================================================================

class IntermediateResult(BaseModel):
    """
    Intermediate calculation results (not final deliverables).
    File: intermediate_results.json
    """
    id: str = Field(..., description="Unique identifier")
    name: str = Field(..., description="Result name")
    value: float = Field(..., description="Numeric value")
    unit: Optional[str] = Field(None, description="Unit of measurement")
    method_ref: Optional[str] = Field(None, description="Method ID that produced this")
    inputs: list[str] = Field(default_factory=list, description="Input IDs used")
    links: list[LinkReference] = Field(default_factory=list)
    comment: Optional[str] = Field(None)
    
    class_name: str = Field(default="intermediate_results", frozen=True)


# ============================================================================
# Class 11: Final Results
# ============================================================================

class CheckResult(BaseModel):
    """Check result for final values."""
    description: str = Field(..., description="Check description")
    status: bool = Field(..., description="Pass/fail")
    norm_ref: Optional[str] = Field(None, description="Normative reference")


class FinalResult(BaseModel):
    """
    Final calculation results for deliverables.
    File: final_results.json
    """
    id: str = Field(..., description="Unique identifier")
    name: str = Field(..., description="Result name")
    value: Any = Field(..., description="Value(s)")
    unit: Optional[str] = Field(None, description="Unit of measurement")
    method_ref: Optional[str] = Field(None, description="Method ID")
    checks: list[CheckResult] = Field(default_factory=list, description="Validation checks")
    links: list[LinkReference] = Field(default_factory=list)
    comment: Optional[str] = Field(None)
    
    class_name: str = Field(default="final_results", frozen=True)


# ============================================================================
# Class 12: Comparison Data
# ============================================================================

class ComparisonVariant(BaseModel):
    """Variant for comparison."""
    name: str = Field(..., description="Variant name")
    parameters: list[dict[str, Any]] = Field(default_factory=list)
    cost: Optional[float] = Field(None, description="Capital cost")
    operating_cost: Optional[float] = Field(None, description="Operating cost")
    payback: Optional[float] = Field(None, description="Payback period")


class ComparisonData(BaseModel):
    """
    Data for selecting optimal design variant.
    File: comparison_data.json
    """
    id: str = Field(..., description="Unique identifier")
    variants: list[ComparisonVariant] = Field(default_factory=list)
    criteria: list[str] = Field(default_factory=list, description="Comparison criteria")
    selected_variant: Optional[str] = Field(None, description="Selected variant ID")
    rationale: Optional[str] = Field(None, description="Selection rationale")
    links: list[LinkReference] = Field(default_factory=list)
    comment: Optional[str] = Field(None)
    
    class_name: str = Field(default="comparison_data", frozen=True)


# ============================================================================
# Class 13: Guidelines
# ============================================================================

class Guideline(BaseModel):
    """
    Instructional guidelines (technology, safety, quality control).
    File: guidelines.json
    """
    id: str = Field(..., description="Unique identifier")
    description: str = Field(..., description="Guideline description")
    source_ref: list[str] = Field(default_factory=list, description="Normative references")
    links: list[LinkReference] = Field(default_factory=list)
    comment: Optional[str] = Field(None)
    
    class_name: str = Field(default="guidelines", frozen=True)


# ============================================================================
# Class 14: References
# ============================================================================

class Reference(BaseModel):
    """
    External and internal references (drawings, software, reports).
    File: references.json
    """
    id: str = Field(..., description="Unique identifier")
    type: str = Field(..., description="Type: drawing/software/report/etc.")
    name: str = Field(..., description="Name")
    details: Optional[dict[str, Any]] = Field(None, description="Type-specific details")
    links: list[LinkReference] = Field(default_factory=list)
    comment: Optional[str] = Field(None)
    
    class_name: str = Field(default="references", frozen=True)


# ============================================================================
# Class 15: Misc Data
# ============================================================================

class MiscData(BaseModel):
    """
    Miscellaneous unclassified data (pending reclassification).
    File: misc.json
    """
    id: str = Field(..., description="Unique identifier")
    description: str = Field(..., description="Description")
    source_context: Optional[str] = Field(None, description="Original context or index ref")
    needs_reclassification: bool = Field(default=True)
    links: list[LinkReference] = Field(default_factory=list)
    comment: Optional[str] = Field(None)
    
    class_name: str = Field(default="misc", frozen=True)


# ============================================================================
# Registry
# ============================================================================

CLASSES_REGISTRY: dict[str, type[BaseModel]] = {
    "metadata": Metadata,
    "regulatory_framework": RegulatoryFramework,
    "input_data": InputData,
    "reference_data": ReferenceData,
    "document_structure": DocumentStructure,
    "methods": Method,
    "formulas": Formula,
    "assumptions": Assumption,
    "design_decisions": DesignDecision,
    "intermediate_results": IntermediateResult,
    "final_results": FinalResult,
    "comparison_data": ComparisonData,
    "guidelines": Guideline,
    "references": Reference,
    "misc": MiscData,
}

# File names for each class
CLASS_FILE_NAMES: dict[str, str] = {
    "metadata": "metadata.json",
    "regulatory_framework": "regulatory_framework.json",
    "input_data": "input_data.json",
    "reference_data": "reference_data.json",
    "document_structure": "document_structure.json",
    "methods": "methods.json",
    "formulas": "formulas.json",
    "assumptions": "assumptions.json",
    "design_decisions": "design_decisions.json",
    "intermediate_results": "intermediate_results.json",
    "final_results": "final_results.json",
    "comparison_data": "comparison_data.json",
    "guidelines": "guidelines.json",
    "references": "references.json",
    "misc": "misc.json",
}