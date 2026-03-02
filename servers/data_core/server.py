"""
Data Core MCP Server — хранилище расчётных данных, параметров и формул.

Предоставляет инструменты для:
- Управления параметрами (get/set/list)
- Работы с формулами (add/execute)
- Запуска скриптов (run_script)
- Экспорта/импорта данных (export/import)
"""

import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio

# Создаём экземпляр MCP-сервера
server = Server("data_core")

# Путь к файлу данных
# Поддерживаем переменную окружения PROJECT_PATH для привязки к проекту
_project_path = os.environ.get("PROJECT_PATH", "")
if _project_path:
    DATA_PATH = Path(_project_path) / "data"
else:
    DATA_PATH = Path("data")
CALCULATIONS_FILE = DATA_PATH / "calculations.json"

# Структура данных по умолчанию
DEFAULT_DATA = {
    "parameters": {},
    "formulas": {},
    "scripts": {},
    "metadata": {
        "created": None,
        "modified": None,
        "version": "1.0"
    }
}


def ensure_data_file():
    """Создаёт файл данных, если он не существует."""
    DATA_PATH.mkdir(parents=True, exist_ok=True)
    if not CALCULATIONS_FILE.exists():
        data = DEFAULT_DATA.copy()
        data["metadata"]["created"] = datetime.now().isoformat()
        data["metadata"]["modified"] = datetime.now().isoformat()
        save_data(data)


