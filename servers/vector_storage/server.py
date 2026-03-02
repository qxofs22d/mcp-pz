"""
Vector Storage MCP Server — семантическое индексирование и поиск по текстам.

Использует sentence-transformers для эмбеддингов и NumPy для хранения и поиска.
Поддерживает несколько коллекций: documents, pdf, dialogue, system.
Не зависит от ChromaDB, работает с Python 3.14+.
"""

import json
import os
import numpy as np
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio

# Создаём экземпляр MCP-сервера
server = Server("vector_storage")

# Путь к хранилищу векторов
# Поддерживаем переменную окружения PROJECT_PATH для привязки к проекту
_project_path = os.environ.get("PROJECT_PATH", "")
if _project_path:
    VECTOR_INDEX_PATH = Path(_project_path) / "vector_index"
else:
    VECTOR_INDEX_PATH = Path("vector_index")

# Поддерживаемые коллекции
COLLECTIONS = ["documents", "pdf", "dialogue", "system"]

# Глобальные переменные
_embedding_model = None


def get_embedding_model():
    """
    Возвращает модель эмбеддингов (ленивая инициализация).
    """
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
    return _embedding_model


def get_embeddings(texts: List[str]) -> np.ndarray:
    """
    Вычисляет эмбеддинги для списка текстов.
    
    Args:
        texts: Список текстов
    
    Returns:
        Массив векторов эмбеддингов (numpy)
    """
    model = get_embedding_model()
    embeddings = model.encode(texts, convert_to_numpy=True)
    return embeddings


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """
    Вычисляет косинусную схожесть между вектором a и матрицей векторов b.
    
    Args:
        a: Вектор запроса (1D)
        b: Матрица векторов (2D)
    
    Returns:
        Массив значений схожести
    """
    # Нормализуем векторы
    a_norm = a / (np.linalg.norm(a) + 1e-8)
    b_norm = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-8)
    
    # Вычисляем косинусную схожесть
    return np.dot(b_norm, a_norm)


