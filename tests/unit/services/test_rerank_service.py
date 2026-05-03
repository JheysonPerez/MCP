"""
Tests unitarios para RerankService.
"""
import pytest
from unittest.mock import MagicMock, patch
from services.rerank_service import RerankService, create_rerank_service


@pytest.fixture
def rerank_service():
    """Fixture del servicio de re-ranking."""
    with patch.dict('os.environ', {'OLLAMA_BASE_URL': 'http://localhost:11434'}):
        service = RerankService(model="llama3.2")
        yield service


class TestInit:
    """Test suite para constructor."""

    def test_carga_configuracion_default(self):
        """Debe cargar configuración por defecto."""
        service = RerankService()
        assert service.base_url == "http://localhost:11434"
        assert service.model == "llama3.2"

    def test_acepta_parametros_custom(self):
        """Debe aceptar parámetros personalizados."""
        service = RerankService(base_url="http://custom:8080", model="mistral")
        assert service.base_url == "http://custom:8080"
        assert service.model == "mistral"


class TestScoreRelevance:
    """Test suite para _score_relevance()."""

    def test_calcula_score_heuristico(self, rerank_service):
        """Debe calcular score usando heurísticas locales."""
        result = rerank_service._score_relevance(
            query="consulta de prueba",
            text="Texto del chunk con consulta incluida"
        )

        assert isinstance(result, float)
        assert 0 <= result <= 1

    def test_score_alto_si_match_exacto(self, rerank_service):
        """Debe dar score alto si hay match exacto."""
        result = rerank_service._score_relevance(
            query="documento importante",
            text="Este es un documento importante para revisar"
        )

        assert result > 0.5

    def test_score_bajo_si_no_hay_match(self, rerank_service):
        """Debe dar score bajo si no hay relación."""
        result = rerank_service._score_relevance(
            query="xyz123 abc789",
            text="Texto completamente diferente sin relación"
        )

        assert result < 0.5


class TestRerank:
    """Test suite para rerank()."""

    @patch.object(RerankService, '_score_relevance')
    def test_reordena_chunks(self, mock_score, rerank_service):
        """Debe reordenar chunks por relevancia."""
        mock_score.return_value = 0.9

        chunks = [
            {"id": 1, "text": "Texto 1", "score": 0.5},
            {"id": 2, "text": "Texto 2", "score": 0.6}
        ]

        result = rerank_service.rerank(
            query="consulta",
            chunks=chunks,
            top_k=2
        )

        assert isinstance(result, list)
        assert len(result) <= 2

    @patch.object(RerankService, '_score_relevance')
    def test_limita_top_k(self, mock_score, rerank_service):
        """Debe limitar resultados a top_k."""
        mock_score.return_value = 0.8

        chunks = [{"id": i, "text": f"Texto {i}"} for i in range(10)]

        result = rerank_service.rerank(
            query="consulta",
            chunks=chunks,
            top_k=3
        )

        assert len(result) == 3


class TestRerankWithLLM:
    """Test suite para rerank_with_llm()."""

    @patch('services.rerank_service.requests.post')
    def test_usa_llm_para_ranking(self, mock_post, rerank_service):
        """Debe usar LLM para ranking."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "message": {"content": "1. Chunk 1\n2. Chunk 2\n3. Chunk 3"}
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        chunks = [
            {"chunk_index": 0, "text": "Chunk 1"},
            {"chunk_index": 1, "text": "Chunk 2"},
            {"chunk_index": 2, "text": "Chunk 3"}
        ]

        result = rerank_service.rerank_with_llm(
            query="consulta",
            chunks=chunks,
            top_k=3
        )

        assert isinstance(result, list)


class TestFactory:
    """Test suite para factory function."""

    def test_create_service(self):
        """Debe crear instancia del servicio."""
        service = create_rerank_service()
        assert isinstance(service, RerankService)