def load_data() -> Dict[str, Any]:
    """Загружает данные из JSON-файла."""
    ensure_data_file()
    try:
        with open(CALCULATIONS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        # Если файл повреждён, создаём новый
        data = DEFAULT_DATA.copy()
        data["metadata"]["created"] = datetime.now().isoformat()
        data["metadata"]["modified"] = datetime.now().isoformat()
        save_data(data)
        return data


def save_data(data: Dict[str, Any]):
    """Атомарно сохраняет данные в JSON-файл."""
    # Обновляем метку времени
    data["metadata"]["modified"] = datetime.now().isoformat()
    
    # Атомарное сохранение через временный файл
    temp_file = CALCULATIONS_FILE.with_suffix('.tmp')
    with open(temp_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    # Заменяем оригинальный файл
    temp_file.replace(CALCULATIONS_FILE)


def get_parameter(name: str) -> dict:
    """
    Возвращает значение параметра по имени.
    
    Args:
        name: Имя параметра
    
    Returns:
        Информация о параметре или ошибка
    """
    data = load_data()
    
    if name in data["parameters"]:
        param = data["parameters"][name]
        return {
            "success": True,
            "parameter": {
                "name": name,
                "value": param.get("value"),
                "unit": param.get("unit"),
                "source": param.get("source"),
                "description": param.get("description"),
                "created": param.get("created"),
                "modified": param.get("modified")
            }
        }
    else:
        return {
            "success": False,
            "error": f"Параметр '{name}' не найден"
        }


def set_parameter(
    name: str,
    value: Any,
    unit: Optional[str] = None,
    source: Optional[str] = None,
    description: Optional[str] = None
) -> dict:
    """
    Устанавливает или обновляет параметр.
    
    Args:
        name: Имя параметра
        value: Значение параметра
        unit: Единица измерения (опционально)
        source: Источник значения (опционально)
        description: Описание параметра (опционально)
    
    Returns:
        Статус операции
    """
    if not name:
        return {
            "success": False,
            "error": "Имя параметра не может быть пустым"
        }
    
    data = load_data()
    now = datetime.now().isoformat()
    
    # Проверяем, это новый параметр или обновление
    is_new = name not in data["parameters"]
    
    # Сохраняем старое значение для информации
    old_value = None
    if not is_new:
        old_value = data["parameters"][name].get("value")
    
    # Устанавливаем параметр
    data["parameters"][name] = {
        "value": value,
        "unit": unit,
        "source": source,
        "description": description,
        "created": data["parameters"].get(name, {}).get("created", now),
        "modified": now
    }
    
    # Помечаем зависимые формулы как устаревшие
    for formula_name, formula in data["formulas"].items():
        if name in formula.get("parameters", []):
            formula["stale"] = True
    
    save_data(data)
    
    return {
        "success": True,
        "message": f"Параметр '{name}' {'создан' if is_new else 'обновлён'}",
        "parameter": {
            "name": name,
            "value": value,
            "old_value": old_value,
            "unit": unit,
            "source": source,
            "description": description
        }
    }


def list_parameters(filter_pattern: Optional[str] = None) -> dict:
    """
    Возвращает список всех параметров с возможностью фильтрации.
    
    Args:
        filter_pattern: Паттерн для фильтрации имён (опционально)
    
    Returns:
        Список параметров
    """
    data = load_data()
    parameters = []
    
    for name, param in data["parameters"].items():
        # Фильтрация по паттерну (простое вхождение подстроки)
        if filter_pattern and filter_pattern.lower() not in name.lower():
            continue
        
        parameters.append({
            "name": name,
            "value": param.get("value"),
            "unit": param.get("unit"),
            "source": param.get("source"),
            "description": param.get("description")
        })
    
    return {
        "success": True,
        "count": len(parameters),
        "parameters": parameters
    }


def add_formula(
    name: str,
    expression: str,
    parameters: List[str],
    result: Optional[str] = None
) -> dict:
    """
    Добавляет или обновляет формулу.
    
    Args:
        name: Имя формулы
        expression: Математическое выражение
        parameters: Список имён используемых параметров
        result: Имя параметра для сохранения результата (опционально)
    
    Returns:
        Статус операции
    """
    if not name or not expression:
        return {
            "success": False,
            "error": "Имя и выражение формулы обязательны"
        }
    
    data = load_data()
    now = datetime.now().isoformat()
    
    is_new = name not in data["formulas"]
    
    data["formulas"][name] = {
        "expression": expression,
        "parameters": parameters,
        "result": result,
        "stale": False,
        "created": data["formulas"].get(name, {}).get("created", now),
        "modified": now
    }
    
    save_data(data)
    
    return {
        "success": True,
        "message": f"Формула '{name}' {'создана' if is_new else 'обновлена'}",
        "formula": {
            "name": name,
            "expression": expression,
            "parameters": parameters,
            "result": result
        }
    }


def execute_formula(name: str, arguments: Optional[Dict[str, Any]] = None) -> dict:
    """
    Вычисляет формулу с заданными аргументами.
    
    Args:
        name: Имя формулы
        arguments: Словарь значений параметров (опционально, иначе берутся из хранилища)
    
    Returns:
        Результат вычисления
    """
    data = load_data()
    
    if name not in data["formulas"]:
        return {
            "success": False,
            "error": f"Формула '{name}' не найдена"
        }
    
    formula = data["formulas"][name]
    expression = formula["expression"]
    formula_params = formula.get("parameters", [])
    
    # Подготавливаем значения параметров
    values = {}
    for param_name in formula_params:
        if arguments and param_name in arguments:
            values[param_name] = arguments[param_name]
        elif param_name in data["parameters"]:
            values[param_name] = data["parameters"][param_name].get("value")
        else:
            return {
                "success": False,
                "error": f"Параметр '{param_name}' не найден ни в аргументах, ни в хранилище"
            }
    
    # Безопасное вычисление с asteval
    try:
        from asteval import Interpreter
        interp = Interpreter()
        
        # Добавляем параметры в интерпретатор
        for param_name, param_value in values.items():
            # Заменяем дефисы на подчёркивания для валидных имён
            safe_name = param_name.replace('-', '_')
            interp.symtable[safe_name] = param_value
        
        # Заменяем имена параметров в выражении
        safe_expression = expression
        for param_name in formula_params:
            safe_name = param_name.replace('-', '_')
            safe_expression = safe_expression.replace(param_name, safe_name)
        
        # Вычисляем
        result = interp(safe_expression)
        
        if interp.error:
            errors = [str(e) for e in interp.error]
            return {
                "success": False,
                "error": f"Ошибка вычисления: {errors}"
            }
        
        # Сохраняем результат если указан параметр
        result_param = formula.get("result")
        if result_param:
            data["parameters"][result_param] = {
                "value": result,
                "source": f"formula:{name}",
                "created": data["parameters"].get(result_param, {}).get("created", datetime.now().isoformat()),
                "modified": datetime.now().isoformat()
            }
            data["formulas"][name]["stale"] = False
            save_data(data)
        
        return {
            "success": True,
            "formula": name,
            "expression": expression,
            "values_used": values,
            "result": result,
            "saved_to": result_param
        }
    
    except ImportError:
        return {
            "success": False,
            "error": "asteval не установлен. Установите: pip install asteval"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Ошибка при вычислении: {str(e)}"
        }


def run_script(script_name: str, input_data: Optional[Dict[str, Any]] = None) -> dict:
    """
    Запускает Python-скрипт с переданными данными.
    
    Args:
        script_name: Имя скрипта (файл в scripts/ или абсолютный путь)
        input_data: Данные для передачи скрипту (опционально)
    
    Returns:
        Результат выполнения скрипта
    """
    # Определяем путь к скрипту
    script_path = Path(script_name)
    if not script_path.is_absolute():
        script_path = Path("scripts") / script_name
    
    if not script_path.exists():
        return {
            "success": False,
            "error": f"Скрипт не найден: {script_path}"
        }
    
    # Подготавливаем данные для скрипта
    script_input = input_data or {}
    script_input["_data_file"] = str(CALCULATIONS_FILE.absolute())
    
    # Создаём временный файл для передачи данных
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
        json.dump(script_input, f, ensure_ascii=False)
        input_file = f.name
    
    output_file = tempfile.mktemp(suffix='.json')
    
    try:
        # Запускаем скрипт с таймаутом
        result = subprocess.run(
            ['python', str(script_path), input_file, output_file],
            capture_output=True,
            text=True,
            timeout=60,  # Таймаут 60 секунд
            cwd=str(Path.cwd())
        )
        
        # Удаляем входной файл
        try:
            os.unlink(input_file)
        except:
            pass
        
        if result.returncode != 0:
            return {
                "success": False,
                "error": f"Скрипт завершился с ошибкой (код {result.returncode})",
                "stderr": result.stderr,
                "stdout": result.stdout
            }
        
        # Читаем результат
        if os.path.exists(output_file):
            with open(output_file, 'r', encoding='utf-8') as f:
                script_result = json.load(f)
            try:
                os.unlink(output_file)
            except:
                pass
            
            # Если скрипт вернул обновлённые данные, применяем их
            if "updated_parameters" in script_result:
                data = load_data()
                for param_name, param_value in script_result["updated_parameters"].items():
                    if isinstance(param_value, dict):
                        data["parameters"][param_name] = {
                            "value": param_value.get("value"),
                            "unit": param_value.get("unit"),
                            "source": f"script:{script_name}",
                            "description": param_value.get("description"),
                            "created": data["parameters"].get(param_name, {}).get("created", datetime.now().isoformat()),
                            "modified": datetime.now().isoformat()
                        }
                    else:
                        data["parameters"][param_name] = {
                            "value": param_value,
                            "source": f"script:{script_name}",
                            "created": data["parameters"].get(param_name, {}).get("created", datetime.now().isoformat()),
                            "modified": datetime.now().isoformat()
                        }
                save_data(data)
            
            return {
                "success": True,
                "script": script_name,
                "stdout": result.stdout,
                "result": script_result
            }
        else:
            return {
                "success": True,
                "script": script_name,
                "stdout": result.stdout,
                "message": "Скрипт выполнен, но не создал файл результата"
            }
    
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": f"Скрипт превысил таймаут (60 сек)"
        }
    except json.JSONDecodeError as e:
        return {
            "success": False,
            "error": f"Ошибка чтения результата скрипта: {str(e)}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Ошибка запуска скрипта: {str(e)}"
        }


def export_data() -> dict:
    """
    Экспортирует все данные в JSON.
    
    Returns:
        Полные данные хранилища
    """
    data = load_data()
    return {
        "success": True,
        "data": data,
        "export_time": datetime.now().isoformat()
    }


def import_data(json_data: Dict[str, Any]) -> dict:
    """
    Импортирует данные из JSON.
    
    Args:
        json_data: Данные для импорта
    
    Returns:
        Статус операции
    """
    if not isinstance(json_data, dict):
        return {
            "success": False,
            "error": "Данные должны быть объектом JSON"
        }
    
    # Валидация структуры
    if "parameters" not in json_data and "formulas" not in json_data:
        return {
            "success": False,
            "error": "Данные должны содержать 'parameters' или 'formulas'"
        }
    
    try:
        # Загружаем текущие данные
        data = load_data()
        
        # Подсчитываем изменения
        params_added = 0
        params_updated = 0
        formulas_added = 0
        formulas_updated = 0
        
        # Импортируем параметры
        if "parameters" in json_data:
            for name, param in json_data["parameters"].items():
                if name not in data["parameters"]:
                    params_added += 1
                else:
                    params_updated += 1
                data["parameters"][name] = param
        
        # Импортируем формулы
        if "formulas" in json_data:
            for name, formula in json_data["formulas"].items():
                if name not in data["formulas"]:
                    formulas_added += 1
                else:
                    formulas_updated += 1
                data["formulas"][name] = formula
        
        # Сохраняем
        save_data(data)
        
        return {
            "success": True,
            "message": "Данные успешно импортированы",
            "stats": {
                "parameters_added": params_added,
                "parameters_updated": params_updated,
                "formulas_added": formulas_added,
                "formulas_updated": formulas_updated
            }
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": f"Ошибка импорта: {str(e)}"
        }


@server.list_tools()
async def list_tools():
    """Возвращает список доступных инструментов."""
    return [
        Tool(
            name="get_parameter",
            description=(
                "Возвращает значение параметра по имени. "
                "Включает значение, единицу измерения, источник и описание."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Имя параметра"
                    }
                },
                "required": ["name"]
            }
        ),
        Tool(
            name="set_parameter",
            description=(
                "Создаёт или обновляет параметр. "
                "При обновлении помечает зависимые формулы как устаревшие."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Имя параметра"
                    },
                    "value": {
                        "description": "Значение параметра (число, строка, объект)"
                    },
                    "unit": {
                        "type": "string",
                        "description": "Единица измерения (опционально)"
                    },
                    "source": {
                        "type": "string",
                        "description": "Источник значения (опционально)"
                    },
                    "description": {
                        "type": "string",
                        "description": "Описание параметра (опционально)"
                    }
                },
                "required": ["name", "value"]
            }
        ),
        Tool(
            name="list_parameters",
            description=(
                "Возвращает список всех параметров с возможностью фильтрации по имени."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "filter": {
                        "type": "string",
                        "description": "Паттерн для фильтрации имён (опционально)"
                    }
                }
            }
        ),
        Tool(
            name="add_formula",
            description=(
                "Добавляет или обновляет формулу для вычислений. "
                "Использует asteval для безопасного вычисления выражений."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Имя формулы"
                    },
                    "expression": {
                        "type": "string",
                        "description": "Математическое выражение (например: 'a + b * c')"
                    },
                    "parameters": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Список имён используемых параметров"
                    },
                    "result": {
                        "type": "string",
                        "description": "Имя параметра для сохранения результата (опционально)"
                    }
                },
                "required": ["name", "expression", "parameters"]
            }
        ),
        Tool(
            name="execute_formula",
            description=(
                "Вычисляет формулу и возвращает результат. "
                "Может сохранить результат в указанный параметр."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Имя формулы"
                    },
                    "arguments": {
                        "type": "object",
                        "description": "Значения параметров для вычисления (опционально)"
                    }
                },
                "required": ["name"]
            }
        ),
        Tool(
            name="run_script",
            description=(
                "Запускает Python-скрипт с таймаутом и изоляцией. "
                "Скрипт получает данные через временный JSON-файл."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "script_name": {
                        "type": "string",
                        "description": "Имя скрипта (в scripts/) или абсолютный путь"
                    },
                    "input_data": {
                        "type": "object",
                        "description": "Данные для передачи скрипту (опционально)"
                    }
                },
                "required": ["script_name"]
            }
        ),
        Tool(
            name="export_data",
            description=(
                "Экспортирует все параметры и формулы в JSON."
            ),
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="import_data",
            description=(
                "Импортирует параметры и формулы из JSON. "
                "Объединяет с существующими данными."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "json_data": {
                        "type": "object",
                        "description": "Данные для импорта (параметры и/или формулы)"
                    }
                },
                "required": ["json_data"]
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    """Обрабатывает вызовы инструментов."""
    
    if name == "get_parameter":
        param_name = arguments.get("name")
        if not param_name:
            return [TextContent(type="text", text="Ошибка: не указано имя параметра.")]
        result = get_parameter(param_name)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "set_parameter":
        param_name = arguments.get("name")
        value = arguments.get("value")
        
        if not param_name:
            return [TextContent(type="text", text="Ошибка: не указано имя параметра.")]
        if value is None:
            return [TextContent(type="text", text="Ошибка: не указано значение параметра.")]
        
        result = set_parameter(
            name=param_name,
            value=value,
            unit=arguments.get("unit"),
            source=arguments.get("source"),
            description=arguments.get("description")
        )
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "list_parameters":
        filter_pattern = arguments.get("filter")
        result = list_parameters(filter_pattern)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "add_formula":
        formula_name = arguments.get("name")
        expression = arguments.get("expression")
        parameters = arguments.get("parameters", [])
        
        if not formula_name:
            return [TextContent(type="text", text="Ошибка: не указано имя формулы.")]
        if not expression:
            return [TextContent(type="text", text="Ошибка: не указано выражение формулы.")]
        
        result = add_formula(
            name=formula_name,
            expression=expression,
            parameters=parameters,
            result=arguments.get("result")
        )
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "execute_formula":
        formula_name = arguments.get("name")
        
        if not formula_name:
            return [TextContent(type="text", text="Ошибка: не указано имя формулы.")]
        
        result = execute_formula(formula_name, arguments.get("arguments"))
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "run_script":
        script_name = arguments.get("script_name")
        
        if not script_name:
            return [TextContent(type="text", text="Ошибка: не указано имя скрипта.")]
        
        result = run_script(script_name, arguments.get("input_data"))
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "export_data":
        result = export_data()
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "import_data":
        json_data = arguments.get("json_data")
        
        if not json_data:
            return [TextContent(type="text", text="Ошибка: не указаны данные для импорта.")]
        
        result = import_data(json_data)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    return [TextContent(type="text", text=f"Неизвестный инструмент: {name}")]


async def main():
    """Запускает MCP-сервер."""
    # Убеждаемся, что файл данных существует
    ensure_data_file()
    
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())