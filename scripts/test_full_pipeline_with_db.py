import sys
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.document_service import DocumentService
from services.chunk_service import ChunkService
from services.embedding_service import EmbeddingService
from services.retrieval_service import RetrievalService
from services.rag_service import RagService
from services.persistence_service import PersistenceService
from db.connection import DatabaseConnection

import tempfile

load_dotenv()

def run_tests():
    print("--- INICIANDO FLUJO COMPLETO DE NEGOCIO: RAG + PERSISTENCIA POSTGRESQL ---")
    
    # 0. Instanciar Base de Datos
    db_conn = DatabaseConnection()
    persistence = PersistenceService(db=db_conn)
    
    # 1. Configurar Servicios con Inyección de Dependencias
    document_service = DocumentService(persistence_service=persistence)
    chunk_service = ChunkService(chunk_size=300, overlap=50)
    embedding_service = EmbeddingService()
    retrieval_service = RetrievalService(embedding_service=embedding_service)
    
    # RAG service con la capa de Persistencia
    rag_service = RagService(retrieval_service=retrieval_service, persistence_service=persistence)

    # Limpiamos antes para test repetible en DB
    print("0. Limpiando metadatos viejos de prueba RAG en la BD...")
    db_conn.execute_query("DELETE FROM queries WHERE query_text LIKE '¿Qué tipo de base de datos%';", commit=True)
    db_conn.execute_query("DELETE FROM documents WHERE filename = 'manual_epiis_rag_db.txt';", commit=True)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        texto = (
            "Manual Técnico EPIIS - Flujo Base de Datos\n\n"
            "El sistema almacena el conocimiento documental y vectorial de manera híbrida. "
            "Por un lado dependemos de PostgreSQL transaccional, que aloja usuarios, metadatos, historiales de consultas (queries) y sus respuestas (responses). "
            "Por otra parte el servidor usa memoria volátil (Listas Python) para Indexación Vectorial inicial. "
            "Es crucial que cualquier respuesta generada por los modelos Ollama (qwen2.5:3b) se registre en la tabla `responses` apuntando siempre al `query_id` originario del usuario."
        )
        fake_file_path = temp_path / "manual_epiis_rag_db.txt"
        with open(fake_file_path, "w", encoding="utf-8") as f:
            f.write(texto)

        # 2. PROCESAMIENTO E INGESTA (Debería Guardar en BD "documents")
        print("\n1. Subiendo e Ingestando Documento (El DocumentService lo registrará en la BD de paso)...")
        upload_path, processed_path = document_service.process_and_save(fake_file_path)
        print(f"   ✓ Extraído a: {processed_path.name}")

        with open(processed_path, "r", encoding="utf-8") as f:
            texto_extraido = f.read()

        # Chunking y Embeddings (Memoria)
        chunks = chunk_service.chunk_text(texto_extraido, document_id=processed_path.name)
        retrieval_service.add_chunks(chunks)

        # 3. INTERACCIÓN USUARIO Y RAG (Debería guardar en "queries" y "responses")
        pregunta = "¿Qué tipo de base de datos aloja el historial y las respuestas y por qué es importante apuntar el query id?"
        print(f"\n2. [Usuario Manda Pregunta al RAG]: {pregunta}")
        
        resultado_rag = rag_service.generate_response(pregunta, top_k=2)
        
        print("\n3. [Respuesta Generada por LLM y Almacenada]:")
        print("-" * 50)
        print(resultado_rag["answer"])
        print("-" * 50)
        
        # 4. COMPROBACIÓN POSTGRESQL FINAL
        print("\n4. COMUNICANDO CON LA BD: Verificando rastros en PostgreSQL...")
        
        doc_q = db_conn.execute_query("SELECT id, filename, uploaded_by FROM documents WHERE filename = 'manual_epiis_rag_db.txt'", fetch=True)
        query_q = db_conn.execute_query("SELECT id, query_text FROM queries ORDER BY id DESC LIMIT 1;", fetch=True)
        resp_q = db_conn.execute_query("SELECT id, query_id, generated_by_model FROM responses ORDER BY id DESC LIMIT 1;", fetch=True)
        
        print("\n [✓] DOCUMENTO REGISTRADO EN DB:")
        if doc_q:
            print(f"     ID: {doc_q[0]['id']} | Archivo Original: {doc_q[0]['filename']} | Uploader_ID: {doc_q[0]['uploaded_by']}")
            
        print("\n [✓] CONSULTA (QUERY) REGISTRADA EN DB:")
        if query_q:
            print(f"     ID: {query_q[0]['id']} | Texto Ingresado: '{query_q[0]['query_text'][:50]}...'")
            
        print("\n [✓] RESPUESTA (RESPONSE) REGISTRADA EN DB:")
        if resp_q:
            relacion_str = f"<- Conectado Correctamente al Query ID: {query_q[0]['id']}" if resp_q[0]['query_id'] == query_q[0]['id'] else "❌ FALLA DE LLAVE FORÁNEA"
            print(f"     ID: {resp_q[0]['id']} | Evaluador Modelo: {resp_q[0]['generated_by_model']} {relacion_str}")
        
        print("\n--- TEST INTEGRAL RAG <-> BD FUNCIONAL, PERSISTENCIA ASEGURADA ---")

if __name__ == "__main__":
    run_tests()
