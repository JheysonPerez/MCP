"""
Fixtures compartidos para todos los tests de MCP-DOCS.
"""
import pytest
import os
import sys

# Asegurar que el proyecto está en el path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Setea variables de entorno para testing."""
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_CHAT_MODEL", "qwen2.5:3b")
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/mcp_test")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-12345")


@pytest.fixture
def sample_document_text():
    """Texto de ejemplo para tests de chunking."""
    return """
# INTRODUCCIÓN

Este es el primer párrafo del documento. Habla sobre temas generales
y establece el contexto para lo que viene después.

## Sección Principal

Aquí entramos en detalles. Este párrafo contiene información específica
sobre el tema central del documento. Más texto aquí para completar.

### Subsección A

Contenido de la subsección con datos técnicos y números: 123, 456.

## Conclusión

Resumen final de los puntos clave mencionados anteriormente.
"""


@pytest.fixture
def sample_chunks():
    """Chunks de ejemplo para tests de retrieval."""
    return [
        {
            "id": 1,
            "document_id": 1,
            "text": "Introducción al sistema de gestión documental",
            "section": "Introducción",
            "position": 0
        },
        {
            "id": 2,
            "document_id": 1,
            "text": "Configuración de PostgreSQL con pgvector para embeddings",
            "section": "Configuración",
            "position": 1
        },
        {
            "id": 3,
            "document_id": 2,
            "text": "Guía de uso del asistente RAG",
            "section": "Guía",
            "position": 0
        }
    ]


@pytest.fixture
def mock_db_response():
    """Respuesta mock de base de datos."""
    return [
        {
            "id": 1,
            "filename": "test_doc.pdf",
            "doc_type": "informe",
            "doc_year": 2024,
            "is_indexed": True,
            "chunk_count": 5,
            "summary": "Documento de prueba"
        }
    ]
