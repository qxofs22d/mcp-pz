"""
PDF Decomposer MCP Server — анализ и декомпозиция PDF-файлов.

Извлекает:
- Иерархию разделов
- Таблицы
- Формулы
- Названия чертежей
"""

import json
import os
import re
import hashlib
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio

# Создаём экземпляр MCP-сервера
server = Server("pdf_decomposer")

# Папка для кэша
# Поддерживаем переменную окружения PROJECT_PATH для привязки к проекту
_project_path = os.environ.get("PROJECT_PATH", "")
if _project_path:
    CACHE_DIR = Path(_project_path) / "pdf_cache"
else:
    CACHE_DIR = Path("pdf_cache")

# Ключевые слова для поиска чертежей
DRAWING_KEYWORDS = [
    "чертёж", "чертеж", "лист", "формат", "масштаб",
    "вид", "разрез", "сечение", "план", "фасад",
    "схема", "узел", "деталь", "спецификация"
]

# Паттерны для формул
FORMULA_PATTERNS = [
    r'[\w\s]+\s*=\s*[\w\s\+\-\*\/\(\)\.\d]+',  # a = b + c
    r'[\d\.\,]+\s*[\+\-\*\/]\s*[\d\.\,]+\s*=',  # расчёты
    r'расч[ёе]т',  # слово "расчёт"
    r'формула',  # слово "формула"
]


