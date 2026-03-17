import sys
from pathlib import Path

# Permitir importaciones de nuestra carpeta modules "services" y "db"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.connection import DatabaseConnection
from services.persistence_service import PersistenceService
from services.document_service import DocumentService
from services.chunk_service import ChunkService
from services.embedding_service import EmbeddingService
from services.retrieval_service import RetrievalService
from services.rag_service import RagService

# Instanciamos dependencias base para inyectar globalmente a los tools de MCP
db_conn = DatabaseConnection()
persistence = PersistenceService(db=db_conn)

document_service = DocumentService(persistence_service=persistence)

# Asumimos que los documentos ya están ingestados para el contexto de consulta base.
# Si el backend sube nuevos, simplemente se irán acumulando en DB y memoria.
chunk_service = ChunkService(chunk_size=300, overlap=50)
embedding_service = EmbeddingService()
retrieval_service = RetrievalService(embedding_service=embedding_service)

rag_service = RagService(retrieval_service=retrieval_service, persistence_service=persistence)

# Como el in-memory list (retrieval_service.chunks_db) arranca vacío si no cargamos los archivos de los folders,
# vamos a hacer un reload mock-up automático al iniciar el servidor (MVP).
def load_all_processed_docs_to_memory():
    """ 
    Lee todos los .txt en data/processed/ y los lanza al retriever. 
    En Producción Real(pgvector) esto no será necesario.
    """
    for file_path in document_service.processed_dir.glob("*.txt"):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                 text = f.read()
            chunks = chunk_service.chunk_text(text, document_id=file_path.name)
            retrieval_service.add_chunks(chunks)
        except Exception:
            pass

load_all_processed_docs_to_memory()
