"""
Validator for PZ data classes.
Validates links between objects and fills missing class_name references.
"""

from typing import Optional
from dataclasses import dataclass, field

from .loader import ProjectData
from .classes import LinkReference, BaseModel


@dataclass
class ValidationResult:
    """Result of validation operation."""
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    fixed: list[str] = field(default_factory=list)


class Validator:
    """
    Validates cross-references between data objects.
    Fills missing class_name in LinkReference objects.
    """
    
    def __init__(self, project_data: ProjectData):
        """
        Initialize validator.
        
        Args:
            project_data: ProjectData instance with loaded objects
        """
        self.project = project_data
    
    def validate_all(self, fix: bool = False) -> ValidationResult:
        """
        Validate all objects in project.
        
        Args:
            fix: If True, fix missing class_name references
            
        Returns:
            ValidationResult with errors, warnings, and fixed items
        """
        result = ValidationResult(valid=True)
        
        # Validate each class
        for class_name in self.project._objects:
            for obj_id, obj in self.project._objects[class_name].items():
                self._validate_object(obj, result, fix)
        
        # Check for orphan links (references to non-existent objects)
        self._check_orphan_links(result)
        
        result.valid = len(result.errors) == 0
        return result
    
    def _validate_object(self, obj: BaseModel, result: ValidationResult, fix: bool) -> None:
        """
        Validate a single object.
        
        Args:
            obj: Object to validate
            result: ValidationResult to update
            fix: If True, fix missing class_name
        """
        obj_id = obj.id  # type: ignore
        links = getattr(obj, 'links', [])
        
        for i, link in enumerate(links):
            if not isinstance(link, LinkReference):
                continue
            
            # Check if target exists
            target_class = self.project.get_class_name(link.id)
            
            if target_class is None:
                result.warnings.append(
                    f"Object '{obj_id}': link to non-existent '{link.id}' (type: {link.type})"
                )
                continue
            
            # Check if class_name is set
            if link.class_name is None:
                if fix:
                    # Fix the class_name
                    link.class_name = target_class
                    result.fixed.append(
                        f"Object '{obj_id}': set class_name='{target_class}' for link to '{link.id}'"
                    )
                else:
                    result.warnings.append(
                        f"Object '{obj_id}': missing class_name for link to '{link.id}'"
                    )
            elif link.class_name != target_class:
                result.errors.append(
                    f"Object '{obj_id}': wrong class_name '{link.class_name}' for link to '{link.id}' "
                    f"(should be '{target_class}')"
                )
        
        # Check related_objects if present (InputData)
        related = getattr(obj, 'related_objects', [])
        for link in related:
            target_class = self.project.get_class_name(link.id)
            if target_class is None:
                result.warnings.append(
                    f"Object '{obj_id}': related_objects references non-existent '{link.id}'"
                )
        
        # Check content_refs if present (DocumentStructure)
        content_refs = getattr(obj, 'content_refs', [])
        for link in content_refs:
            target_class = self.project.get_class_name(link.id)
            if target_class is None:
                result.warnings.append(
                    f"Object '{obj_id}': content_refs references non-existent '{link.id}'"
                )
        
        # Check inputs/outputs if present (Method)
        for attr_name in ['inputs', 'outputs']:
            refs = getattr(obj, attr_name, [])
            for link in refs:
                target_class = self.project.get_class_name(link.id)
                if target_class is None:
                    result.warnings.append(
                        f"Object '{obj_id}': {attr_name} references non-existent '{link.id}'"
                    )
        
        # Check formula variables
        variables = getattr(obj, 'variables', [])
        for var in variables:
            if hasattr(var, 'id'):
                target_class = self.project.get_class_name(var.id)
                if target_class is None:
                    result.warnings.append(
                        f"Object '{obj_id}': variable '{var.id}' not found"
                    )
    
    def _check_orphan_links(self, result: ValidationResult) -> None:
        """Check for objects that are referenced but don't exist."""
        # Collect all referenced IDs
        referenced_ids = set()
        
        for class_name in self.project._objects:
            for obj_id, obj in self.project._objects[class_name].items():
                links = getattr(obj, 'links', [])
                for link in links:
                    if isinstance(link, LinkReference):
                        referenced_ids.add(link.id)
        
        # Check which referenced IDs don't exist
        for ref_id in referenced_ids:
            if self.project.get(ref_id) is None:
                # Already reported in warnings above
                pass
    
    def validate_ids_unique(self) -> ValidationResult:
        """
        Check that all IDs are unique across all classes.
        
        Returns:
            ValidationResult with any duplicate ID errors
        """
        result = ValidationResult(valid=True)
        seen_ids: dict[str, str] = {}  # id -> class_name
        
        for class_name in self.project._objects:
            for obj_id in self.project._objects[class_name]:
                if obj_id in seen_ids:
                    result.errors.append(
                        f"Duplicate ID '{obj_id}' found in both '{seen_ids[obj_id]}' and '{class_name}'"
                    )
                else:
                    seen_ids[obj_id] = class_name
        
        result.valid = len(result.errors) == 0
        return result
    
    def validate_class_consistency(self) -> ValidationResult:
        """
        Check that class_name field matches the actual class.
        
        Returns:
            ValidationResult with any inconsistencies
        """
        result = ValidationResult(valid=True)
        
        for class_name in self.project._objects:
            for obj_id, obj in self.project._objects[class_name].items():
                obj_class_name = getattr(obj, 'class_name', None)
                if obj_class_name and obj_class_name != class_name:
                    result.errors.append(
                        f"Object '{obj_id}': class_name='{obj_class_name}' but stored in '{class_name}'"
                    )
        
        result.valid = len(result.errors) == 0
        return result


def validate_project(project_data: ProjectData, fix: bool = False) -> ValidationResult:
    """
    Convenience function to validate a project.
    
    Args:
        project_data: ProjectData instance
        fix: If True, fix missing class_name references
        
    Returns:
        ValidationResult
    """
    validator = Validator(project_data)
    return validator.validate_all(fix)