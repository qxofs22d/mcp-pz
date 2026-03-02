"""
LLM Gateway MCP Server — доступ к внешним LLM через OpenRouter API.

Предоставляет инструменты для:
- Отправки запросов к различным LLM
- Управления моделями
- Логирования запросов через Logger
"""

import json
import os
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio

# Создаём экземпляр MCP-сервера
server = Server("llm_gateway")

# Конфигурация
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "deepseek/deepseek-r1-0528:free"
REQUEST_TIMEOUT = 60
MAX_RETRIES = 3

# Популярные модели OpenRouter
POPULAR_MODELS = [
    {
        "id": "deepseek/deepseek-r1-0528:free",
        "name": "DeepSeek R1 (Free)",
        "description": "Бесплатная модель с хорошим качеством",
        "free": True
    },
    {
        "id": "mistralai/mistral-7b-instruct:free",
        "name": "Mistral 7B Instruct (Free)",
        "description": "Быстрая бесплатная модель",
        "free": True
    },
    {
        "id": "google/gemini-2.0-flash-exp:free",
        "name": "Google Gemini 2.0 Flash (Free)",
        "description": "Быстрая модель от Google",
        "free": True
    },
    {
        "id": "anthropic/claude-3-haiku-20240307",
        "name": "Claude 3 Haiku",
        "description": "Быстрая модель от Anthropic",
        "free": False
    },
    {
        "id": "openai/gpt-4o-2024-08-06",
        "name": "GPT-4o",
        "description": "Флагманская модель OpenAI",
        "free": False
    }
]


class Config:
    """Загрузка конфигурации из .env файла."""
    
    _instance = None
    _api_key = None
    _default_model = DEFAULT_MODEL
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config()
        return cls._instance
    
    def _load_config(self):
        """Загружает конфигурацию из .env файла."""
        # Сначала пробуем переменную окружения
        self._api_key = os.environ.get("OPENROUTER_API_KEY")
        
        # Если нет, пробуем .env файл
        if not self._api_key:
            env_path = Path(".env")
            if env_path.exists():
                try:
                    with open(env_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith("OPENROUTER_API_KEY="):
                                self._api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                                break
                except Exception:
                    pass
    
    @property
    def api_key(self) -> Optional[str]:
        return self._api_key
    
    @property
    def default_model(self) -> str:
        return self._default_model
    
    def set_default_model(self, model: str):
        self._default_model = model


class OpenRouterClient:
    """Асинхронный клиент для OpenRouter API."""
    
    def __init__(self, config: Config):
        self.config = config
        self._session = None
    
    async def _get_session(self):
        """Ленивая инициализация aiohttp сессии."""
        if self._session is None:
            try:
                import aiohttp
                self._session = aiohttp.ClientSession()
            except ImportError:
                raise RuntimeError("aiohttp не установлен. Установите: pip install aiohttp")
        return self._session
    
    async def close(self):
        """Закрывает сессию."""
        if self._session:
            await self._session.close()
            self._session = None
    
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 2000
    ) -> Dict[str, Any]:
        """
        Отправляет запрос к OpenRouter API.
        
        Args:
            messages: Список сообщений [{"role": "user", "content": "..."}]
            model: ID модели
            temperature: Температура генерации
            max_tokens: Максимум токенов в ответе
        
        Returns:
            Ответ API
        """
        import aiohttp
        
        if not self.config.api_key:
            return {
                "success": False,
                "error": "API ключ не настроен. Установите OPENROUTER_API_KEY в .env файле или переменной окружения."
            }
        
        session = await self._get_session()
        
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://mcp-pz.local",
            "X-Title": "MCP-PZ LLM Gateway"
        }
        
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        url = f"{OPENROUTER_BASE_URL}/chat/completions"
        
        # Retry logic
        for attempt in range(MAX_RETRIES):
            try:
                async with session.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "success": True,
                            "response": data
                        }
                    elif response.status == 401:
                        return {
                            "success": False,
                            "error": "Неверный API ключ. Проверьте OPENROUTER_API_KEY."
                        }
                    elif response.status == 429:
                        return {
                            "success": False,
                            "error": "Превышен лимит запросов. Попробуйте позже."
                        }
                    else:
                        error_text = await response.text()
                        if attempt < MAX_RETRIES - 1:
                            await asyncio.sleep(2 ** attempt)  # Exponential backoff
                            continue
                        return {
                            "success": False,
                            "error": f"Ошибка API (статус {response.status}): {error_text}"
                        }
            
            except asyncio.TimeoutError:
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                return {
                    "success": False,
                    "error": f"Таймаут запроса ({REQUEST_TIMEOUT} сек)"
                }
            
            except aiohttp.ClientError as e:
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                return {
                    "success": False,
                    "error": f"Ошибка сети: {str(e)}"
                }
        
        return {
            "success": False,
            "error": "Не удалось выполнить запрос после нескольких попыток"
        }


