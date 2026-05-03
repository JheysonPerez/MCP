"""
Tests unitarios para MetadataExtractionService.
"""
import pytest
from unittest.mock import MagicMock, patch
import json
from services.metadata_extraction_service import MetadataExtractionService


@pytest.fixture
def metadata_service():
    """Fixture del servicio de extracción de metadatos."""
    service = MetadataExtractionService()
    yield service


class TestExtractMetadata:
    """Test suite para extract_metadata()."""

    @patch('services.metadata_extraction_service.requests.post')
    def test_extrae_tipo_documento(self, mock_post, metadata_service):
        """Debe extraer doc_type del contenido."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": json.dumps({
                "doc_type": "certificado",
                "doc_year": 2024,
                "personas": ["Juan Perez"],
                "organizaciones": ["UNAS"],
                "lugares": [],
                "temas": ["trabajo"],
                "keywords": ["certificado", "trabajo"],
                "summary": "Certificado de trabajo"
            })
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        text = "CERTIFICADO DE TRABAJO\n\nSe certifica que Juan Perez..."
        result = metadata_service.extract_metadata(text, filename="certificado.pdf")

        assert result.get("doc_type") == "certificado"
        assert result.get("doc_year") == 2024

    @patch('services.metadata_extraction_service.requests.post')
    def test_maneja_respuesta_json_malformada(self, mock_post, metadata_service):
        """Debe manejar respuesta JSON malformada del LLM."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "No es JSON válido"}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        text = "Texto del documento"
        result = metadata_service.extract_metadata(text, filename="doc.pdf")

        # Debe retornar estructura con metadata_extraction_failed = True
        assert result.get("metadata_extraction_failed") is True

    @patch('services.metadata_extraction_service.requests.post')
    def test_maneja_timeout_llm(self, mock_post, metadata_service):
        """Debe manejar timeout de llamada a LLM."""
        from requests.exceptions import Timeout
        mock_post.side_effect = Timeout("Request timed out")

        text = "Texto del documento"
        result = metadata_service.extract_metadata(text, filename="doc.pdf")

        assert result.get("metadata_extraction_failed") is True

    @patch('services.metadata_extraction_service.requests.post')
    def test_calcula_confidence(self, mock_post, metadata_service):
        """Debe calcular confianza de clasificación."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": json.dumps({
                "doc_type": "informe",
                "doc_year": 2024,
                "doc_date": "2024-01-15",
                "personas": ["Juan"],
                "organizaciones": ["UNAS"],
                "lugares": [],
                "temas": ["tema1"],
                "keywords": ["k1", "k2", "k3"],
                "summary": "Resumen del documento de más de 20 caracteres"
            })
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        text = "Contenido del informe"
        result = metadata_service.extract_metadata(text, filename="informe.pdf")

        assert "classification_confidence" in result
        assert result["classification_confidence"] > 0


class TestNormalizeDocType:
    """Test suite para normalización de tipos."""

    def test_normaliza_resolucion(self, metadata_service):
        """Debe normalizar variantes de resolución."""
        result = metadata_service._normalize_doc_type("resolucion")
        assert result == "resolución"

        result = metadata_service._normalize_doc_type("RESOLUCION")
        assert result == "resolución"

    def test_normaliza_informe(self, metadata_service):
        """Debe mapear reporte a informe."""
        result = metadata_service._normalize_doc_type("reporte")
        assert result == "informe"

    def test_normaliza_otro_si_no_encuentra(self, metadata_service):
        """Debe retornar 'otro' para tipos desconocidos."""
        result = metadata_service._normalize_doc_type("documento_desconocido_xyz")
        assert result == "otro"


class TestExtractYear:
    """Test suite para extracción de años."""

    def test_extrae_año_numerico(self, metadata_service):
        """Debe extraer año cuando es número válido."""
        result = metadata_service._extract_year(2024, None)
        assert result == 2024

    def test_extrae_año_de_fecha(self, metadata_service):
        """Debe extraer año de string de fecha."""
        result = metadata_service._extract_year(None, "2024-01-15")
        assert result == 2024

    def test_retorna_none_año_invalido(self, metadata_service):
        """Debe retornar None para año inválido."""
        result = metadata_service._extract_year(1800, None)
        assert result is None

        result = metadata_service._extract_year(2500, None)
        assert result is None


class TestNormalizeDate:
    """Test suite para normalización de fechas."""

    def test_normaliza_iso(self, metadata_service):
        """Debe aceptar formato ISO."""
        result = metadata_service._normalize_date("2024-01-15")
        assert result == "2024-01-15"

    def test_normaliza_slash(self, metadata_service):
        """Debe convertir formato con slashes."""
        result = metadata_service._normalize_date("15/01/2024")
        assert result == "2024-01-15"

    def test_retorna_none_fecha_invalida(self, metadata_service):
        """Debe retornar None para fecha inválida."""
        result = metadata_service._normalize_date("fecha invalida")
        assert result is None


class TestCalculateConfidence:
    """Test suite para cálculo de confianza."""

    def test_confidence_maxima(self, metadata_service):
        """Debe dar confianza alta con todos los campos."""
        data = {
            "doc_type": "certificado",
            "doc_year": 2024,
            "doc_date": "2024-01-15",
            "personas": ["Juan"],
            "keywords": ["k1", "k2", "k3"],
            "summary": "Resumen del documento de más de 20 caracteres"
        }
        result = metadata_service._calculate_confidence(data)
        assert result == 1.0

    def test_confidence_baja_si_otro(self, metadata_service):
        """Debe dar confianza baja si tipo es 'otro'."""
        data = {
            "doc_type": "otro",
            "doc_year": 2024,
            "personas": [],
            "keywords": [],
            "summary": ""
        }
        result = metadata_service._calculate_confidence(data)
        assert result < 0.5


class TestClassifyBatch:
    """Test suite para procesamiento batch."""

    @patch('services.metadata_extraction_service.requests.post')
    def test_procesa_multiples_documentos(self, mock_post, metadata_service):
        """Debe procesar múltiples documentos."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": json.dumps({
                "doc_type": "informe",
                "doc_year": 2024,
                "personas": [],
                "organizaciones": [],
                "lugares": [],
                "temas": [],
                "keywords": ["k1"],
                "summary": "Resumen"
            })
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        # Mock del persistence service
        mock_persistence = MagicMock()
        mock_persistence.get_document_by_id.return_value = {
            "id": 1,
            "filename": "doc.pdf",
            "processed_path": None  # Forzar que falle el procesamiento
        }

        result = metadata_service.classify_batch([1, 2, 3], mock_persistence)

        assert "total_processed" in result
        assert "total_failed" in result
