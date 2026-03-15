"""
Project Manager MCP Server — управление проектами, файлами и состоянием.

Обеспечивает единую точку управления проектом: создание папок, 
копирование PDF, сохранение прогресса, доступ к файлам и метаданным.

Интеграция с core:
- Загрузка и валидация данных через core.loader и core.validator
- Построение графа зависимостей через core.graph
- Работа с 15 классами данных ПЗ

Структура проекта:
    project/
    ├── state.json           # рабочее состояние
    ├── pdf/                 # PDF-документы
    ├── data/                # данные расчётов
    │   └── classes/         # JSON-файлы классов данных
    ├── output/              # результаты (md-файлы)
    ├── vector_index/        # векторный индекс
    └── pdf_cache/           # кэш декомпозиции PDF
"""

import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Any, List, Dict

from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio

# Добавляем путь к core для импорта
_PLATFORM_PATH = Path(__file__).parent.parent.parent
if str(_PLATFORM_PATH) not in sys.path:
    sys.path.insert(0, str(_PLATFORM_PATH))

# Импорты core-библиотеки
try:
    from core.loader import ProjectData, load_project
    from core.validator import Validator, validate_project
    from core.graph import CalculationGraph, CycleType
    from core.classes import CLASSES_REGISTRY, CLASS_FILE_NAMES
    CORE_AVAILABLE = True
except ImportError as e:
    CORE_AVAILABLE = False
    _import_error = str(e)

# Создаём экземпляр MCP-сервера
server = Server("project_manager")

# Состояние проекта (глобальная переменная)
_current_project: Optional["ProjectManager"] = None

# Путь к Платформе (для глобальных скиллов)
PLATFORM_PATH = Path(__file__).parent.parent.parent


