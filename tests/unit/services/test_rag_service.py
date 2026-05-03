"""
Tests unitarios para RagService.
"""
import pytest
from unittest.mock import MagicMock, patch, mock_open
from services.rag_service import RagService


@pytest.fixture
def rag_service():
    """Fixture del servicio RAG con mocks."""
    with patch('services.rag_service.RetrievalService') as mock_retrieval_class:
        with patch('services.rag_service.ChunkService') as mock_chunk_class:
            mock_retrieval = MagicMock()
            mock_chunk = MagicMock()
            mock_retrieval_class.return_value = mock_retrieval
            mock_chunk_class.return_value = mock_chunk

            service = RagService(
                retrieval_service=mock_retrieval,
                chunk_service=mock_chunk,
                persistence_service=None
            )
            service._mock_retrieval = mock_retrieval
            service._mock_chunk = mock_chunk

            yield service


class TestClassifyIntent:
    """Test suite para _classify_intent()."""

    def test_detecta_saludo_simple(self, rag_service):
        """Debe detectar saludos simples."""
        result = rag_service._classify_intent("hola")
        assert result == "greeting"

    def test_detecta_metadata_query(self, rag_service):
        """Debe detectar consultas sobre metadata."""
        result = rag_service._classify_intent("cuántos documentos hay")
        assert result == "metadata"

    def test_detecta_content_query(self, rag_service):
        """Debe detectar consultas sobre contenido."""
        result = rag_service._classify_intent("qué dice el certificado")
        assert result == "content"


class TestNormalizeText:
    """Test suite para _normalize_text()."""

    def test_quita_extensiones(self, rag_service):
        """Debe quitar extensiones de archivo."""
        result = rag_service._normalize_text("documento.pdf")
        assert ".pdf" not in result

    def test_quita_puntuacion(self, rag_service):
        """Debe quitar puntuación."""
        result = rag_service._normalize_text("documento,;.")
        assert "," not in result

    def test_minusculas(self, rag_service):
        """Debe convertir a minúsculas."""
        result = rag_service._normalize_text("DOCUMENTO")
        assert result == "documento"


class TestDetectQuestionType:
    """Test suite para _detect_question_type()."""

    def test_detecta_factual(self, rag_service):
        """Debe detectar preguntas factuales."""
        result = rag_service._detect_question_type("¿Cuál es el DNI?")
        assert result == "factual"

    def test_detecta_synthesis(self, rag_service):
        """Debe detectar preguntas de síntesis."""
        result = rag_service._detect_question_type("dame un resumen del documento")
        assert result == "synthesis"

    def test_detecta_procedural(self, rag_service):
        """Debe detectar preguntas de procedimiento."""
        result = rag_service._detect_question_type("pasos a seguir")
        assert result == "procedural"


class TestIsNumericQuery:
    """Test suite para _is_numeric_query()."""

    def test_detecta_dni(self, rag_service):
        """Debe detectar queries de DNI."""
        assert rag_service._is_numeric_query("cual es el dni") is True

    def test_detecta_codigo(self, rag_service):
        """Debe detectar queries de código."""
        assert rag_service._is_numeric_query("cual es el código") is True

    def test_detecta_fecha(self, rag_service):
        """Debe detectar queries de fecha."""
        assert rag_service._is_numeric_query("cual es la fecha") is True


class TestDetectMetadataFilters:
    """Test suite para _detect_metadata_filters()."""

    def test_detecta_tipo_certificado(self, rag_service):
        """Debe detectar filtro de tipo certificado."""
        result = rag_service._detect_metadata_filters("certificado 2024")
        assert result.get("doc_type") == "certificado"

    def test_detecta_tipo_resolucion(self, rag_service):
        """Debe detectar filtro de tipo resolución."""
        result = rag_service._detect_metadata_filters("resolución 2023")
        assert result.get("doc_type") == "resolución"


class TestCleanResponse:
    """Test suite para _clean_response()."""

    def test_quita_asteriscos(self, rag_service):
        """Debe quitar asteriscos sueltos."""
        result = rag_service._clean_response("***texto***")
        assert "***" not in result

    def test_normaliza_espacios(self, rag_service):
        """Debe normalizar espacios múltiples."""
        result = rag_service._clean_response("texto    con    espacios")
        assert "    " not in result


class TestGenerateResponse:
    """Test suite para generate_response()."""

    @patch('services.rag_service.requests.post')
    def test_responde_saludo(self, mock_post, rag_service):
        """Debe responder a saludos sin llamar a retrieval."""
        result = rag_service.generate_response("hola")

        assert "hola" in result["answer"].lower() or "asistente" in result["answer"].lower()
        # No debe llamar a retrieval para saludos
        rag_service._mock_retrieval.search.assert_not_called()

    @patch('services.rag_service.requests.post')
    def test_genera_respuesta_con_llm(self, mock_post, rag_service):
        """Debe generar respuesta usando LLM."""
        # Mock retrieval
        rag_service._mock_retrieval.search.return_value = [
            {"document_id": 1, "chunk_index": 0, "text": "Contexto", "score": 0.8, "filename": "doc.pdf"}
        ]

        # Mock LLM
        mock_response = MagicMock()
        mock_response.json.return_value = {"message": {"content": "Respuesta generada"}}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        result = rag_service.generate_response("qué dice el documento")

        assert result is not None
        assert "answer" in result


class TestIndexDocument:
    """Test suite para index_document()."""

    @patch('os.path.exists')
    def test_indexa_documento_completado(self, mock_exists, rag_service):
        """Debe indexar documento en estado completed."""
        mock_exists.return_value = True
        mock_persistence = MagicMock()
        mock_persistence.get_document_by_id.return_value = {
            "id": 1,
            "processing_status": "completed",
            "filename": "doc.pdf"
        }
        rag_service.persistence = mock_persistence

        with patch('builtins.open', mock_open(read_data="texto del documento")):
            rag_service._mock_chunk.chunk_text.return_value = [
                {"text": "chunk1", "chunk_index": 0}
            ]
            rag_service.index_document(1, "/path/to/doc.txt")

        rag_service._mock_chunk.chunk_text.assert_called_once()