# Глобальные экземпляры
config = Config()
client = OpenRouterClient(config)


async def log_request(prompt: str, model: str, response_length: int, success: bool):
    """Логирует запрос через Logger."""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from logger.server import write_log_entry
        
        write_log_entry(
            role="system",
            content=f"LLM Gateway запрос: model={model}, prompt_length={len(prompt)}, response_length={response_length}, success={success}",
            entry_type="expert",
            metadata={
                "model": model,
                "prompt_preview": prompt[:200] if len(prompt) > 200 else prompt,
                "response_length": response_length,
                "success": success
            }
        )
    except Exception:
        pass  # Не критично, если логирование не удалось


async def ask(
    prompt: str,
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 2000
) -> dict:
    """
    Отправляет запрос к LLM.
    
    Args:
        prompt: Текст запроса
        model: ID модели (опционально)
        temperature: Температура генерации
        max_tokens: Максимум токенов в ответе
    
    Returns:
        Ответ модели
    """
    if not prompt:
        return {
            "success": False,
            "error": "Запрос не может быть пустым"
        }
    
    model = model or config.default_model
    
    messages = [{"role": "user", "content": prompt}]
    
    result = await client.chat_completion(
        messages=messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens
    )
    
    if result["success"]:
        response_data = result["response"]
        choices = response_data.get("choices", [])
        
        if choices:
            content = choices[0].get("message", {}).get("content", "")
            response_length = len(content)
            
            # Логируем успешный запрос
            await log_request(prompt, model, response_length, True)
            
            return {
                "success": True,
                "model": model,
                "content": content,
                "usage": response_data.get("usage", {}),
                "finish_reason": choices[0].get("finish_reason")
            }
        else:
            return {
                "success": False,
                "error": "Пустой ответ от модели"
            }
    else:
        # Логируем ошибку
        await log_request(prompt, model, 0, False)
        return result


async def ask_with_context(
    prompt: str,
    context: str,
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 2000
) -> dict:
    """
    Отправляет запрос с контекстом.
    
    Args:
        prompt: Текст запроса
        context: Контекстная информация
        model: ID модели (опционально)
        temperature: Температура генерации
        max_tokens: Максимум токенов в ответе
    
    Returns:
        Ответ модели
    """
    if not prompt:
        return {
            "success": False,
            "error": "Запрос не может быть пустым"
        }
    
    model = model or config.default_model
    
    # Формируем сообщения с контекстом
    messages = []
    
    if context:
        messages.append({
            "role": "system",
            "content": f"Контекст для ответа:\n{context}"
        })
    
    messages.append({"role": "user", "content": prompt})
    
    result = await client.chat_completion(
        messages=messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens
    )
    
    if result["success"]:
        response_data = result["response"]
        choices = response_data.get("choices", [])
        
        if choices:
            content = choices[0].get("message", {}).get("content", "")
            response_length = len(content)
            
            # Логируем успешный запрос
            await log_request(prompt, model, response_length, True)
            
            return {
                "success": True,
                "model": model,
                "content": content,
                "usage": response_data.get("usage", {}),
                "finish_reason": choices[0].get("finish_reason"),
                "context_used": True
            }
        else:
            return {
                "success": False,
                "error": "Пустой ответ от модели"
            }
    else:
        # Логируем ошибку
        await log_request(prompt, model, 0, False)
        return result