class ProjectManager:
    """
    Класс для управления проектом.
    
    Атрибуты:
        path: Путь к папке проекта
        state: Текущее состояние проекта (словарь)
    """
    
    DEFAULT_STATE = {
        "project_name": "",
        "created_at": None,
        "updated_at": None,
        "pdfs": [],
        "sections": [],
        "parameters": {},
        "metadata": {}
    }
    
    def __init__(self, project_path: str):
        """
        Инициализация менеджера проекта.
        
        Args:
            project_path: Путь к папке проекта
        """
        self.path = Path(project_path).resolve()
        self.state = self._load_state()
    
    def _state_file(self) -> Path:
        """Возвращает путь к файлу состояния."""
        return self.path / "state.json"
    
    def _vector_index_dir(self) -> Path:
        """Возвращает путь к папке векторного индекса."""
        return self.path / "vector_index"
    
    def _pdf_cache_dir(self) -> Path:
        """Возвращает путь к папке кэша PDF."""
        return self.path / "pdf_cache"
    
    def _load_state(self) -> dict:
        """
        Загружает состояние из файла state.json.
        
        Returns:
            Словарь с состоянием проекта
        """
        state_file = self._state_file()
        if state_file.exists():
            with open(state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return self.DEFAULT_STATE.copy()
    
    def _save_state(self):
        """Сохраняет текущее состояние в файл state.json."""
        self.state["updated_at"] = datetime.now().isoformat()
        state_file = self._state_file()
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)
    
    def is_pzproject(self) -> bool:
        """
        Проверяет, является ли папка проектом ПЗ.
        
        Returns:
            True если есть state.json
        """
        return self._state_file().exists()
    
    def init_project(self, description: str = "") -> dict:
        """
        Инициализирует новый проект ПЗ с полной структурой.
        
        Создаёт:
        - state.json — рабочее состояние
        - pdf/ — папка для PDF-документов
        - data/ — папка для данных расчётов
        - output/ — папка для результатов (md-файлы)
        - vector_index/ — папка для векторного индекса
        - pdf_cache/ — папка для кэша PDF
        
        Args:
            description: Описание проекта
        
        Returns:
            Статус операции
        """
        # Создаём структуру папок
        (self.path / "pdf").mkdir(parents=True, exist_ok=True)
        (self.path / "data").mkdir(parents=True, exist_ok=True)
        (self.path / "output").mkdir(parents=True, exist_ok=True)
        (self._vector_index_dir()).mkdir(parents=True, exist_ok=True)
        (self._pdf_cache_dir()).mkdir(parents=True, exist_ok=True)
        
        # Инициализируем состояние
        self.state = self.DEFAULT_STATE.copy()
        self.state["project_name"] = self.path.name
        self.state["description"] = description
        self.state["created_at"] = datetime.now().isoformat()
        self._save_state()
        
        return {
            "success": True,
            "message": f"Проект ПЗ инициализирован: {self.path}",
            "project_name": self.state["project_name"],
            "structure": {
                "state.json": "рабочее состояние",
                "pdf/": "PDF-документы",
                "data/": "данные расчётов",
                "output/": "результаты (md-файлы)",
                "vector_index/": "векторный индекс",
                "pdf_cache/": "кэш декомпозиции PDF"
            }
        }
    
    def create_project(self) -> dict:
        """
        Создаёт новый проект с папками pdf, data, output и файлом state.json.
        
        Returns:
            Статус операции
        """
        # Создаём структуру папок
        (self.path / "pdf").mkdir(parents=True, exist_ok=True)
        (self.path / "data").mkdir(parents=True, exist_ok=True)
        (self.path / "output").mkdir(parents=True, exist_ok=True)
        
        # Инициализируем состояние
        self.state = self.DEFAULT_STATE.copy()
        self.state["project_name"] = self.path.name
        self.state["created_at"] = datetime.now().isoformat()
        self._save_state()
        
        return {
            "success": True,
            "message": f"Проект создан: {self.path}",
            "project_name": self.state["project_name"]
        }
    
    def load_project(self) -> dict:
        """
        Загружает существующий проект.
        
        Returns:
            Статус операции с состоянием проекта
        """
        if not self.path.exists():
            return {
                "success": False,
                "error": f"Папка проекта не существует: {self.path}",
                "suggestion": "Создайте новый проект с помощью init_project"
            }
        
        if not self._state_file().exists():
            return {
                "success": False,
                "error": "Файл state.json не найден",
                "suggestion": "Возможно, это не папка проекта. Создайте новый проект."
            }
        
        self.state = self._load_state()
        return {
            "success": True,
            "message": f"Проект загружен: {self.state.get('project_name', self.path.name)}",
            "state": self.state
        }
    
    def detect_project(self) -> dict:
        """
        Определяет, является ли текущая папка проектом ПЗ.
        
        Returns:
            Информация о проекте или предложение инициализировать
        """
        has_state = self._state_file().exists()
        
        if has_state:
            return {
                "success": True,
                "is_pzproject": True,
                "message": "Обнаружен проект ПЗ",
                "project_path": str(self.path),
                "state": self.state
            }
        else:
            return {
                "success": True,
                "is_pzproject": False,
                "message": "Папка не является проектом ПЗ",
                "project_path": str(self.path),
                "suggestion": "Используйте init_project для создания нового проекта"
            }
    
    def get_project_info(self) -> dict:
        """
        Возвращает полную информацию о проекте.
        
        Returns:
            Информация о проекте (пути, статистика, статус)
        """
        # Статистика PDF
        pdfs = self.state.get("pdfs", [])
        pdf_stats = {
            "total": len(pdfs),
            "processed": sum(1 for p in pdfs if p.get("processed")),
            "indexed": sum(1 for p in pdfs if p.get("indexed"))
        }
        
        # Статистика разделов
        sections = self.state.get("sections", [])
        section_stats = {
            "total": len(sections),
            "draft": sum(1 for s in sections if s.get("status") == "draft"),
            "complete": sum(1 for s in sections if s.get("status") == "complete")
        }
        
        return {
            "success": True,
            "project_path": str(self.path),
            "project_name": self.state.get("project_name", self.path.name),
            "description": self.state.get("description", ""),
            # Данные из state
            "pdfs": pdfs,
            "sections": sections,
            "metadata": self.state.get("metadata", {}),
            # Пути
            "paths": {
                "pdf": str(self.path / "pdf"),
                "data": str(self.path / "data"),
                "output": str(self.path / "output"),
                "vector_index": str(self._vector_index_dir()),
                "pdf_cache": str(self._pdf_cache_dir()),
                "state": str(self._state_file())
            },
            "stats": {
                "pdfs": pdf_stats,
                "sections": section_stats
            },
            "created_at": self.state.get("created_at"),
            "updated_at": self.state.get("updated_at")
        }
    
    def add_pdf(self, file_path: str) -> dict:
        """
        Добавляет PDF в проект (копирует в папку pdf/).
        
        Args:
            file_path: Путь к исходному PDF-файлу
        
        Returns:
            Статус операции
        """
        src_path = Path(file_path).resolve()
        
        if not src_path.exists():
            return {
                "success": False,
                "error": f"Файл не найден: {src_path}"
            }
        
        if not src_path.suffix.lower() == ".pdf":
            return {
                "success": False,
                "error": "Файл должен быть в формате PDF"
            }
        
        # Копируем в папку pdf/
        dest_path = self.path / "pdf" / src_path.name
        try:
            shutil.copy2(src_path, dest_path)
        except Exception as e:
            return {
                "success": False,
                "error": f"Ошибка копирования: {str(e)}"
            }
        
        # Обновляем состояние
        pdf_info = {
            "filename": src_path.name,
            "relative_path": f"pdf/{src_path.name}",
            "added_at": datetime.now().isoformat(),
            "processed": False,
            "indexed": False
        }
        
        # Проверяем, нет ли уже этого файла
        existing = [p for p in self.state["pdfs"] if p["filename"] == src_path.name]
        if not existing:
            self.state["pdfs"].append(pdf_info)
            self._save_state()
        
        return {
            "success": True,
            "message": f"PDF добавлен: {src_path.name}",
            "pdf_info": pdf_info
        }
    
    def get_state(self) -> dict:
        """
        Возвращает текущее состояние проекта.
        
        Returns:
            Состояние проекта
        """
        return {
            "success": True,
            "project_path": str(self.path),
            "state": self.state
        }
    
    def update_state(self, updates: dict) -> dict:
        """
        Обновляет отдельные поля состояния.
        
        Args:
            updates: Словарь с обновлениями
        
        Returns:
            Статус операции
        """
        def deep_update(target: dict, source: dict):
            """Рекурсивное обновление словаря."""
            for key, value in source.items():
                if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                    deep_update(target[key], value)
                else:
                    target[key] = value
        
        deep_update(self.state, updates)
        self._save_state()
        
        return {
            "success": True,
            "message": "Состояние обновлено",
            "updated_fields": list(updates.keys())
        }
    
    def save_section_text(self, section_title: str, text: str) -> dict:
        """
        Сохраняет текст раздела в папку output/ и обновляет состояние.
        
        Args:
            section_title: Название раздела
            text: Текст раздела
        
        Returns:
            Статус операции
        """
        # Формируем имя файла из названия раздела
        filename = section_title.lower().replace(" ", "_").replace("/", "_") + ".md"
        output_path = self.path / "output" / filename
        
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception as e:
            return {
                "success": False,
                "error": f"Ошибка сохранения файла: {str(e)}"
            }
        
        # Обновляем информацию о разделе в состоянии
        section_found = False
        for sec in self.state.get("sections", []):
            if sec.get("title") == section_title:
                sec["output_file"] = f"output/{filename}"
                sec["status"] = "draft"
                sec["updated_at"] = datetime.now().isoformat()
                section_found = True
                break
        
        if not section_found:
            if "sections" not in self.state:
                self.state["sections"] = []
            self.state["sections"].append({
                "title": section_title,
                "output_file": f"output/{filename}",
                "status": "draft",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            })
        
        self._save_state()
        
        return {
            "success": True,
            "message": f"Раздел '{section_title}' сохранён",
            "output_file": f"output/{filename}"
        }
    
    # ========================================================================
    # Методы для работы с core-библиотекой (15 классов данных ПЗ)
    # ========================================================================
    
    def load_data_classes(self) -> dict:
        """
        Загружает все классы данных ПЗ через core.loader.
        
        Returns:
            Статус загрузки с количеством объектов по классам
        """
        if not CORE_AVAILABLE:
            return {
                "success": False,
                "error": f"Core-библиотека недоступна: {_import_error}"
            }
        
        try:
            project_data = load_project(self.path)
            stats = project_data.stats()
            
            return {
                "success": True,
                "message": f"Загружено {sum(stats.values())} объектов из {self.path}",
                "stats": stats,
                "classes_available": list(CLASSES_REGISTRY.keys())
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Ошибка загрузки данных: {str(e)}"
            }
    
    def validate_data(self, fix: bool = False) -> dict:
        """
        Валидирует данные проекта через core.validator.
        
        Args:
            fix: Исправлять ли автоматически missing class_name
        
        Returns:
            Результаты валидации
        """
        if not CORE_AVAILABLE:
            return {
                "success": False,
                "error": f"Core-библиотека недоступна: {_import_error}"
            }
        
        try:
            project_data = load_project(self.path)
            result = validate_project(project_data, fix=fix)
            
            # Если были исправления, сохраняем
            if fix and result.fixed:
                for class_name in project_data._objects:
                    project_data.save_class(class_name)
            
            return {
                "success": True,
                "valid": result.valid,
                "errors_count": len(result.errors),
                "warnings_count": len(result.warnings),
                "fixed_count": len(result.fixed),
                "errors": result.errors[:20],
                "warnings": result.warnings[:20],
                "fixed": result.fixed[:20]
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Ошибка валидации: {str(e)}"
            }
    
    def get_graph_stats(self) -> dict:
        """
        Возвращает статистику графа зависимостей.
        
        Returns:
            Статистика графа: узлы, связи, циклы
        """
        if not CORE_AVAILABLE:
            return {
                "success": False,
                "error": f"Core-библиотека недоступна: {_import_error}"
            }
        
        try:
            project_data = load_project(self.path)
            graph = CalculationGraph(project_data)
            graph.build()
            
            stats = graph.stats()
            cycles = graph.find_cycles()
            
            return {
                "success": True,
                "total_nodes": stats.total_nodes,
                "total_edges": stats.total_edges,
                "cycles_count": stats.cycles_count,
                "unlinked_nodes": stats.unlinked_nodes,
                "nodes_by_type": {k.value: v for k, v in stats.nodes_by_type.items()},
                "cycles": [
                    {
                        "path": c.path,
                        "type": c.cycle_type.value,
                        "description": c.description
                    }
                    for c in cycles[:10]
                ]
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Ошибка построения графа: {str(e)}"
            }
    
    def get_impact_analysis(self, obj_id: str) -> dict:
        """
        Анализ влияния изменения объекта.
        
        Args:
            obj_id: ID объекта для анализа
        
        Returns:
            Список затронутых объектов
        """
        if not CORE_AVAILABLE:
            return {
                "success": False,
                "error": f"Core-библиотека недоступна: {_import_error}"
            }
        
        try:
            project_data = load_project(self.path)
            graph = CalculationGraph(project_data)
            graph.build()
            
            result = graph.impact_analysis(obj_id)
            
            if result is None:
                return {
                    "success": False,
                    "error": f"Объект не найден: {obj_id}"
                }
            
            return {
                "success": True,
                "source_id": obj_id,
                "affected_count": len(result.affected_ids),
                "direct_deps_count": len(result.direct_deps),
                "affected_ids": result.affected_ids[:50],
                "direct_deps": result.direct_deps[:20]
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Ошибка анализа влияния: {str(e)}"
            }
    
    def list_data_objects(self, class_name: Optional[str] = None) -> dict:
        """
        Возвращает список объектов данных.
        
        Args:
            class_name: Имя класса для фильтрации (опционально)
        
        Returns:
            Список объектов с ID и именами
        """
        if not CORE_AVAILABLE:
            return {
                "success": False,
                "error": f"Core-библиотека недоступна: {_import_error}"
            }
        
        try:
            project_data = load_project(self.path)
            
            if class_name:
                if class_name not in CLASSES_REGISTRY:
                    return {
                        "success": False,
                        "error": f"Неизвестный класс: {class_name}",
                        "available_classes": list(CLASSES_REGISTRY.keys())
                    }
                
                objects = project_data.get_all(class_name)
                items = []
                for obj_id, obj in objects.items():
                    name = getattr(obj, 'name', None) or getattr(obj, 'title', None) or getattr(obj, 'designation', None)
                    items.append({
                        "id": obj_id,
                        "name": name,
                        "class": class_name
                    })
                
                return {
                    "success": True,
                    "class_name": class_name,
                    "count": len(items),
                    "objects": items
                }
            else:
                # Все классы
                result = {}
                total = 0
                for cn in CLASSES_REGISTRY:
                    objects = project_data.get_all(cn)
                    if objects:
                        result[cn] = list(objects.keys())
                        total += len(objects)
                
                return {
                    "success": True,
                    "total_objects": total,
                    "by_class": result
                }
        except Exception as e:
            return {
                "success": False,
                "error": f"Ошибка получения объектов: {str(e)}"
            }
    
    def get_object_details(self, obj_id: str) -> dict:
        """
        Возвращает детальную информацию об объекте.
        
        Args:
            obj_id: ID объекта
        
        Returns:
            Полные данные объекта
        """
        if not CORE_AVAILABLE:
            return {
                "success": False,
                "error": f"Core-библиотека недоступна: {_import_error}"
            }
        
        try:
            project_data = load_project(self.path)
            obj = project_data.get(obj_id)
            
            if obj is None:
                return {
                    "success": False,
                    "error": f"Объект не найден: {obj_id}"
                }
            
            class_name = project_data.get_class_name(obj_id)
            data = obj.model_dump(mode='json')
            
            return {
                "success": True,
                "id": obj_id,
                "class_name": class_name,
                "data": data
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Ошибка получения объекта: {str(e)}"
            }
    
    def get_calculation_order(self) -> dict:
        """
        Возвращает топологический порядок вычислений.
        
        Returns:
            Порядок вычислений или информация о циклах
        """
        if not CORE_AVAILABLE:
            return {
                "success": False,
                "error": f"Core-библиотека недоступна: {_import_error}"
            }
        
        try:
            project_data = load_project(self.path)
            graph = CalculationGraph(project_data)
            graph.build()
            
            order = graph.topological_order()
            
            if order is None:
                return {
                    "success": True,
                    "has_logical_cycles": True,
                    "message": "Невозможно построить порядок из-за логических циклов",
                    "cycles": [
                        {
                            "path": c.path,
                            "description": c.description
                        }
                        for c in graph.cycles
                        if c.cycle_type == CycleType.LOGICAL
                    ]
                }
            
            return {
                "success": True,
                "has_logical_cycles": False,
                "order": order,
                "total_steps": len(order)
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Ошибка построения порядка: {str(e)}"
            }
    
    def export_graph_dot(self, title: Optional[str] = None) -> dict:
        """
        Экспортирует граф в формате Graphviz DOT.
        
        Args:
            title: Заголовок графа
        
        Returns:
            DOT-содержимое
        """
        if not CORE_AVAILABLE:
            return {
                "success": False,
                "error": f"Core-библиотека недоступна: {_import_error}"
            }
        
        try:
            project_data = load_project(self.path)
            graph = CalculationGraph(project_data)
            graph.build()
            
            dot_content = graph.export_dot(title or f"Graph: {self.path.name}")
            
            # Сохраняем в output
            output_path = self.path / "output" / "graph.dot"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(dot_content)
            
            return {
                "success": True,
                "message": "DOT-файл экспортирован",
                "output_file": "output/graph.dot",
                "content": dot_content
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Ошибка экспорта: {str(e)}"
            }


