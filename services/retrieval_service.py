import math
from typing import List, Dict
from services.embedding_service import EmbeddingService

def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """
    KISS: Utiliza matemática estándar de Python para evitar la carga temporal de numpy en esta prueba de MVP.
    Compara dos vectores y devuelve la similitud coseno (-1.0 a 1.0).
    """
    dot_product = sum(a * b for a, b in zip(v1, v2))
    norm_a = math.sqrt(sum(a * a for a in v1))
    norm_b = math.sqrt(sum(b * b for b in v2))
    
    if norm_a == 0 or norm_b == 0:
        return 0.0
        
    return dot_product / (norm_a * norm_b)


class RetrievalService:
    def __init__(self, embedding_service: EmbeddingService):
        self.embedding_service = embedding_service
        # Estructura en memoria temporal para almacenar los chunks y sus vectores antes
        # de usar una base de datos compleja (ej. PostgreSQL + pgvector)
        self.chunks_db: List[Dict] = []

    def add_chunks(self, chunks: List[Dict]):
        """
        Por cada chunk entrante de texto, se genera el embedding y se guarda en la "BD" de memoria.
        Cada registro ahora incluye el filename para visualización directa.
        """
        for chunk in chunks:
            text = chunk["text"]
            embedding = self.embedding_service.get_embedding(text)
            
            chunk_record = {
                "document_id": chunk["document_id"],
                "filename": chunk.get("filename", "Desconocido"),
                "chunk_index": chunk["chunk_index"],
                "text": text,
                "embedding": embedding
            }
            self.chunks_db.append(chunk_record)

    def remove_document_chunks(self, document_id: str | int):
        """
        Elimina de la memoria todos los chunks pertenecientes a un documento.
        """
        doc_id_str = str(document_id)
        self.chunks_db = [c for c in self.chunks_db if str(c["document_id"]) != doc_id_str]

    def clear_all_chunks(self):
        """
        Limpia completamente el índice en memoria.
        """
        self.chunks_db = []

    def search(self, query: str, top_k: int = 3, document_id: str = None, boost_id: str = None) -> List[Dict]:
        """
        1. Embebe la consulta de búsqueda.
        2. La compara con el embedding de cada iteración en chunks_db.
        3. Aplica boost si el documento coincide con boost_id.
        4. Ordena los resultados usando el score y los devuelve.
        """
        query_embedding = self.embedding_service.get_embedding(query)
        
        results = []
        for record in self.chunks_db:
            # Filtro duro (si aplica)
            if document_id and str(record["document_id"]) != str(document_id):
                continue
                
            # Calcular similitud base
            score = cosine_similarity(query_embedding, record["embedding"])
            
            # Aplicar BOOST (si aplica)
            # Si el documento coincide con el boost_id, aumentamos su relevancia un 20%
            if boost_id and str(record["document_id"]) == str(boost_id):
                score = min(1.0, score * 1.2)
            
            results.append({
                "document_id": record["document_id"],
                "filename": record["filename"],
                "chunk_index": record["chunk_index"],
                "score": score,
                "text": record["text"]
            })
            
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]
