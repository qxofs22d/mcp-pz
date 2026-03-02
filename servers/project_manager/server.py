"""
Project Manager MCP Server — управление проектами, файлами и состоянием.

Обеспечивает единую точку управления проектом: создание папок, 
копирование PDF, сохранение прогресса, доступ к файлам и метаданным.

Структура проекта:
    project/
    ├── .pzproject/          # маркер и настройки проекта
    │   ├── config.json      # конфигурация (модель, шаблон)
    │   └── skills/          # локальные скиллы (опционально)
    ├── state.json           # рабочее состояние
    ├── pdf/                 # PDF-документы
    ├── data/                # данные расчётов
    ├── output/              # результаты
    ├── vector_index/        # индекс векторов
    └── .dialogue/           # логи диалогов
"""

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Any, List, Dict

from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio

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
        config: Конфигурация проекта из .pzproject/config.json
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
    
    DEFAULT_CONFIG = {
        "project_name": "",
        "model": "deepseek/deepseek-r1-0528:free",
        "template": "default",
        "description": "",
        "created_at": None,
        "updated_at": None
    }
    
    def __init__(self, project_path: str):
        """
        Инициализация менеджера проекта.
        
        Args:
            project_path: Путь к папке проекта
        """
        self.path = Path(project_path).resolve()
        self.config = self._load_config()
        self.state = self._load_state()
    
    def _pzproject_dir(self) -> Path:
        """Возвращает путь к папке .pzproject."""
        return self.path / ".pzproject"
    
    def _config_file(self) -> Path:
        """Возвращает путь к файлу конфигурации."""
        return self._pzproject_dir() / "config.json"
    
    def _state_file(self) -> Path:
        """Возвращает путь к файлу состояния."""
        return self.path / "state.json"
    
    def _dialogue_dir(self) -> Path:
        """Возвращает путь к папке диалогов."""
        return self.path / ".dialogue"
    
    def _vector_index_dir(self) -> Path:
        """Возвращает путь к папке векторного индекса."""
        return self.path / "vector_index"
    
    def _load_config(self) -> dict:
        """Загружает конфигурацию из .pzproject/config.json."""
        config_file = self._config_file()
        if config_file.exists():
            with open(config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return self.DEFAULT_CONFIG.copy()
    
    def _save_config(self):
        """Сохраняет конфигурацию в .pzproject/config.json."""
        self.config["updated_at"] = datetime.now().isoformat()
        config_file = self._config_file()
        config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)
    
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
            True если есть .pzproject/ или state.json
        """
        return self._pzproject_dir().exists() or self._state_file().exists()
    
    def init_project(self, description: str = "", model: str = "", template: str = "") -> dict:
        """
        Инициализирует новый проект ПЗ с полной структурой.
        
        Создаёт:
        - .pzproject/config.json — конфигурация
        - .pzproject/skills/ — папка для локальных скиллов
        - state.json — рабочее состояние
        - pdf/, data/, output/ — папки для данных
        - vector_index/ — папка для векторного индекса
        - .dialogue/ — папка для логов диалогов
        
        Args:
            description: Описание проекта
            model: Модель LLM по умолчанию
            template: Шаблон проекта
        
        Returns:
            Статус операции
        """
        # Создаём структуру папок
        (self._pzproject_dir() / "skills").mkdir(parents=True, exist_ok=True)
        (self.path / "pdf").mkdir(parents=True, exist_ok=True)
        (self.path / "data").mkdir(parents=True, exist_ok=True)
        (self.path / "output").mkdir(parents=True, exist_ok=True)
        (self._vector_index_dir()).mkdir(parents=True, exist_ok=True)
        (self._dialogue_dir()).mkdir(parents=True, exist_ok=True)
        
        # Инициализируем конфигурацию
        self.config = self.DEFAULT_CONFIG.copy()
        self.config["project_name"] = self.path.name
        self.config["description"] = description
        if model:
            self.config["model"] = model
        if template:
            self.config["template"] = template
        self.config["created_at"] = datetime.now().isoformat()
        self._save_config()
        
        # Инициализируем состояние
        self.state = self.DEFAULT_STATE.copy()
        self.state["project_name"] = self.path.name
        self.state["created_at"] = datetime.now().isoformat()
        self._save_state()
        
        return {
            "success": True,
            "message": f"Проект ПЗ инициализирован: {self.path}",
            "project_name": self.config["project_name"],
            "config": self.config,
            "structure": {
                ".pzproject/": "конфигурация и скиллы",
                "state.json": "рабочее состояние",
                "pdf/": "PDF-документы",
                "data/": "данные расчётов",
                "output/": "результаты",
                "vector_index/": "векторный индекс",
                ".dialogue/": "логи диалогов"
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
                "suggestion": "Создайте новый проект с помощью create_project"
            }
        
        if not self._state_file().exists():
            return {
                "success": False,
                "error": "Файл state.json не найден",
                "suggestion": "Возможно, это не папка проекта. Создайте новый проект."
            }
        
        self.state = self._load_state()
        self.config = self._load_config()
        return {
            "success": True,
            "message": f"Проект загружен: {self.state.get('project_name', self.path.name)}",
            "state": self.state,
            "config": self.config if self._pzproject_dir().exists() else None
        }
    
    def detect_project(self) -> dict:
        """
        Определяет, является ли текущая папка проектом ПЗ.
        
        Returns:
            Информация о проекте или предложение инициализировать
        """
        has_pzproject = self._pzproject_dir().exists()
        has_state = self._state_file().exists()
        
        if has_pzproject:
            # Полноценный проект ПЗ с конфигурацией
            return {
                "success": True,
                "is_pzproject": True,
                "type": "full",
                "message": "Обнаружен проект ПЗ с конфигурацией",
                "project_path": str(self.path),
                "config": self.config,
                "state": self.state
            }
        elif has_state:
            # Старый формат проекта (только state.json)
            return {
                "success": True,
                "is_pzproject": True,
                "type": "legacy",
                "message": "Обнаружен проект старого формата (только state.json)",
                "project_path": str(self.path),
                "state": self.state,
                "suggestion": "Рекомендуется выполнить init_project для перехода на новый формат"
            }
        else:
            # Не проект ПЗ
            return {
                "success": True,
                "is_pzproject": False,
                "type": None,
                "message": "Папка не является проектом ПЗ",
                "project_path": str(self.path),
                "suggestion": "Используйте init_project для создания нового проекта"
            }
    
    def get_config(self) -> dict:
        """
        Возвращает конфигурацию проекта.
        
        Returns:
            Конфигурация проекта
        """
        return {
            "success": True,
            "project_path": str(self.path),
            "config": self.config
        }
    
    def update_config(self, updates: dict) -> dict:
        """
        Обновляет конфигурацию проекта.
        
        Args:
            updates: Словарь с обновлениями
        
        Returns:
            Статус операции
        """
        for key, value in updates.items():
            if key in self.DEFAULT_CONFIG:
                self.config[key] = value
        
        self._save_config()
        
        return {
            "success": True,
            "message": "Конфигурация обновлена",
            "config": self.config
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
        
        # Проверка наличия системного промпта
        system_prompt_path = self._pzproject_dir() / "system_prompt.md"
        system_prompt_exists = system_prompt_path.exists()
        
        return {
            "success": True,
            "project_path": str(self.path),
            "project_name": self.state.get("project_name", self.path.name),
            # Ключевые поля из config
            "model": self.config.get("model"),
            "template": self.config.get("template"),
            "description": self.config.get("description"),
            # Данные из state
            "pdfs": pdfs,
            "sections": sections,
            "metadata": self.state.get("metadata", {}),
            # Системный промпт
            "system_prompt_exists": system_prompt_exists,
            "system_prompt_path": str(system_prompt_path) if system_prompt_exists else None,
            # Полная конфигурация
            "config": self.config,
            "paths": {
                "pdf": str(self.path / "pdf"),
                "data": str(self.path / "data"),
                "output": str(self.path / "output"),
                "vector_index": str(self._vector_index_dir()),
                "dialogue": str(self._dialogue_dir()),
                "config": str(self._config_file()),
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


@server.list_tools()
async def list_tools():
    """Возвращает список доступных инструментов."""
    return [
        Tool(
            name="init_project",
            description="Инициализирует новый проект ПЗ с полной структурой (.pzproject/, state.json, pdf/, data/, output/, vector_index/, .dialogue/).",
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
                    },
                    "model": {
                        "type": "string",
                        "description": "Модель LLM по умолчанию (опционально)"
                    },
                    "template": {
                        "type": "string",
                        "description": "Шаблон проекта (опционально)"
                    }
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="detect_project",
            description="Определяет, является ли указанная папка проектом ПЗ. Возвращает тип проекта (full/legacy/none).",
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
            name="create_project",
            description="Создаёт новый проект в указанной папке с подкаталогами pdf, data, output и файлом state.json (старый формат).",
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
            name="load_project",
            description="Загружает существующий проект из указанной папки, восстанавливая состояние из state.json и конфигурацию из .pzproject/.",
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
            description="Возвращает полную информацию о проекте: пути, статистика, конфигурация.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="get_config",
            description="Возвращает конфигурацию проекта из .pzproject/config.json.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="update_config",
            description="Обновляет конфигурацию проекта (модель, шаблон, описание).",
            inputSchema={
                "type": "object",
                "properties": {
                    "updates": {
                        "type": "object",
                        "description": "Словарь с обновлениями конфигурации",
                        "additionalProperties": True
                    }
                },
                "required": ["updates"]
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
            description=arguments.get("description", ""),
            model=arguments.get("model", ""),
            template=arguments.get("template", "")
        )
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "detect_project":
        project_path = arguments.get("path")
        if not project_path:
            return [TextContent(type="text", text="Ошибка: не указан путь к папке.")]
        
        project = ProjectManager(project_path)
        result = project.detect_project()
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "create_project":
        project_path = arguments.get("path")
        if not project_path:
            return [TextContent(type="text", text="Ошибка: не указан путь к проекту.")]
        
        _current_project = ProjectManager(project_path)
        result = _current_project.create_project()
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
    
    elif name == "get_config":
        if not _current_project:
            return [TextContent(type="text", text="Ошибка: проект не загружен.")]
        
        result = _current_project.get_config()
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "update_config":
        if not _current_project:
            return [TextContent(type="text", text="Ошибка: проект не загружен.")]
        
        updates = arguments.get("updates", {})
        result = _current_project.update_config(updates)
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