@server.list_tools()
async def list_tools():
    """Возвращает список доступных инструментов."""
    return [
        Tool(
            name="init_project",
            description="Инициализирует новый проект ПЗ с полной структурой (state.json, pdf/, data/, output/, vector_index/, pdf_cache/).",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Путь к папке проекта"
                    },
                    "description": {
                        "type": "string",
                        "description": "Описание проекта (опционально)"
                    }
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="detect_project",
            description="Определяет, является ли указанная папка проектом ПЗ (наличие state.json).",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Путь к проверяемой папке"
                    }
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="load_project",
            description="Загружает существующий проект из указанной папки, восстанавливая состояние из state.json.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Путь к папке проекта"
                    }
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="get_project_info",
            description="Возвращает полную информацию о проекте: пути, статистика, состояние.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="add_pdf",
            description="Добавляет PDF-файл в проект (копирует в папку pdf/ и обновляет state.json).",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Путь к исходному PDF-файлу"
                    }
                },
                "required": ["file_path"]
            }
        ),
        Tool(
            name="get_state",
            description="Возвращает текущее состояние проекта.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="update_state",
            description="Обновляет отдельные поля состояния проекта.",
            inputSchema={
                "type": "object",
                "properties": {
                    "updates": {
                        "type": "object",
                        "description": "Словарь с обновлениями состояния",
                        "additionalProperties": True
                    }
                },
                "required": ["updates"]
            }
        ),
        Tool(
            name="save_state",
            description="Принудительно сохраняет текущее состояние в state.json.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="save_section_text",
            description="Сохраняет текст раздела в папку output/ и обновляет информацию о разделе в state.json.",
            inputSchema={
                "type": "object",
                "properties": {
                    "section_title": {
                        "type": "string",
                        "description": "Название раздела"
                    },
                    "text": {
                        "type": "string",
                        "description": "Текст раздела"
                    }
                },
                "required": ["section_title", "text"]
            }
        ),
        # Инструменты для работы с core-библиотекой (15 классов данных ПЗ)
        Tool(
            name="load_data_classes",
            description="Загружает все классы данных ПЗ (15 классов) из папки data/classes/. Возвращает статистику по каждому классу.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="validate_data",
            description="Валидирует данные проекта: проверяет ссылки между объектами, заполняет missing class_name. Используйте fix=true для автоматического исправления.",
            inputSchema={
                "type": "object",
                "properties": {
                    "fix": {
                        "type": "boolean",
                        "description": "Автоматически исправлять missing class_name (по умолчанию false)"
                    }
                }
            }
        ),
        Tool(
            name="get_graph_stats",
            description="Возвращает статистику графа зависимостей: количество узлов, связей, циклов, изолированных узлов.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="get_impact_analysis",
            description="Анализ влияния: находит все объекты, которые зависят от указанного объекта (прямо или косвенно).",
            inputSchema={
                "type": "object",
                "properties": {
                    "object_id": {
                        "type": "string",
                        "description": "ID объекта для анализа влияния"
                    }
                },
                "required": ["object_id"]
            }
        ),
        Tool(
            name="list_data_objects",
            description="Возвращает список объектов данных. Можно фильтровать по имени класса.",
            inputSchema={
                "type": "object",
                "properties": {
                    "class_name": {
                        "type": "string",
                        "description": "Имя класса для фильтрации (metadata, input_data, formulas, methods, final_results и т.д.)"
                    }
                }
            }
        ),
        Tool(
            name="get_object_details",
            description="Возвращает детальную информацию об объекте по его ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "object_id": {
                        "type": "string",
                        "description": "ID объекта"
                    }
                },
                "required": ["object_id"]
            }
        ),
        Tool(
            name="get_calculation_order",
            description="Возвращает топологический порядок вычислений (порядок расчёта объектов).",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="export_graph_dot",
            description="Экспортирует граф зависимостей в формат Graphviz DOT для визуализации.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Заголовок графа (опционально)"
                    }
                }
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    """Обрабатывает вызовы инструментов."""
    global _current_project
    
    if name == "init_project":
        project_path = arguments.get("path")
        if not project_path:
            return [TextContent(type="text", text="Ошибка: не указан путь к проекту.")]
        
        _current_project = ProjectManager(project_path)
        result = _current_project.init_project(
            description=arguments.get("description", "")
        )
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "detect_project":
        project_path = arguments.get("path")
        if not project_path:
            return [TextContent(type="text", text="Ошибка: не указан путь к папке.")]
        
        project = ProjectManager(project_path)
        result = project.detect_project()
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "load_project":
        project_path = arguments.get("path")
        if not project_path:
            return [TextContent(type="text", text="Ошибка: не указан путь к проекту.")]
        
        _current_project = ProjectManager(project_path)
        result = _current_project.load_project()
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "get_project_info":
        if not _current_project:
            return [TextContent(type="text", text="Ошибка: проект не загружен.")]
        
        result = _current_project.get_project_info()
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "add_pdf":
        if not _current_project:
            return [TextContent(type="text", text="Ошибка: проект не загружен. Сначала вызовите load_project или create_project.")]
        
        file_path = arguments.get("file_path")
        if not file_path:
            return [TextContent(type="text", text="Ошибка: не указан путь к файлу.")]
        
        result = _current_project.add_pdf(file_path)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "get_state":
        if not _current_project:
            return [TextContent(type="text", text="Ошибка: проект не загружен.")]
        
        result = _current_project.get_state()
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "update_state":
        if not _current_project:
            return [TextContent(type="text", text="Ошибка: проект не загружен.")]
        
        updates = arguments.get("updates", {})
        result = _current_project.update_state(updates)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "save_state":
        if not _current_project:
            return [TextContent(type="text", text="Ошибка: проект не загружен.")]
        
        _current_project._save_state()
        return [TextContent(type="text", text="Состояние сохранено.")]
    
    elif name == "save_section_text":
        if not _current_project:
            return [TextContent(type="text", text="Ошибка: проект не загружен.")]
        
        section_title = arguments.get("section_title")
        text = arguments.get("text")
        
        if not section_title or text is None:
            return [TextContent(type="text", text="Ошибка: не указаны section_title или text.")]
        
        result = _current_project.save_section_text(section_title, text)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    # Новые инструменты для работы с core-библиотекой
    elif name == "load_data_classes":
        if not _current_project:
            return [TextContent(type="text", text="Ошибка: проект не загружен.")]
        
        result = _current_project.load_data_classes()
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "validate_data":
        if not _current_project:
            return [TextContent(type="text", text="Ошибка: проект не загружен.")]
        
        fix = arguments.get("fix", False)
        result = _current_project.validate_data(fix=fix)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "get_graph_stats":
        if not _current_project:
            return [TextContent(type="text", text="Ошибка: проект не загружен.")]
        
        result = _current_project.get_graph_stats()
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "get_impact_analysis":
        if not _current_project:
            return [TextContent(type="text", text="Ошибка: проект не загружен.")]
        
        obj_id = arguments.get("object_id")
        if not obj_id:
            return [TextContent(type="text", text="Ошибка: не указан object_id.")]
        
        result = _current_project.get_impact_analysis(obj_id)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "list_data_objects":
        if not _current_project:
            return [TextContent(type="text", text="Ошибка: проект не загружен.")]
        
        class_name = arguments.get("class_name")
        result = _current_project.list_data_objects(class_name)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "get_object_details":
        if not _current_project:
            return [TextContent(type="text", text="Ошибка: проект не загружен.")]
        
        obj_id = arguments.get("object_id")
        if not obj_id:
            return [TextContent(type="text", text="Ошибка: не указан object_id.")]
        
        result = _current_project.get_object_details(obj_id)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "get_calculation_order":
        if not _current_project:
            return [TextContent(type="text", text="Ошибка: проект не загружен.")]
        
        result = _current_project.get_calculation_order()
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "export_graph_dot":
        if not _current_project:
            return [TextContent(type="text", text="Ошибка: проект не загружен.")]
        
        title = arguments.get("title")
        result = _current_project.export_graph_dot(title)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    return [TextContent(type="text", text=f"Неизвестный инструмент: {name}")]


async def main():
    """Запускает MCP-сервер."""
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())