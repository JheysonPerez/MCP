"""
Tests unitarios para PersistenceService.
"""
import pytest
from unittest.mock import MagicMock, patch
from services.persistence_service import PersistenceService


@pytest.fixture
def persistence_service():
    """Fixture del servicio de persistencia con DB mockeada."""
    with patch('services.persistence_service.DatabaseConnection') as mock_db_class:
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db

        service = PersistenceService()
        service.db = mock_db
        service._mock_db = mock_db

        yield service


class TestRegisterDocument:
    """Test suite para register_document()."""

    def test_registra_documento_nuevo(self, persistence_service):
        """Debe registrar nuevo documento en BD."""
        persistence_service._mock_db.execute_query.return_value = [{"id": 1}]

        result = persistence_service.register_document(
            filename="doc.pdf",
            original_path="/uploads/doc.pdf",
            processed_path="/processed/doc.txt",
            user_id=1
        )

        assert result == 1
        persistence_service._mock_db.execute_query.assert_called()


class TestCreateOrGetUser:
    """Test suite para create_or_get_user()."""

    def test_crea_usuario_nuevo(self, persistence_service):
        """Debe crear usuario si no existe."""
        persistence_service._mock_db.execute_query.side_effect = [
            [],  # SELECT no encuentra
            [{"id": 5}]  # INSERT retorna nuevo ID
        ]

        result = persistence_service.create_or_get_user("testuser", "test@test.com")

        assert result == 5

    def test_retorna_usuario_existente(self, persistence_service):
        """Debe retornar ID si usuario ya existe."""
        persistence_service._mock_db.execute_query.return_value = [{"id": 3}]

        result = persistence_service.create_or_get_user("existing", "existing@test.com")

        assert result == 3


class TestGetDocument:
    """Test suite para obtener documentos."""

    def test_get_document_by_id_existente(self, persistence_service):
        """Debe retornar documento por ID."""
        persistence_service._mock_db.execute_query.return_value = [
            {"id": 1, "filename": "doc.pdf", "doc_type": "certificado"}
        ]

        result = persistence_service.get_document_by_id(1)

        assert result is not None
        assert result["id"] == 1
        assert result["filename"] == "doc.pdf"

    def test_get_document_by_id_no_existente(self, persistence_service):
        """Debe retornar None si documento no existe."""
        persistence_service._mock_db.execute_query.return_value = []

        result = persistence_service.get_document_by_id(999)

        assert result is None

    def test_get_all_documents(self, persistence_service):
        """Debe retornar todos los documentos."""
        persistence_service._mock_db.execute_query.return_value = [
            {"id": 1, "filename": "doc1.pdf"},
            {"id": 2, "filename": "doc2.pdf"}
        ]

        result = persistence_service.get_all_documents()

        assert len(result) == 2

    def test_get_documents_by_type(self, persistence_service):
        """Debe filtrar documentos por tipo."""
        persistence_service._mock_db.execute_query.return_value = [
            {"id": 1, "filename": "cert1.pdf", "doc_type": "certificado", "doc_year": 2024},
            {"id": 2, "filename": "cert2.pdf", "doc_type": "certificado", "doc_year": 2023}
        ]

        result = persistence_service.get_documents_by_type("certificado")

        assert len(result) == 2
        assert all(d["doc_type"] == "certificado" for d in result)

    def test_get_documents_by_type_y_year(self, persistence_service):
        """Debe filtrar por tipo y año."""
        persistence_service._mock_db.execute_query.return_value = [
            {"id": 1, "filename": "cert2024.pdf", "doc_type": "certificado", "doc_year": 2024}
        ]

        result = persistence_service.get_documents_by_type("certificado", doc_year=2024)

        assert len(result) == 1
        assert result[0]["doc_year"] == 2024