class SimpleVectorStore:
    """
    Простое файловое хранилище векторов на NumPy.
    
    Структура файлов для каждой коллекции:
    - {collection}_vectors.npy — матрица векторов (n x dim)
    - {collection}_metadata.json — метаданные чанков
    """
    
    def __init__(self, collection: str):
        self.collection = collection
        self.vectors_path = VECTOR_INDEX_PATH / f"{collection}_vectors.npy"
        self.metadata_path = VECTOR_INDEX_PATH / f"{collection}_metadata.json"
        self.vectors: Optional[np.ndarray] = None
        self.metadata: List[Dict] = []
        self._load()
    
    def _load(self):
        """Загружает данные из файлов."""
        VECTOR_INDEX_PATH.mkdir(parents=True, exist_ok=True)
        
        if self.vectors_path.exists():
            try:
                self.vectors = np.load(self.vectors_path)
            except Exception:
                self.vectors = None
        
        if self.metadata_path.exists():
            try:
                with open(self.metadata_path, 'r', encoding='utf-8') as f:
                    self.metadata = json.load(f)
            except Exception:
                self.metadata = []
    
    def _save(self):
        """Сохраняет данные в файлы."""
        if self.vectors is not None:
            np.save(self.vectors_path, self.vectors)
        
        with open(self.metadata_path, 'w', encoding='utf-8') as f:
            json.dump(self.metadata, f, ensure_ascii=False, indent=2)
    
    def add(self, ids: List[str], documents: List[str], embeddings: List[List[float]], metadatas: List[Dict]):
        """Добавляет векторы в хранилище."""
        new_vectors = np.array(embeddings, dtype=np.float32)
        
        if self.vectors is None:
            self.vectors = new_vectors
        else:
            self.vectors = np.vstack([self.vectors, new_vectors])
        
        # Добавляем метаданные
        for i, (id_, doc, meta) in enumerate(zip(ids, documents, metadatas)):
            self.metadata.append({
                "id": id_,
                "document": doc,
                "metadata": meta
            })
        
        self._save()
    
    def query(self, query_embedding: List[float], n_results: int, where_filter: Optional[Dict] = None) -> Dict:
        """Выполняет поиск по схожести."""
        if self.vectors is None or len(self.vectors) == 0:
            return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
        
        query_vec = np.array(query_embedding, dtype=np.float32)
        
        # Вычисляем схожесть
        similarities = cosine_similarity(query_vec, self.vectors)
        
        # Фильтрация по документам
        if where_filter and "document_name" in where_filter:
            doc_names = where_filter["document_name"].get("$in", [])
            mask = np.array([
                m.get("metadata", {}).get("document_name", "") in doc_names
                for m in self.metadata
            ])
            similarities = np.where(mask, similarities, -1)
        
        # Получаем топ-k индексов
        n_results = min(n_results, len(similarities))
        top_indices = np.argsort(similarities)[::-1][:n_results]
        
        # Формируем результат
        ids = [[self.metadata[i]["id"] for i in top_indices]]
        documents = [[self.metadata[i]["document"] for i in top_indices]]
        metadatas = [[self.metadata[i]["metadata"] for i in top_indices]]
        distances = [[1 - similarities[i] for i in top_indices]]  # конвертируем в distance
        
        return {
            "ids": ids,
            "documents": documents,
            "metadatas": metadatas,
            "distances": distances
        }
    
    def delete_by_document(self, document_name: str) -> int:
        """Удаляет все чанки документа."""
        if self.vectors is None:
            return 0
        
        # Находим индексы для удаления
        indices_to_keep = [
            i for i, m in enumerate(self.metadata)
            if m.get("metadata", {}).get("document_name") != document_name
        ]
        
        deleted_count = len(self.metadata) - len(indices_to_keep)
        
        if deleted_count > 0:
            self.vectors = self.vectors[indices_to_keep] if indices_to_keep else None
            self.metadata = [self.metadata[i] for i in indices_to_keep]
            self._save()
        
        return deleted_count
    
    def count(self) -> int:
        """Возвращает количество векторов."""
        return len(self.vectors) if self.vectors is not None else 0


# Глобальное хранилище коллекций
_stores: Dict[str, SimpleVectorStore] = {}


def get_store(collection: str) -> SimpleVectorStore:
    """Возвращает или создаёт хранилище для коллекции."""
    if collection not in _stores:
        _stores[collection] = SimpleVectorStore(collection)
    return _stores[collection]


def split_into_chunks(text: str, chunk_size: int = 500, overlap: float = 0.1) -> List[str]:
    """
    Разбивает текст на чанки с перекрытием.
    
    Args:
        text: Исходный текст
        chunk_size: Размер чанка в токенах (примерно 4 символа = 1 токен)
        overlap: Доля перекрытия (0.1 = 10%)
    
    Returns:
        Список чанков
    """
    # Примерная оценка: 1 токен ≈ 4 символа для русского/английского
    chars_per_chunk = chunk_size * 4
    overlap_chars = int(chars_per_chunk * overlap)
    
    chunks = []
    start = 0
    text_len = len(text)
    
    while start < text_len:
        end = min(start + chars_per_chunk, text_len)
        chunk = text[start:end].strip()
        
        if chunk:  # Не добавляем пустые чанки
            chunks.append(chunk)
        
        # Сдвигаемся с учётом перекрытия
        start = end - overlap_chars
        if end == text_len:
            break
    
    return chunks


