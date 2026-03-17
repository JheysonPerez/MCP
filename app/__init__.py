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
    chunk_service = ChunkService(chunk_size=300, overlap=50)
    embedding_service = EmbeddingService()
    retrieval_service = RetrievalService(embedding_service=embedding_service)
    # Inyectar chunk_service en rag_service
    rag_service = RagService(
        retrieval_service=retrieval_service, 
        chunk_service=chunk_service, 
        persistence_service=persistence
    )

    # Inyección de dependencias en el contexto global de app para poder consumirlos en app/routes.py
    app.db_conn = db_conn
    app.persistence = persistence
    app.document_service = document_service
    app.chunk_service = chunk_service
    app.retrieval_service = retrieval_service
    app.rag_service = rag_service
    
    # Sincronización Global del Repositorio al arrancar (Elimina la "amnesia")
    with app.app_context():
        try:
            app.rag_service.sync_repository_to_index()
        except Exception as e:
            print(f"[WARN] Error en la sincronización inicial: {e}")

    # Registrar Rutas
    with app.app_context():
        from . import routes

    return app
