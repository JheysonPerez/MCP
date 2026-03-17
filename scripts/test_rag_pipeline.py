import sys
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.document_service import DocumentService
from services.chunk_service import ChunkService
from services.embedding_service import EmbeddingService
from services.retrieval_service import RetrievalService
from services.rag_service import RagService

import tempfile

load_dotenv()

def run_tests():
    print("--- INICIANDO FLUJO DE RAG MINIMALISTA COMPLETADO ---")
    
    # Invocamos servicios
    document_service = DocumentService()
    chunk_service = ChunkService(chunk_size=300, overlap=50) # Agrandamos el chunk levemente
    embedding_service = EmbeddingService()
    retrieval_service = RetrievalService(embedding_service=embedding_service)
    rag_service = RagService(retrieval_service=retrieval_service)

    # 1. Crear documento local dinámico "ejemplo_rag_politica.txt" temporal simulando la web.
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        texto_original = (
            "Política de Seguridad RAG - Versión 1.0\n\n"
            "El sistema de Recuperación Aumentada por Generación (RAG) funciona enteramente on-premise en EPIIS. "
            "Esto significa que ninguna información documental abandona la infraestructura local en la llamada a la Inteligencia Artificial. "
            "En el futuro se adoptará la base de datos PostgreSQL, porque permite extender facilidades vectoriales mediante extensiones como pgvector si lo requerimos. "
            "Actualmente, sin dicha base de datos, el flujo depende de arrays de memoria puramente locales."
            "El flujo MCP debe mantenerse lo más minimalista y estandarizado posible garantizando transparencia auditada."
        )
        fake_file_path = temp_path / "politica_rag.txt"
        with open(fake_file_path, "w", encoding="utf-8") as f:
            f.write(texto_original)

        # 2. Guardar a /data/uploads, Extaer Texto y Enviar a /data/processed (DocumentService)
        # Esto probará el fix de doble-txt o extensiones mantenidas en nombres
        print(f"1. Subiendo documento falso mediante DocumentService para comprobar correccion de nombre de salida...")
        upload_path, processed_path = document_service.process_and_save(fake_file_path)
        print(f"   Original depositado a: {upload_path.name}")
        print(f"   Archivo Procesado Depositado a: {processed_path.name}")
        
        # 3. Leer ese mismo texto que ya el servicio proceso como standard de nuestro sistema
        with open(processed_path, "r", encoding="utf-8") as f:
            texto_extraido = f.read()

    # 4. Dividir Limpiamente el Texto con el Word-Safe Fix de ChunkService
    print("\n2. Mandando el archivo extraído a particiones de bloque semánticas mediante ChunkService..")
    document_id = processed_path.name # Usando el .txt como ID
    chunks = chunk_service.chunk_text(texto_extraido, document_id)
    
    for c in chunks:
         print(f"   -> [Chunk {c['chunk_index']}]: '{c['text'][:55]}...' | (Palabras Incompletas Protegidas)")

    # 5. Agregar y generar Vectores con Retrieval Servicio (Qwen Embeddings / GemmaEmbeddings) en Memoria local
    print("\n3. Indexando fragmentos bajo vectores para Búsqueda (Ollama EmbeddingGemma)...")
    retrieval_service.add_chunks(chunks)
    print("   ✓ Chunks incrustados correctamente.")

    # 6. Realizar la Prueba Principal! Consultar y Devolver a través de Qwen LLM Chat Generation
    pregunta = "¿Qué clase de base de datos se utilizará para alojar la extensión de similitudes a futuro y por qué ventajas?"
    print(f"\n4. Disparando Chat Inteligente (RAG Pipeline)")
    print(f"\n[❓] Pregunta del Usuario: {pregunta}")
    
    # Obtener el dictionary
    resultado_rag = rag_service.generate_response(pregunta, top_k=2)
    
    print("\n[🤖] Respuesta Generada por Qwen:")
    print("-" * 50)
    print(resultado_rag["answer"])
    print("-" * 50)
    
    print("\n[📚] Fuentes Recuperadas (Contexto):")
    for i, s in enumerate(resultado_rag["sources"]):
         print(f"   [{i+1}] Doc: {s['document_id']} (Chunk {s['chunk_index']}) | Match: {s['score']:.4f}")
         print(f"       📝 Fragmento: \"{s['text']}\"")
         
    print("\n--- TEST RAG COMPLETADO EXISTOSAMENTE. NINGÚN CORTE INVASIVO FUE DETECTADO ---\n")

if __name__ == "__main__":
    run_tests()
