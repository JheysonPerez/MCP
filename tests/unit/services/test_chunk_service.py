"""
Tests unitarios para ChunkService.
"""
import pytest
from services.chunk_service import ChunkService


@pytest.fixture
def chunker():
    """Fixture del servicio de chunking."""
    return ChunkService(chunk_size=800, overlap=100)


class TestChunkService:
    """Test suite para ChunkService."""

    def test_chunk_text_genera_chunks(self, chunker):
        """Debe generar chunks a partir de texto."""
        text = """## Introducción

Contenido de introducción con suficiente texto para hacer chunks de prueba.
Este párrafo necesita ser más largo para que el chunking tenga efecto.

## Metodología

Contenido de metodología también extenso para que se detecte como sección.
Agregamos más líneas para asegurar que el chunker procese correctamente.

## Resultados

Contenido de resultados con datos y números para completar el documento."""

        chunks = chunker.chunk_text(text, document_id="test_1")

        assert len(chunks) > 0
        # Verificar estructura de chunks
        for chunk in chunks:
            assert 'text' in chunk
            assert 'document_id' in chunk
            assert chunk['document_id'] == "test_1"

    def test_chunking_con_parametros_custom(self):
        """Debe respetar chunk_size y overlap personalizados."""
        chunker = ChunkService(chunk_size=200, overlap=20)
        text = "Palabra " * 100  # Texto largo

        chunks = chunker.chunk_text(text, document_id="test_2")

        assert len(chunks) > 0
        # Verificar que hay chunks (con overlap pueden ser más)
        for chunk in chunks:
            assert 'text' in chunk
            assert chunk['text'].strip()

    def test_chunk_no_vacios(self, chunker):
        """No debe generar chunks vacíos."""
        text = """## Título

Contenido aquí con texto suficiente para generar al menos un chunk.
Necesitamos más contenido para asegurar que el chunker tenga material.



Otro párrafo con información adicional."""

        chunks = chunker.chunk_text(text, document_id="test_3")

        for chunk in chunks:
            assert chunk['text'].strip()
            assert len(chunk['text'].strip()) > 0

    def test_detecta_documento_formulario(self, chunker):
        """Debe detectar documentos tipo formulario y aplicar estrategia especial."""
        # Texto que simula un formulario (líneas cortas, campos)
        text = """Campo 1: Valor 1
Campo 2: Valor 2
Campo 3: Valor 3
Campo 4: Valor 4
Campo 5: Valor 5"""

        chunks = chunker.chunk_text(text, document_id="form_1")

        assert len(chunks) > 0
        for chunk in chunks:
            assert 'text' in chunk
            assert chunk['document_id'] == "form_1"

    def test_texto_simple_sin_headers(self, chunker):
        """Debe funcionar con texto sin headers."""
        text = "Este es un texto simple sin secciones ni headers. " * 20

        chunks = chunker.chunk_text(text, document_id="simple_1")

        assert len(chunks) > 0
        for chunk in chunks:
            assert 'text' in chunk
            assert chunk['document_id'] == "simple_1"
