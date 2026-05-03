"""
Tests unitarios para EmbeddingService.
"""
import pytest
from unittest.mock import MagicMock, patch
from services.embedding_service import EmbeddingService


@pytest.fixture
def embedding_service():
    """Fixture del servicio de embeddings."""
    with patch.dict('os.environ', {
        'OLLAMA_BASE_URL': 'http://localhost:11434',
        'OLLAMA_EMBED_MODEL': 'embeddinggemma'
    }):
        service = EmbeddingService()
        yield service


class TestInit:
    """Test suite para constructor."""

    def test_carga_configuracion_default(self):
        """Debe cargar configuración por defecto."""
        service = EmbeddingService()
        assert service.base_url == "http://localhost:11434"
        # El modelo puede variar según .env, solo verificamos que existe
        assert isinstance(service.model, str)
        assert len(service.model) > 0

    def test_carga_configuracion_env(self):
        """Debe cargar configuración desde variables de entorno."""
        with patch.dict('os.environ', {
            'OLLAMA_BASE_URL': 'http://custom:8080',
            'OLLAMA_EMBED_MODEL': 'nomic-embed-text'
        }):
            service = EmbeddingService()
            assert service.base_url == "http://custom:8080"
            assert service.model == "nomic-embed-text"


class TestGetEmbedding:
    """Test suite para get_embedding()."""

    @patch('services.embedding_service.requests.post')
    def test_genera_embedding(self, mock_post, embedding_service):
        """Debe generar embedding para texto."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"embedding": [0.1, 0.2, 0.3]}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        result = embedding_service.get_embedding("Texto de prueba")

        assert result == [0.1, 0.2, 0.3]
        mock_post.assert_called_once()

    @patch('services.embedding_service.requests.post')
    def test_retorna_vacio_si_falla(self, mock_post, embedding_service):
        """Debe retornar lista vacía si no hay embedding."""
        mock_response = MagicMock()
        mock_response.json.return_value = {}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        result = embedding_service.get_embedding("Texto")

        assert result == []

    @patch('services.embedding_service.requests.post')
    def test_maneja_timeout(self, mock_post, embedding_service):
        """Debe lanzar excepción en timeout."""
        import requests
        mock_post.side_effect = requests.Timeout("Timeout")

        with pytest.raises(requests.Timeout):
            embedding_service.get_embedding("Texto")
