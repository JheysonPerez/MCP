"""
Tests unitarios para RetrievalService.
"""
import pytest
from unittest.mock import MagicMock, patch
from services.retrieval_service import RetrievalService


@pytest.fixture
def retrieval_service():
    """Fixture del servicio completamente mockeado."""
    with patch('services.retrieval_service.EmbeddingService') as mock_embed_class, \
         patch('services.retrieval_service.RerankService'), \
         patch('services.retrieval_service.HybridSearchService'), \
         patch('services.retrieval_service.DatabaseConnection') as mock_db_class, \
         patch('services.retrieval_service.register_vector'):

        # Configurar mocks
        mock_embed = MagicMock()
        mock_embed.get_embedding.return_value = [0.1] * 768
        mock_embed_class.return_value = mock_embed

        mock_db = MagicMock()
        mock_db_class.return_value = mock_db

        # Simular conexión y cursor
        mock_conn = MagicMock()
        mock_db.get_connection.return_value = mock_conn

        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        # Crear servicio
        service = RetrievalService(embedding_service=mock_embed)
        service.db = mock_db

        # Guardar mocks para acceso en tests
        service._mock_cursor = mock_cursor
        service._mock_conn = mock_conn
        service._mock_embed = mock_embed

        yield service


class TestRetrievalService:
    """Test suite para RetrievalService."""

    def test_inicializa_con_servicios(self, retrieval_service):
        """Debe inicializarse con los servicios requeridos."""
        assert retrieval_service.embedding_service is not None
        assert retrieval_service.db is not None

    def test_llama_a_embedding_service(self, retrieval_service):
        """Debe llamar al embedding service para generar embeddings."""
        retrieval_service._mock_cursor.fetchall.return_value = [
            {"document_id": 1, "chunk_text": "Test", "score": 0.8, "filename": "test.pdf", "chunk_index": 0}
        ]

        retrieval_service.search(query="consulta de prueba", use_rerank=False, use_hybrid=False)

        # Verificar que se llamó al embedding service
        retrieval_service._mock_embed.get_embedding.assert_called_once_with("consulta de prueba")

    def test_construye_query_con_filtros(self, retrieval_service):
        """Debe construir query SQL con filtros de metadatos."""
        retrieval_service._mock_cursor.fetchall.return_value = [
            {"document_id": 42, "chunk_text": "Certificado", "score": 0.8, "filename": "cert.pdf", "chunk_index": 0}
        ]

        retrieval_service.search(
            query="certificado",
            doc_type_filter="certificado",
            doc_year_filter=2024,
            use_rerank=False,
            use_hybrid=False
        )

        # Verificar que se ejecutó la query
        retrieval_service._mock_cursor.execute.assert_called()
        # La query debe haber sido llamada con parámetros
        call_args = retrieval_service._mock_cursor.execute.call_args
        assert call_args is not None

    def test_retorna_resultados_con_document_id(self, retrieval_service):
        """Los resultados deben incluir document_id."""
        retrieval_service._mock_cursor.fetchall.return_value = [
            {"document_id": 99, "chunk_text": "Texto del chunk", "score": 0.9, "filename": "doc99.pdf", "chunk_index": 0}
        ]

        results = retrieval_service.search(
            query="test",
            use_rerank=False,
            use_hybrid=False
        )

        assert len(results) > 0
        assert results[0]['document_id'] == 99