class TestUpdateDocumentMetadata:
    """Test suite para update_document_metadata()."""

    def test_actualiza_metadatos(self, persistence_service):
        """Debe actualizar metadatos del documento."""
        metadata = {
            "doc_type": "certificado",
            "doc_year": 2024,
            "keywords": ["certificado", "trabajo"],
            "summary": "Resumen del documento"
        }

        persistence_service.update_document_metadata(1, metadata)

        persistence_service._mock_db.update_document_metadata.assert_called()

    def test_actualiza_entities_json(self, persistence_service):
        """Debe convertir entities a JSON."""
        metadata = {
            "extracted_entities": {
                "personas": ["Juan Pérez"],
                "organizaciones": ["UNAS"]
            }
        }

        persistence_service.update_document_metadata(5, metadata)

        call_args = persistence_service._mock_db.update_document_metadata.call_args
        assert "extracted_entities" in str(call_args)


class TestDeleteOperations:
    """Test suite para operaciones de borrado."""

    def test_delete_document_existente(self, persistence_service):
        """Debe eliminar documento y sus archivos."""
        persistence_service._mock_db.execute_query.return_value = [
            {"id": 1, "original_path": "/tmp/doc.pdf", "processed_path": "/tmp/doc.txt"}
        ]

        with patch('os.path.exists') as mock_exists:
            mock_exists.return_value = True
            with patch('os.remove') as mock_remove:
                result = persistence_service.delete_document(1)

        assert result is True
        persistence_service._mock_db.execute_query.assert_called()

    def test_delete_document_no_existente(self, persistence_service):
        """Debe retornar False si documento no existe."""
        persistence_service._mock_db.execute_query.return_value = []

        result = persistence_service.delete_document(999)

        assert result is False


class TestGetDocumentsWithoutMetadata:
    """Test suite para get_documents_without_metadata()."""

    def test_retorna_documentos_sin_metadatos(self, persistence_service):
        """Debe retornar documentos que necesitan extracción."""
        persistence_service._mock_db.execute_query.return_value = [
            {"id": 1, "filename": "doc1.pdf", "processed_path": "/tmp/1.txt"},
            {"id": 2, "filename": "doc2.pdf", "processed_path": "/tmp/2.txt"}
        ]

        result = persistence_service.get_documents_without_metadata()

        assert len(result) == 2
        assert "doc1.pdf" in str(result)


class TestResetIndexing:
    """Test suite para reset_indexing_metadata()."""

    def test_reset_indexing(self, persistence_service):
        """Debe resetear estado de indexación."""
        persistence_service.reset_indexing_metadata(1)

        persistence_service._mock_db.update_document_metadata.assert_called_with(
            1,
            is_indexed=False,
            chunk_count=0,
            last_indexed_at=None
        )


class TestUpdateStatus:
    """Test suite para update_document_status()."""

    def test_update_processing_status(self, persistence_service):
        """Debe actualizar estado de procesamiento."""
        persistence_service.update_document_status(1, processing_status="completed")

        persistence_service._mock_db.update_document_metadata.assert_called()

    def test_update_indexed_status(self, persistence_service):
        """Debe marcar documento como indexado."""
        persistence_service.update_document_status(1, is_indexed=True, chunk_count=15)

        persistence_service._mock_db.update_document_metadata.assert_called_with(
            1,
            is_indexed=True,
            chunk_count=15
        )

    def test_update_con_error_log(self, persistence_service):
        """Debe guardar mensaje de error."""
        persistence_service.update_document_status(1, error_log="Error procesando")

        persistence_service._mock_db.update_document_metadata.assert_called()


class TestRegisterQueryResponse:
    """Test suite para registro de queries y respuestas."""

    def test_register_query(self, persistence_service):
        """Debe registrar consulta del usuario."""
        persistence_service._mock_db.execute_query.return_value = [{"id": 100}]

        result = persistence_service.register_query(1, "¿Qué documentos hay?")

        assert result == 100
        persistence_service._mock_db.execute_query.assert_called()

    def test_register_response(self, persistence_service):
        """Debe registrar respuesta del LLM."""
        persistence_service._mock_db.execute_query.return_value = [{"id": 200}]

        result = persistence_service.register_response(100, "Respuesta del sistema", "qwen2.5:3b")

        assert result == 200

    def test_register_generated_document(self, persistence_service):
        """Debe registrar documento generado."""
        persistence_service._mock_db.execute_query.return_value = [{"id": 300}]

        result = persistence_service.register_generated_document(200, "Contenido generado", "txt")

        assert result == 300
