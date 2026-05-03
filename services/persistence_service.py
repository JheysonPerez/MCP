import sys
import os
from pathlib import Path
from typing import Dict, Any, Optional, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.connection import DatabaseConnection

class PersistenceService:
    def __init__(self, db: DatabaseConnection = None):
        """
        Servicio centralizado para manejar el guardado de estado en PostgreSQL
        en las distintas etapas del pipeline.
        """
        self.db = db if db else DatabaseConnection()

    def create_or_get_user(self, username: str, email: str) -> int:
        """
        Asegura que exista un usuario para relacionar los datos en el flujo.
        Devuelve el ID.
        """
        query = "SELECT id FROM users WHERE username = %s OR email = %s LIMIT 1"
        result = self.db.execute_query(query, (username, email), fetch=True)
        
        if result:
            return result[0]['id']
            
        # Si no existe, crearlo
        insert_query = "INSERT INTO users (username, email) VALUES (%s, %s) RETURNING id;"
        new_user = self.db.execute_query(insert_query, (username, email), fetch=True, commit=True)
        return new_user[0]['id']

    def register_document(self, filename: str, original_path: str, processed_path: str, user_id: int) -> int:
        """
        Guarda el registro inicial de un documento procesado en la tabla `documents`.
        """
        query = """
            INSERT INTO documents (filename, original_path, processed_path, uploaded_by, processing_status) 
            VALUES (%s, %s, %s, %s, 'pending') RETURNING id;
        """
        result = self.db.execute_query(
            query, (filename, original_path, processed_path, user_id), 
            fetch=True, commit=True
        )
        return result[0]['id']

    def update_document_status(self, doc_id: int, **kwargs):
        """
        Actualiza los metadatos de un documento (processing_status, is_indexed, etc).
        """
        self.db.update_document_metadata(doc_id, **kwargs)

    def update_document_metadata(self, doc_id: int, metadata: dict):
        """
        Actualiza los metadatos extraídos automáticamente de un documento.
        Incluye: doc_type, doc_date, doc_year, extracted_entities, keywords, summary, etc.
        """
        # Preparar los campos para actualización
        update_fields = {}

        if "doc_type" in metadata:
            update_fields["doc_type"] = metadata["doc_type"]
        if "doc_date" in metadata:
            update_fields["doc_date"] = metadata["doc_date"]
        if "doc_year" in metadata:
            update_fields["doc_year"] = metadata["doc_year"]
        if "extracted_entities" in metadata:
            import json
            update_fields["extracted_entities"] = json.dumps(metadata["extracted_entities"])
        if "keywords" in metadata:
            update_fields["keywords"] = metadata["keywords"]
        if "summary" in metadata:
            update_fields["summary"] = metadata["summary"]
        if "classification_confidence" in metadata:
            update_fields["classification_confidence"] = metadata["classification_confidence"]
        if "metadata_extraction_failed" in metadata:
            update_fields["metadata_extraction_failed"] = metadata["metadata_extraction_failed"]

        if update_fields:
            self.db.update_document_metadata(doc_id, **update_fields)
            print(f"[OK] Metadatos guardados para documento {doc_id}")

    def get_documents_without_metadata(self) -> list:
        """
        Obtiene documentos indexados que aún no tienen metadatos extraídos.
        Útil para procesamiento batch.
        """
        query = """
            SELECT id, filename, processed_path
            FROM documents
            WHERE is_indexed = TRUE
              AND (doc_type IS NULL OR metadata_extraction_failed = TRUE)
            ORDER BY created_at ASC;
        """
        return self.db.execute_query(query, fetch=True)

    def get_all_documents(self) -> List[Dict]:
        """
        Obtiene todos los documentos registrados sin filtrar por estado.
        Útil para auditorías y sincronización global.
        """
        query = "SELECT * FROM documents ORDER BY created_at DESC;"
        return self.db.execute_query(query, fetch=True)

    def get_all_completed_documents(self) -> List[Dict]:
        """
        Obtiene solo los documentos procesados con éxito.
        """
        query = "SELECT * FROM documents WHERE processing_status = 'completed';"
        return self.db.execute_query(query, fetch=True)

    def get_document_by_id(self, doc_id: int) -> Optional[Dict]:
        """
        Obtiene toda la información de un documento por su ID.
        """
        query = "SELECT * FROM documents WHERE id = %s;"
        result = self.db.execute_query(query, (doc_id,), fetch=True)
        return result[0] if result else None

    def get_documents_by_type(self, doc_type: str, doc_year: int = None) -> List[Dict]:
        """
        Obtiene documentos filtrados por tipo (y opcionalmente por año).
        Útil para listar documentos cuando hay múltiples del mismo tipo.
        """
        if doc_year:
            query = """
                SELECT id, filename, doc_year, summary
                FROM documents
                WHERE doc_type = %s AND doc_year = %s AND is_indexed = TRUE
                ORDER BY doc_year DESC NULLS LAST, filename ASC;
            """
            return self.db.execute_query(query, (doc_type, doc_year), fetch=True)
        else:
            query = """
                SELECT id, filename, doc_year, summary
                FROM documents
                WHERE doc_type = %s AND is_indexed = TRUE
                ORDER BY doc_year DESC NULLS LAST, filename ASC;
            """
            return self.db.execute_query(query, (doc_type,), fetch=True)

    def reset_indexing_metadata(self, doc_id: int):
        """
        Limpia los campos de indexación de un documento para corregir inconsistencias.
        """
        self.db.update_document_metadata(
            doc_id,
            is_indexed=False,
            chunk_count=0,
            last_indexed_at=None
        )

    def delete_document(self, doc_id: int) -> bool:
        """
        Elimina un documento de la base de datos y sus archivos físicos asociados.
        """
        doc = self.get_document_by_id(doc_id)
        if not doc:
            return False
            
        # 1. Eliminar archivos físicos
        for path_key in ['original_path', 'processed_path']:
            path_str = doc.get(path_key)
            if path_str and os.path.exists(path_str):
                try:
                    os.remove(path_str)
                except Exception as e:
                    print(f"[WARN] No se pudo eliminar el archivo {path_str}: {e}")
        
        # 2. Eliminar de la base de datos
        # Las tablas responses, generated_documents, etc. deberían tener ON DELETE CASCADE si están vinculadas,
        # pero por ahora eliminamos el documento principal.
        query = "DELETE FROM documents WHERE id = %s;"
        self.db.execute_query(query, (doc_id,), commit=True)
        return True

    def register_query(self, user_id: int, query_text: str) -> int:
        """
        Registra la consulta (pregunta) que hace el usuario al RAG.
        """
        query = "INSERT INTO queries (user_id, query_text) VALUES (%s, %s) RETURNING id;"
        result = self.db.execute_query(query, (user_id, query_text), fetch=True, commit=True)
        return result[0]['id']

    def register_response(self, query_id: int, response_text: str, model_name: str) -> int:
        """
        Asocia la respuesta generativa por el LLM a una pregunta.
        """
        query = """
            INSERT INTO responses (query_id, response_text, generated_by_model) 
            VALUES (%s, %s, %s) RETURNING id;
        """
        result = self.db.execute_query(
            query, (query_id, response_text, model_name), 
            fetch=True, commit=True
        )
        return result[0]['id']

    def register_generated_document(self, response_id: int, content: str, doc_format: str = "txt") -> int:
        """
        Guarda un documento secundario de salida derivado de la inferencia IA.
        """
        query = """
            INSERT INTO generated_documents (response_id, document_content, format) 
            VALUES (%s, %s, %s) RETURNING id;
        """
        result = self.db.execute_query(
            query, (response_id, content, doc_format), 
            fetch=True, commit=True
        )
        return result[0]['id']
