import sys
from pathlib import Path
from dotenv import load_dotenv

# Ajustar el sys.path para importarlo desde /services de nuestro servidor actual
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.chunk_service import ChunkService
from services.embedding_service import EmbeddingService
from services.retrieval_service import RetrievalService

load_dotenv()

def run_tests():
    print("--- INICIANDO PRUEBAS DE CHUNKING Y BÚSQUEDA SEMÁNTICA ---")
    
    # 1. Configurar los servicios base
    # (Para el testo uso chunk size más pequeño para forzar los cortes visualmente)
    chunk_service = ChunkService(chunk_size=120, overlap=20)
    embedding_service = EmbeddingService()
    retrieval_service = RetrievalService(embedding_service=embedding_service)
    
    # Simular extraccion de texto "crudo" de DocumentService
    document_id = "memoria_institucional_test.txt"
    texto_documento = (
        "La EPIIS es una institución comprometida con la excelencia y la formación de profesionales competentes en el país. "
        "El servidor de Protocolo de Contexto de Modelos (MCP) que estamos construyendo permitirá gestionar los valiosos documentos de forma ágil e inteligente. "
        "La Inteligencia Artificial completamente local, implementada mediante la tecnología Ollama, se asegurará de resolver requerimientos complejos garantizando la seguridad sin salidas a la nube. "
        "Posteriormente planearemos el uso de la base de datos PostgreSQL, la cual nos apoyará almacenando todos los metadatos relevantes de los archivos o usuarios. "
        "Por ahora el modelo generativo de chat preferido es qwen2.5 de pocos parámetros (3b) para un excelente desempeño con recursos justos, mientras que los algoritmos de búsquedas consumirán embeddinggemma."
    )
    
    print(f"\n1. Dividiendo el documento '{document_id}' en pedazos pequeños...")
    chunks = chunk_service.chunk_text(texto_documento, document_id)
    print(f"  -> El ChunkService generó {len(chunks)} chunks de texto.")
    for c in chunks:
        print(f"     [Chunk {c['chunk_index']}]: {c['text'][:45].replace(chr(10), ' ')}...")
        
    print("\n2. Mandando los chunks hacia el EmbeddingService (Ollama) para su indexación en memoria...")
    retrieval_service.add_chunks(chunks)
    print("  -> Chunks convertidos a vectores y almacenados exitosamente.")
    
    # Realizar algunas consultas a ver qué recuperan
    consultas = [
        "¿Qué base de datos usaremos para guardar info de los archivos?",
        "Háblame de seguridad y privacidad en la IA local",
        "¿Cuáles son los modelos que usamos para chat y para buscar?"
    ]
    
    print("\n3. Lanzando el RetrievalService: Simulando extracción RAG (Búsqueda semántica) para cada consulta...")
    for q in consultas:
        print(f"\n  [?] Consulta: '{q}'")
        resultados = retrieval_service.search(query=q, top_k=2)
        
        for i, res in enumerate(resultados):
            print(f"      Top {i+1} | Score: {res['score']:.4f} | Origen: {res['document_id']} (idx: {res['chunk_index']})")
            print(f"      Fragmento: \"{res['text']}\"")
            print("      ---")
            
    print("\n--- ¡PIEZA DE RECUPERACIÓN (RETRIEVAL) PUESTA EN MARCHA EXISTOSAMENTE! ---")

if __name__ == "__main__":
    run_tests()
