"""
Logger MCP Server — модуль логирования диалогов в JSONL.

Записывает сообщения диалога в файл .dialogue/dialogue.jsonl для 
последующего анализа и индексации.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio

# Создаём экземпляр MCP-сервера
server = Server("logger")

# Путь к файлу лога диалогов
# Поддерживаем переменную окружения PROJECT_PATH для привязки к проекту
_project_path = os.environ.get("PROJECT_PATH", "")
if _project_path:
    DIALOGUE_DIR = Path(_project_path) / ".dialogue"
else:
    DIALOGUE_DIR = Path(".dialogue")
DIALOGUE_FILE = DIALOGUE_DIR / "dialogue.jsonl"


def ensure_dialogue_dir():
    """Создаёт папку .dialogue, если её нет."""
    DIALOGUE_DIR.mkdir(parents=True, exist_ok=True)


def write_log_entry(
    role: str, 
    msg_type: str, 
    content: str, 
    metadata: Optional[dict] = None
) -> dict:
    """
    Записывает сообщение в файл лога.
    
    Args:
        role: Роль отправителя ("user" или "assistant")
        msg_type: Тип сообщения ("regular", "expert", "system")
        content: Текст сообщения
        metadata: Опциональные метаданные (словарь)
    
    Returns:
        Записанный объект (словарь)
    """
    ensure_dialogue_dir()
    
    entry = {
        "timestamp": datetime.now().isoformat(),
        "role": role,
        "type": msg_type,
        "content": content,
    }
    
    if metadata:
        entry["metadata"] = metadata
    
    with open(DIALOGUE_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    
    return entry


@server.list_tools()
async def list_tools():
    """Возвращает список доступных инструментов."""
    return [
        Tool(
            name="log",
            description=(
                "Записывает сообщение диалога в файл .dialogue/dialogue.jsonl. "
                "Поля: timestamp (ISO формат, добавляется автоматически), "
                "role ('user' или 'assistant'), type ('regular', 'expert', 'system'), "
                "content (текст сообщения), metadata (опционально, JSON-объект)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "role": {
                        "type": "string",
                        "enum": ["user", "assistant"],
                        "description": "Роль отправителя сообщения"
                    },
                    "type": {
                        "type": "string",
                        "enum": ["regular", "expert", "system"],
                        "description": "Тип сообщения"
                    },
                    "content": {
                        "type": "string",
                        "description": "Текст сообщения"
                    },
                    "metadata": {
                        "type": "object",
                        "description": "Опциональные метаданные (JSON-объект)",
                        "additionalProperties": True
                    }
                },
                "required": ["role", "type", "content"]
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    """Обрабатывает вызовы инструментов."""
    if name == "log":
        role = arguments.get("role")
        msg_type = arguments.get("type")
        content = arguments.get("content")
        metadata = arguments.get("metadata")
        
        if not role or not msg_type or not content:
            return [TextContent(
                type="text",
                text="Ошибка: обязательные поля role, type и content должны быть заполнены."
            )]
        
        entry = write_log_entry(role, msg_type, content, metadata)
        
        return [TextContent(
            type="text",
            text=f"Записано в лог: timestamp={entry['timestamp']}, role={role}, type={msg_type}"
        )]
    
    return [TextContent(
        type="text",
        text=f"Неизвестный инструмент: {name}"
    )]


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