def list_models() -> dict:
    """
    Возвращает список доступных моделей.
    
    Returns:
        Список моделей с описаниями
    """
    return {
        "success": True,
        "models": POPULAR_MODELS,
        "default_model": config.default_model,
        "api_key_configured": config.api_key is not None
    }


def set_default_model(model: str) -> dict:
    """
    Устанавливает модель по умолчанию.
    
    Args:
        model: ID модели
    
    Returns:
        Статус операции
    """
    # Проверяем, что модель в списке
    model_ids = [m["id"] for m in POPULAR_MODELS]
    
    config.set_default_model(model)
    
    return {
        "success": True,
        "message": f"Модель по умолчанию установлена: {model}",
        "default_model": model
    }


@server.list_tools()
async def list_tools():
    """Возвращает список доступных инструментов."""
    return [
        Tool(
            name="ask",
            description=(
                "Отправляет запрос к LLM через OpenRouter API. "
                "Использует модель по умолчанию или указанную."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Текст запроса"
                    },
                    "model": {
                        "type": "string",
                        "description": f"ID модели (по умолчанию: {DEFAULT_MODEL})"
                    },
                    "temperature": {
                        "type": "number",
                        "description": "Температура генерации (0.0-2.0, по умолчанию 0.7)",
                        "default": 0.7
                    },
                    "max_tokens": {
                        "type": "integer",
                        "description": "Максимум токенов в ответе (по умолчанию 2000)",
                        "default": 2000
                    }
                },
                "required": ["prompt"]
            }
        ),
        Tool(
            name="ask_with_context",
            description=(
                "Отправляет запрос к LLM с дополнительным контекстом. "
                "Контекст добавляется как system-сообщение."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Текст запроса"
                    },
                    "context": {
                        "type": "string",
                        "description": "Контекстная информация"
                    },
                    "model": {
                        "type": "string",
                        "description": f"ID модели (по умолчанию: {DEFAULT_MODEL})"
                    },
                    "temperature": {
                        "type": "number",
                        "description": "Температура генерации (0.0-2.0)",
                        "default": 0.7
                    },
                    "max_tokens": {
                        "type": "integer",
                        "description": "Максимум токенов в ответе",
                        "default": 2000
                    }
                },
                "required": ["prompt"]
            }
        ),
        Tool(
            name="list_models",
            description=(
                "Возвращает список доступных моделей OpenRouter. "
                "Показывает популярные бесплатные и платные модели."
            ),
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="set_default_model",
            description=(
                "Устанавливает модель по умолчанию для последующих запросов."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "model": {
                        "type": "string",
                        "description": "ID модели"
                    }
                },
                "required": ["model"]
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    """Обрабатывает вызовы инструментов."""
    
    if name == "ask":
        prompt = arguments.get("prompt")
        
        if not prompt:
            return [TextContent(type="text", text="Ошибка: не указан запрос.")]
        
        result = await ask(
            prompt=prompt,
            model=arguments.get("model"),
            temperature=arguments.get("temperature", 0.7),
            max_tokens=arguments.get("max_tokens", 2000)
        )
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "ask_with_context":
        prompt = arguments.get("prompt")
        context = arguments.get("context", "")
        
        if not prompt:
            return [TextContent(type="text", text="Ошибка: не указан запрос.")]
        
        result = await ask_with_context(
            prompt=prompt,
            context=context,
            model=arguments.get("model"),
            temperature=arguments.get("temperature", 0.7),
            max_tokens=arguments.get("max_tokens", 2000)
        )
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "list_models":
        result = list_models()
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "set_default_model":
        model = arguments.get("model")
        
        if not model:
            return [TextContent(type="text", text="Ошибка: не указана модель.")]
        
        result = set_default_model(model)
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