def ensure_cache_dir():
    """Создаёт папку для кэша."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get_cache_path(pdf_path: Path) -> Path:
    """Возвращает путь к кэш-файлу для PDF."""
    ensure_cache_dir()
    # Используем хэш от полного пути для уникальности
    path_hash = hashlib.md5(str(pdf_path.absolute()).encode()).hexdigest()[:8]
    cache_name = f"{pdf_path.stem}_{path_hash}.json"
    return CACHE_DIR / cache_name


def load_cache(pdf_path: Path) -> Optional[Dict[str, Any]]:
    """Загружает кэшированный результат если он существует."""
    cache_path = get_cache_path(pdf_path)
    if cache_path.exists():
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                cached = json.load(f)
                # Проверяем, что PDF не изменился
                if cached.get("source_file") == str(pdf_path):
                    return cached
        except (json.JSONDecodeError, KeyError):
            pass
    return None


def save_cache(pdf_path: Path, data: Dict[str, Any]):
    """Сохраняет результат в кэш."""
    cache_path = get_cache_path(pdf_path)
    data["cached_at"] = datetime.now().isoformat()
    data["source_file"] = str(pdf_path)
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def extract_text_with_fitz(pdf_path: Path) -> Dict[int, List[Dict[str, Any]]]:
    """
    Извлекает текстовые блоки из PDF с помощью PyMuPDF.
    
    Returns:
        Словарь {page_num: [blocks]}
    """
    import fitz
    
    doc = fitz.open(str(pdf_path))
    pages_content = {}
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
        
        page_blocks = []
        for block in blocks:
            if block.get("type") == 0:  # Текстовый блок
                # Собираем текст из линий
                text = ""
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text += span.get("text", "")
                    text += "\n"
                
                text = text.strip()
                if text:
                    page_blocks.append({
                        "type": "text",
                        "text": text,
                        "bbox": block.get("bbox"),
                        "page": page_num + 1
                    })
        
        pages_content[page_num + 1] = page_blocks
    
    doc.close()
    return pages_content


def extract_tables_with_pdfplumber(pdf_path: Path, pages: Optional[List[int]] = None) -> List[Dict[str, Any]]:
    """
    Извлекает таблицы из PDF с помощью pdfplumber.
    
    Args:
        pdf_path: Путь к PDF
        pages: Список номеров страниц (опционально)
    
    Returns:
        Список таблиц
    """
    import pdfplumber
    
    tables = []
    
    with pdfplumber.open(str(pdf_path)) as pdf:
        page_nums = pages if pages else range(1, len(pdf.pages) + 1)
        
        for page_num in page_nums:
            if page_num < 1 or page_num > len(pdf.pages):
                continue
            
            page = pdf.pages[page_num - 1]
            page_tables = page.extract_tables()
            
            for table_idx, table in enumerate(page_tables):
                if table and len(table) > 0:
                    # Очищаем таблицу от None
                    cleaned_table = []
                    for row in table:
                        cleaned_row = [cell if cell else "" for cell in row]
                        cleaned_table.append(cleaned_row)
                    
                    tables.append({
                        "type": "table",
                        "page": page_num,
                        "table_index": table_idx,
                        "rows": len(cleaned_table),
                        "columns": len(cleaned_table[0]) if cleaned_table else 0,
                        "data": cleaned_table
                    })
    
    return tables


def detect_formulas(text: str) -> List[Dict[str, Any]]:
    """
    Обнаруживает формулы в тексте по эвристикам.
    
    Args:
        text: Текст для анализа
    
    Returns:
        Список найденных формул
    """
    formulas = []
    lines = text.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Проверяем паттерны формул
        for pattern in FORMULA_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                # Проверяем, что строка не слишком длинная (не весь абзац)
                if len(line) < 200:
                    formulas.append({
                        "type": "formula",
                        "text": line,
                        "pattern_matched": pattern
                    })
                    break
    
    return formulas


def detect_drawings(text: str) -> List[Dict[str, Any]]:
    """
    Обнаруживает названия чертежей по ключевым словам.
    
    Args:
        text: Текст для анализа
    
    Returns:
        Список найденных упоминаний чертежей
    """
    drawings = []
    lines = text.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Проверяем ключевые слова
        for keyword in DRAWING_KEYWORDS:
            if keyword.lower() in line.lower():
                drawings.append({
                    "type": "drawing_reference",
                    "text": line,
                    "keyword": keyword
                })
                break
    
    return drawings


def extract_toc(pdf_path: Path) -> List[Dict[str, Any]]:
    """
    Извлекает оглавление из PDF.
    
    Args:
        pdf_path: Путь к PDF
    
    Returns:
        Список разделов из оглавления
    """
    import fitz
    
    doc = fitz.open(str(pdf_path))
    toc = doc.get_toc()
    doc.close()
    
    sections = []
    for item in toc:
        level, title, page = item
        sections.append({
            "level": level,
            "title": title,
            "page": page
        })
    
    return sections


def detect_sections_by_heuristics(pages_content: Dict[int, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """
    Определяет разделы по эвристикам (если нет оглавления).
    
    Ищет строки, похожие на заголовки:
    - Короткие строки
    - Начинаются с цифры и точки
    - Содержат ключевые слова ("раздел", "глава", "приложение")
    """
    sections = []
    section_num = 0
    
    # Паттерны заголовков
    header_patterns = [
        r'^\d+[\.\)]\s*.+',  # "1. Введение" или "1) Введение"
        r'^[А-ЯЁ\s]+$',  # Все заглавные
        r'^(раздел|глава|приложение)',  # Ключевые слова
        r'^(введение|заключение|содержание|литература)',  # Типовые разделы
    ]
    
    for page_num, blocks in sorted(pages_content.items()):
        for block in blocks:
            text = block.get("text", "")
            if not text:
                continue
            
            # Берём первую строку блока
            first_line = text.split('\n')[0].strip()
            
            # Проверяем, похоже ли на заголовок
            if len(first_line) < 100:  # Заголовки обычно короткие
                for pattern in header_patterns:
                    if re.match(pattern, first_line, re.IGNORECASE):
                        section_num += 1
                        sections.append({
                            "level": 1,
                            "title": first_line,
                            "page": page_num,
                            "type": "auto_detected"
                        })
                        break
    
    return sections


def classify_blocks(pages_content: Dict[int, List[Dict[str, Any]]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Классифицирует блоки по типам: текст, таблица, формула, расчётный блок.
    
    Returns:
        Словарь с классифицированными блоками
    """
    classified = {
        "text": [],
        "table": [],
        "formula": [],
        "calculation_block": []
    }
    
    for page_num, blocks in sorted(pages_content.items()):
        for block in blocks:
            text = block.get("text", "")
            if not text:
                continue
            
            # Проверяем на формулы
            formulas = detect_formulas(text)
            if formulas:
                block["contains_formulas"] = True
                block["formulas"] = formulas
            
            # Проверяем на расчётный блок
            # (содержит числа, знаки операций, возможно "=")
            calc_pattern = r'[\d\.\,]+\s*[\+\-\*\/\=]\s*[\d\.\,]+'
            calc_matches = re.findall(calc_pattern, text)
            if len(calc_matches) > 3:  # Несколько расчётов в блоке
                block["type"] = "calculation_block"
                block["calculations"] = calc_matches
                classified["calculation_block"].append(block)
            elif formulas:
                block["type"] = "formula_block"
                classified["formula"].append(block)
            else:
                classified["text"].append(block)
    
    return classified