def add_document_chunks(
    document_name: str,
    chunks: List[str],
    collection: str = "documents"
) -> dict:
    """
    Добавляет чанки документа в коллекцию.
    
    Args:
        document_name: Имя документа
        chunks: Список текстовых чанков
        collection: Имя коллекции
    
    Returns:
        Статус операции
    """
    if collection not in COLLECTIONS:
        return {
            "success": False,
            "error": f"Неизвестная коллекция: {collection}. Доступные: {COLLECTIONS}"
        }
    
    if not chunks:
        return {
            "success": False,
            "error": "Список чанков пуст"
        }
    
    try:
        store = get_store(collection)
        
        # Генерируем уникальные ID для чанков
        import uuid
        ids = [f"{document_name}_{i}_{uuid.uuid4().hex[:8]}" for i in range(len(chunks))]
        
        # Метаданные для каждого чанка
        metadatas = [
            {
                "document_name": document_name,
                "chunk_index": i,
                "chunk_length": len(chunk)
            }
            for i, chunk in enumerate(chunks)
        ]
        
        # Вычисляем эмбеддинги
        embeddings = get_embeddings(chunks)
        
        # Добавляем в хранилище
        store.add(
            ids=ids,
            documents=chunks,
            embeddings=embeddings.tolist(),
            metadatas=metadatas
        )
        
        return {
            "success": True,
            "message": f"Добавлено {len(chunks)} чанков из документа '{document_name}' в коллекцию '{collection}'",
            "document_name": document_name,
            "chunks_count": len(chunks),
            "collection": collection
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": f"Ошибка при добавлении чанков: {str(e)}"
        }


def search(
    query: str,
    top_k: int = 5,
    collection: str = "documents",
    filter_documents: Optional[List[str]] = None
) -> dict:
    """
    Выполняет семантический поиск по коллекции.
    
    Args:
        query: Поисковый запрос
        top_k: Количество результатов
        collection: Имя коллекции
        filter_documents: Список имён документов для фильтрации
    
    Returns:
        Результаты поиска с метаданными
    """
    if collection not in COLLECTIONS:
        return {
            "success": False,
            "error": f"Неизвестная коллекция: {collection}. Доступные: {COLLECTIONS}"
        }
    
    try:
        store = get_store(collection)
        
        # Вычисляем эмбеддинг для запроса
        query_embedding = get_embeddings([query])[0]
        
        # Формируем фильтр если нужно
        where_filter = None
        if filter_documents:
            where_filter = {
                "document_name": {"$in": filter_documents}
            }
        
        # Выполняем поиск
        results = store.query(
            query_embedding=query_embedding.tolist(),
            n_results=top_k,
            where_filter=where_filter
        )
        
        # Форматируем результаты
        search_results = []
        if results and results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                result = {
                    "text": doc,
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else None
                }
                search_results.append(result)
        
        return {
            "success": True,
            "query": query,
            "collection": collection,
            "results_count": len(search_results),
            "results": search_results
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": f"Ошибка при поиске: {str(e)}"
        }


def list_collections() -> dict:
    """
    Возвращает список всех коллекций с информацией о количестве документов.
    
    Returns:
        Информация о коллекциях
    """
    try:
        collections_info = []
        
        for name in COLLECTIONS:
            try:
                store = get_store(name)
                count = store.count()
                collections_info.append({
                    "name": name,
                    "count": count
                })
            except Exception:
                collections_info.append({
                    "name": name,
                    "count": 0
                })
        
        return {
            "success": True,
            "collections": collections_info,
            "index_path": str(VECTOR_INDEX_PATH.absolute())
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": f"Ошибка при получении списка коллекций: {str(e)}"
        }


def delete_document(document_name: str, collection: str = "documents") -> dict:
    """
    Удаляет все чанки документа из коллекции.
    
    Args:
        document_name: Имя документа
        collection: Имя коллекции
    
    Returns:
        Статус операции
    """
    if collection not in COLLECTIONS:
        return {
            "success": False,
            "error": f"Неизвестная коллекция: {collection}"
        }
    
    try:
        store = get_store(collection)
        deleted_count = store.delete_by_document(document_name)
        
        return {
            "success": True,
            "message": f"Удалено {deleted_count} чанков документа '{document_name}'",
            "deleted_count": deleted_count
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": f"Ошибка при удалении документа: {str(e)}"
        }


