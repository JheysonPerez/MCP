from flask import Flask
from pathlib import Path
import os
from dotenv import load_dotenv

# Importar los servicios principales de la arquitectura Python (RAG / DB)
from db.connection import DatabaseConnection
from services.persistence_service import PersistenceService
from services.document_service import DocumentService
from services.chunk_service import ChunkService
from services.embedding_service import EmbeddingService
from services.retrieval_service import RetrievalService
from services.rag_service import RagService
from services.generation_service import GenerationService
from services.user_service import UserService
from services.rerank_service import RerankService
from services.hybrid_search_service import HybridSearchService

load_dotenv()

def create_app():
    # Inicializar la aplicación Flask señalando a esta ruta para buscar static y templates
    app = Flask(__name__)
    
    # Configuración base (El SECRET_KEY está en .env, necesario para manejo de Sesiones HTTP seguras)
    app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY", "fallback_local_secret_epiis")
    
    # === Instanciar dependencias de Back-End (Igual que en test o MCP) ===
    db_conn = DatabaseConnection()
    persistence = PersistenceService(db=db_conn)
    
    document_service = DocumentService(persistence_service=persistence)
    chunk_service = ChunkService(chunk_size=800, overlap=100)
    embedding_service = EmbeddingService()
    
    rerank_service = RerankService()
    hybrid_service = HybridSearchService()
    retrieval_service = RetrievalService(
        embedding_service=embedding_service,
        rerank_service=rerank_service,
        hybrid_service=hybrid_service
    )
    # Inyectar chunk_service en rag_service
    rag_service = RagService(
        retrieval_service=retrieval_service, 
        chunk_service=chunk_service, 
        persistence_service=persistence
    )

    generation_service = GenerationService(
        retrieval_service=retrieval_service,
        persistence_service=persistence
    )
    
    user_service = UserService(db_connection=db_conn)

    # Inyección de dependencias en el contexto global de app para poder consumirlos en app/routes.py
    app.db_conn = db_conn
    app.persistence = persistence
    app.document_service = document_service
    app.chunk_service = chunk_service
    app.retrieval_service = retrieval_service
    app.rerank_service = rerank_service
    app.hybrid_service = hybrid_service
    app.rag_service = rag_service
    app.generation_service = generation_service
    app.user_service = user_service

    # Registrar Rutas
    with app.app_context():
        from . import routes

    return app