def decompose_pdf(pdf_path: str) -> dict:
    """
    Полная декомпозиция PDF-файла.
    
    Args:
        pdf_path: Путь к PDF-файлу
    
    Returns:
        Структурированный JSON с результатами анализа
    """
    path = Path(pdf_path)
    
    if not path.exists():
        return {
            "success": False,
            "error": f"Файл не найден: {pdf_path}"
        }
    
    if not path.suffix.lower() == '.pdf':
        return {
            "success": False,
            "error": f"Файл не является PDF: {pdf_path}"
        }
    
    # Проверяем кэш
    cached = load_cache(path)
    if cached:
        return {
            "success": True,
            "source": "cache",
            "data": cached
        }
    
    try:
        # Извлекаем текст
        pages_content = extract_text_with_fitz(path)
        
        # Извлекаем оглавление
        toc_sections = extract_toc(path)
        
        # Если оглавления нет, определяем разделы по эвристикам
        if not toc_sections:
            toc_sections = detect_sections_by_heuristics(pages_content)
        
        # Классифицируем блоки
        classified = classify_blocks(pages_content)
        
        # Извлекаем таблицы
        tables = extract_tables_with_pdfplumber(path)
        
        # Собираем формулы из всех блоков
        all_formulas = []
        for block in classified.get("formula", []):
            for formula in block.get("formulas", []):
                formula["page"] = block.get("page")
                all_formulas.append(formula)
        
        # Ищем упоминания чертежей
        all_drawings = []
        for page_num, blocks in pages_content.items():
            for block in blocks:
                drawings = detect_drawings(block.get("text", ""))
                for drawing in drawings:
                    drawing["page"] = page_num
                    all_drawings.append(drawing)
        
        # Формируем результат
        result = {
            "file_name": path.name,
            "file_path": str(path.absolute()),
            "pages_count": len(pages_content),
            "sections": toc_sections,
            "standalone_tables": [
                {
                    "page": t["page"],
                    "rows": t["rows"],
                    "columns": t["columns"],
                    "preview": t["data"][:3] if t["data"] else []  # Первые 3 строки
                }
                for t in tables
            ],
            "tables_full": tables,
            "formulas": all_formulas[:50],  # Ограничиваем количество
            "drawings": all_drawings[:50],
            "statistics": {
                "text_blocks": len(classified["text"]),
                "formula_blocks": len(classified["formula"]),
                "calculation_blocks": len(classified["calculation_block"]),
                "tables": len(tables),
                "total_formulas": len(all_formulas),
                "total_drawings": len(all_drawings)
            },
            "classified_blocks": {
                "text_count": len(classified["text"]),
                "formula_count": len(classified["formula"]),
                "calculation_count": len(classified["calculation_block"])
            }
        }
        
        # Сохраняем в кэш
        save_cache(path, result)
        
        return {
            "success": True,
            "source": "fresh",
            "data": result
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": f"Ошибка при обработке PDF: {str(e)}"
        }


def extract_tables(pdf_path: str, pages: Optional[List[int]] = None) -> dict:
    """
    Извлекает таблицы из PDF.
    
    Args:
        pdf_path: Путь к PDF
        pages: Список номеров страниц (опционально)
    
    Returns:
        Список таблиц
    """
    path = Path(pdf_path)
    
    if not path.exists():
        return {
            "success": False,
            "error": f"Файл не найден: {pdf_path}"
        }
    
    try:
        tables = extract_tables_with_pdfplumber(path, pages)
        
        return {
            "success": True,
            "tables_count": len(tables),
            "tables": tables
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": f"Ошибка при извлечении таблиц: {str(e)}"
        }


