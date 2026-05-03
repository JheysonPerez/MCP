"""
Tests para la clasificación de intenciones en RagService.
"""
import pytest
from unittest.mock import MagicMock, patch
from services.rag_service import RagService


@pytest.fixture
def rag_service():
    """Fixture del RAG service con dependencias mockeadas."""
    # Crear mocks de los servicios que necesita RagService
    mock_retrieval = MagicMock()
    mock_chunk = MagicMock()
    mock_persistence = MagicMock()

    # Crear instancia de RagService con los mocks
    service = RagService(
        retrieval_service=mock_retrieval,
        chunk_service=mock_chunk,
        persistence_service=mock_persistence
    )
    return service


class TestIntentClassification:
    """Test suite para clasificación de intenciones (_classify_intent)."""

    def test_detecta_saludo_simple(self, rag_service):
        """Debe clasificar saludos como 'greeting'."""
        saludos = ["hola", "buenos días", "hey", "buenas"]

        for saludo in saludos:
            intent = rag_service._classify_intent(saludo)
            assert intent == 'greeting', f"'{saludo}' debería ser greeting, fue {intent}"

    def test_detecta_metadata_query(self, rag_service):
        """Debe clasificar consultas sobre documentos disponibles como 'metadata'."""
        queries = [
            "cuántos documentos hay",
            "qué archivos tienes",
            "lista de documentos",
            "cuáles son los documentos indexados"
        ]

        for query in queries:
            intent = rag_service._classify_intent(query)
            assert intent == 'metadata', f"'{query}' debería ser metadata, fue {intent}"

    def test_detecta_content_query(self, rag_service):
        """Debe clasificar consultas sobre contenido como 'content'."""
        queries = [
            "de qué habla el documento 5",
            "resume el contenido",
            "qué dice el certificado",
            "explícame el informe"
        ]

        for query in queries:
            intent = rag_service._classify_intent(query)
            assert intent == 'content', f"'{query}' debería ser content, fue {intent}"

    def test_no_clasifica_doc_id_como_metadata(self, rag_service):
        """CRÍTICO: 'de qué habla el documento' NO debe ser metadata.

        Bug reportado: esta consulta se clasificaba erróneamente como metadata
        porque contiene la palabra 'documento', ignorando el contexto.
        """
        intent = rag_service._classify_intent("de qué habla el documento")
        assert intent == 'content', "Consulta sobre contenido de doc específico debe ser 'content'"

    def test_detecta_pregunta_numerica(self, rag_service):
        """Preguntas con números específicos deben ir a content."""
        queries = [
            "qué dice el documento 123",
            "dame el certificado 456",
            "información del doc 789"
        ]

        for query in queries:
            intent = rag_service._classify_intent(query)
            assert intent == 'content', f"'{query}' con número debería ser content"


class TestMetadataFilterDetection:
    """Test suite para detección de filtros de metadatos."""

    def test_detecta_tipo_de_documento(self, rag_service):
        """Debe extraer doc_type de la consulta."""
        query = "muéstrame los certificados del 2023"
        filters = rag_service._detect_metadata_filters(query)

        assert filters.get('doc_type') == 'certificado'

    def test_detecta_año(self, rag_service):
        """Debe extraer doc_year de la consulta."""
        query = "certificados del 2023"
        filters = rag_service._detect_metadata_filters(query)

        assert filters.get('doc_year') == 2023

    def test_detecta_tipo_y_año_juntos(self, rag_service):
        """Debe detectar ambos filtros simultáneamente."""
        query = "informes de 2022"
        filters = rag_service._detect_metadata_filters(query)

        assert filters.get('doc_type') == 'informe'
        assert filters.get('doc_year') == 2022

    def test_no_detecta_filtros_cuando_no_hay(self, rag_service):
        """Consultas sin metadatos específicos deben retornar dict vacío."""
        query = "cuál es mi horario de trabajo"
        filters = rag_service._detect_metadata_filters(query)

        assert filters.get('doc_type') is None
        assert filters.get('doc_year') is None