@server.list_tools()
async def list_tools():
    """Возвращает список доступных инструментов."""
    return [
        Tool(
            name="add_document_chunks",
            description=(
                "Добавляет чанки текста в указанную коллекцию для последующего поиска. "
                "Коллекции: documents, pdf, dialogue, system. "
                "Каждый чанк получает метаданные с именем документа."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "document_name": {
                        "type": "string",
                        "description": "Имя документа (для идентификации и фильтрации)"
                    },
                    "chunks": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Список текстовых чанков для индексации"
                    },
                    "collection": {
                        "type": "string",
                        "enum": COLLECTIONS,
                        "description": "Имя коллекции (по умолчанию 'documents')",
                        "default": "documents"
                    }
                },
                "required": ["document_name", "chunks"]
            }
        ),
        Tool(
            name="search",
            description=(
                "Выполняет семантический поиск по указанной коллекции. "
                "Возвращает top_k наиболее релевантных чанков с метаданными и оценкой расстояния."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Поисковый запрос"
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Количество результатов (по умолчанию 5)",
                        "default": 5
                    },
                    "collection": {
                        "type": "string",
                        "enum": COLLECTIONS,
                        "description": "Имя коллекции (по умолчанию 'documents')",
                        "default": "documents"
                    },
                    "filter_documents": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Список имён документов для фильтрации результатов (опционально)"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="list_collections",
            description=(
                "Возвращает список всех коллекций с информацией о количестве документов в каждой."
            ),
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="delete_document",
            description=(
                "Удаляет все чанки указанного документа из коллекции."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "document_name": {
                        "type": "string",
                        "description": "Имя документа для удаления"
                    },
                    "collection": {
                        "type": "string",
                        "enum": COLLECTIONS,
                        "description": "Имя коллекции (по умолчанию 'documents')",
                        "default": "documents"
                    }
                },
                "required": ["document_name"]
            }
        ),
        Tool(
            name="split_text",
            description=(
                "Разбивает текст на чанки размером ~500 токенов с перекрытием 10%. "
                "Полезно для подготовки текста к индексации."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Текст для разбивки на чанки"
                    },
                    "chunk_size": {
                        "type": "integer",
                        "description": "Размер чанка в токенах (по умолчанию 500)",
                        "default": 500
                    }
                },
                "required": ["text"]
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    """Обрабатывает вызовы инструментов."""
    
    if name == "add_document_chunks":
        document_name = arguments.get("document_name")
        chunks = arguments.get("chunks", [])
        collection = arguments.get("collection", "documents")
        
        if not document_name:
            return [TextContent(type="text", text="Ошибка: не указано имя документа.")]
        
        result = add_document_chunks(document_name, chunks, collection)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "search":
        query = arguments.get("query")
        top_k = arguments.get("top_k", 5)
        collection = arguments.get("collection", "documents")
        filter_documents = arguments.get("filter_documents")
        
        if not query:
            return [TextContent(type="text", text="Ошибка: не указан поисковый запрос.")]
        
        result = search(query, top_k, collection, filter_documents)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "list_collections":
        result = list_collections()
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "delete_document":
        document_name = arguments.get("document_name")
        collection = arguments.get("collection", "documents")
        
        if not document_name:
            return [TextContent(type="text", text="Ошибка: не указано имя документа.")]
        
        result = delete_document(document_name, collection)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "split_text":
        text = arguments.get("text")
        chunk_size = arguments.get("chunk_size", 500)
        
        if not text:
            return [TextContent(type="text", text="Ошибка: не указан текст.")]
        
        chunks = split_into_chunks(text, chunk_size)
        result = {
            "success": True,
            "chunks_count": len(chunks),
            "chunk_size_tokens": chunk_size,
            "chunks": chunks
        }
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    return [TextContent(type="text", text=f"Неизвестный инструмент: {name}")]


async def main():
    """Запускает MCP-сервер."""
    VECTOR_INDEX_PATH.mkdir(parents=True, exist_ok=True)
    
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())