def extract_formulas(pdf_path: str) -> dict:
    """
    Извлекает формулы из PDF.
    
    Args:
        pdf_path: Путь к PDF
    
    Returns:
        Список найденных формул
    """
    path = Path(pdf_path)
    
    if not path.exists():
        return {
            "success": False,
            "error": f"Файл не найден: {pdf_path}"
        }
    
    try:
        pages_content = extract_text_with_fitz(path)
        
        all_formulas = []
        for page_num, blocks in pages_content.items():
            for block in blocks:
                formulas = detect_formulas(block.get("text", ""))
                for formula in formulas:
                    formula["page"] = page_num
                    all_formulas.append(formula)
        
        return {
            "success": True,
            "formulas_count": len(all_formulas),
            "formulas": all_formulas[:100]  # Ограничиваем
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": f"Ошибка при извлечении формул: {str(e)}"
        }


def get_structure(pdf_path: str) -> dict:
    """
    Возвращает иерархию разделов PDF.
    
    Args:
        pdf_path: Путь к PDF
    
    Returns:
        Структура разделов
    """
    path = Path(pdf_path)
    
    if not path.exists():
        return {
            "success": False,
            "error": f"Файл не найден: {pdf_path}"
        }
    
    try:
        # Извлекаем оглавление
        toc_sections = extract_toc(path)
        
        # Если оглавления нет, определяем по эвристикам
        if not toc_sections:
            pages_content = extract_text_with_fitz(path)
            toc_sections = detect_sections_by_heuristics(pages_content)
        
        return {
            "success": True,
            "file_name": path.name,
            "sections_count": len(toc_sections),
            "sections": toc_sections,
            "has_toc": len([s for s in toc_sections if s.get("type") != "auto_detected"]) > 0
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": f"Ошибка при извлечении структуры: {str(e)}"
        }


@server.list_tools()
async def list_tools():
    """Возвращает список доступных инструментов."""
    return [
        Tool(
            name="decompose_pdf",
            description=(
                "Полная декомпозиция PDF-файла. "
                "Извлекает структуру разделов, таблицы, формулы и названия чертежей. "
                "Результат кэшируется в папке pdf_cache/."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pdf_path": {
                        "type": "string",
                        "description": "Путь к PDF-файлу"
                    }
                },
                "required": ["pdf_path"]
            }
        ),
        Tool(
            name="extract_tables",
            description=(
                "Извлекает таблицы из PDF с помощью pdfplumber. "
                "Можно указать конкретные страницы."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pdf_path": {
                        "type": "string",
                        "description": "Путь к PDF-файлу"
                    },
                    "pages": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Список номеров страниц (опционально)"
                    }
                },
                "required": ["pdf_path"]
            }
        ),
        Tool(
            name="extract_formulas",
            description=(
                "Извлекает формулы из PDF по эвристикам. "
                "Ищет строки с '=' и расчётными выражениями."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pdf_path": {
                        "type": "string",
                        "description": "Путь к PDF-файлу"
                    }
                },
                "required": ["pdf_path"]
            }
        ),
        Tool(
            name="get_structure",
            description=(
                "Возвращает иерархию разделов PDF. "
                "Использует оглавление или определяет разделы по эвристикам."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pdf_path": {
                        "type": "string",
                        "description": "Путь к PDF-файлу"
                    }
                },
                "required": ["pdf_path"]
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    """Обрабатывает вызовы инструментов."""
    
    if name == "decompose_pdf":
        pdf_path = arguments.get("pdf_path")
        if not pdf_path:
            return [TextContent(type="text", text="Ошибка: не указан путь к PDF.")]
        
        result = decompose_pdf(pdf_path)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "extract_tables":
        pdf_path = arguments.get("pdf_path")
        pages = arguments.get("pages")
        
        if not pdf_path:
            return [TextContent(type="text", text="Ошибка: не указан путь к PDF.")]
        
        result = extract_tables(pdf_path, pages)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "extract_formulas":
        pdf_path = arguments.get("pdf_path")
        
        if not pdf_path:
            return [TextContent(type="text", text="Ошибка: не указан путь к PDF.")]
        
        result = extract_formulas(pdf_path)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "get_structure":
        pdf_path = arguments.get("pdf_path")
        
        if not pdf_path:
            return [TextContent(type="text", text="Ошибка: не указан путь к PDF.")]
        
        result = get_structure(pdf_path)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    return [TextContent(type="text", text=f"Неизвестный инструмент: {name}")]


async def main():
    """Запускает MCP-сервер."""
    ensure_cache_dir()
    
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())