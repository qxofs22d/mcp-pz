"""
Loader for PZ data classes from JSON files.
Handles loading, parsing, and indexing of all 15 class files.
"""

import json
from pathlib import Path
from typing import Any, Optional
from pydantic import ValidationError

from .classes import (
    CLASSES_REGISTRY,
    CLASS_FILE_NAMES,
    BaseModel,
)


class ProjectData:
    """
    Container for all project data classes.
    Provides loading, indexing, and access to objects by ID.
    """
    
    def __init__(self, project_path: str | Path):
        """
        Initialize project data container.
        
        Args:
            project_path: Path to project directory
        """
        self.project_path = Path(project_path)
        self.data_path = self.project_path / "data"
        self.classes_path = self.data_path / "classes"
        
        # Storage: {class_name: {object_id: object}}
        self._objects: dict[str, dict[str, BaseModel]] = {}
        
        # Global index: {object_id: (class_name, object)}
        self._index: dict[str, tuple[str, BaseModel]] = {}
        
        # Initialize empty containers for all classes
        for class_name in CLASSES_REGISTRY:
            self._objects[class_name] = {}
    
    def load_all(self) -> dict[str, Any]:
        """
        Load all class files from project.
        
        Returns:
            Dict with loading status: {class_name: {"loaded": int, "errors": list}}
        """
        results = {}
        
        for class_name in CLASSES_REGISTRY:
            results[class_name] = self.load_class(class_name)
        
        return results
    
    def load_class(self, class_name: str) -> dict[str, Any]:
        """
        Load a single class file.
        
        Args:
            class_name: Name of class (e.g., 'input_data')
            
        Returns:
            Dict with 'loaded' count and 'errors' list
        """
        result = {"loaded": 0, "errors": []}
        
        if class_name not in CLASSES_REGISTRY:
            result["errors"].append(f"Unknown class: {class_name}")
            return result
        
        file_name = CLASS_FILE_NAMES.get(class_name, f"{class_name}.json")
        file_path = self.classes_path / file_name
        
        if not file_path.exists():
            # File doesn't exist yet - not an error, just empty
            return result
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            result["errors"].append(f"JSON parse error: {e}")
            return result
        except Exception as e:
            result["errors"].append(f"File read error: {e}")
            return result
        
        # Handle both array and single object
        if isinstance(data, dict):
            items = [data]
        elif isinstance(data, list):
            items = data
        else:
            result["errors"].append(f"Invalid data format: expected dict or list")
            return result
        
        model_class = CLASSES_REGISTRY[class_name]
        
        for item in items:
            try:
                obj = model_class.model_validate(item)
                self._add_object(class_name, obj)
                result["loaded"] += 1
            except ValidationError as e:
                result["errors"].append(f"Validation error for {item.get('id', 'unknown')}: {e}")
        
        return result
    
    def _add_object(self, class_name: str, obj: BaseModel) -> None:
        """Add object to storage and index."""
        obj_id = obj.id  # type: ignore
        self._objects[class_name][obj_id] = obj
        self._index[obj_id] = (class_name, obj)
    
    def get(self, obj_id: str) -> Optional[BaseModel]:
        """
        Get object by ID from any class.
        
        Args:
            obj_id: Object identifier
            
        Returns:
            Object instance or None if not found
        """
        entry = self._index.get(obj_id)
        return entry[1] if entry else None
    
    def get_by_class(self, class_name: str, obj_id: str) -> Optional[BaseModel]:
        """
        Get object by ID from specific class.
        
        Args:
            class_name: Class name
            obj_id: Object identifier
            
        Returns:
            Object instance or None if not found
        """
        return self._objects.get(class_name, {}).get(obj_id)
    
    def get_all(self, class_name: str) -> dict[str, BaseModel]:
        """
        Get all objects of a class.
        
        Args:
            class_name: Class name
            
        Returns:
            Dict of {id: object}
        """
        return self._objects.get(class_name, {})
    
    def get_class_name(self, obj_id: str) -> Optional[str]:
        """
        Get class name for an object ID.
        
        Args:
            obj_id: Object identifier
            
        Returns:
            Class name or None if not found
        """
        entry = self._index.get(obj_id)
        return entry[0] if entry else None
    
    def list_ids(self, class_name: Optional[str] = None) -> list[str]:
        """
        List all object IDs.
        
        Args:
            class_name: Optional filter by class
            
        Returns:
            List of object IDs
        """
        if class_name:
            return list(self._objects.get(class_name, {}).keys())
        return list(self._index.keys())
    
    def stats(self) -> dict[str, int]:
        """
        Get statistics about loaded objects.
        
        Returns:
            Dict with counts per class
        """
        return {
            class_name: len(objects) 
            for class_name, objects in self._objects.items()
        }
    
    def save_class(self, class_name: str) -> bool:
        """
        Save a class to JSON file.
        
        Args:
            class_name: Name of class to save
            
        Returns:
            True if successful
        """
        if class_name not in CLASSES_REGISTRY:
            return False
        
        # Ensure directory exists
        self.classes_path.mkdir(parents=True, exist_ok=True)
        
        file_name = CLASS_FILE_NAMES.get(class_name, f"{class_name}.json")
        file_path = self.classes_path / file_name
        
        objects = list(self._objects[class_name].values())
        data = [obj.model_dump(mode='json') for obj in objects]
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False
    
    def add_object(self, obj: BaseModel) -> None:
        """
        Add a new object to storage.
        
        Args:
            obj: Pydantic model instance
        """
        class_name = obj.class_name  # type: ignore
        self._add_object(class_name, obj)


def load_project(project_path: str | Path) -> ProjectData:
    """
    Convenience function to load a project.
    
    Args:
        project_path: Path to project directory
        
    Returns:
        ProjectData instance with loaded data
    """
    project = ProjectData(project_path)
    project.load_all()
    return project