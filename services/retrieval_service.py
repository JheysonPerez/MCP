import math
from typing import List, Dict
from pgvector.psycopg2 import register_vector
from db.connection import DatabaseConnection
from services.embedding_service import EmbeddingService
from services.rerank_service import RerankService
from services.hybrid_search_service import HybridSearchService

class RetrievalService:
    def __init__(self, embedding_service: EmbeddingService, rerank_service: RerankService = None, hybrid_service: HybridSearchService = None):
        self.embedding_service = embedding_service
        self.rerank_service = rerank_service or RerankService()
        self.hybrid_service = hybrid_service or HybridSearchService()
        self.db = DatabaseConnection()

    def add_chunks(self, chunks: List[Dict]):
        """
        Genera embeddings y los persiste en la tabla document_chunks de PostgreSQL.
        Utiliza las llaves: 'text', 'document_id', 'chunk_index' y 'filename'.
        """
        conn = self.db.get_connection()
        register_vector(conn)
        try:
            with conn.cursor() as cur:
                for chunk in chunks:
                    embedding = self.embedding_service.get_embedding(chunk["text"])
                    cur.execute("""
                        INSERT INTO document_chunks
                        (document_id, filename, chunk_index, chunk_text, embedding)
                        VALUES (%s, %s, %s, %s, %s);
                    """, (
                        chunk["document_id"],
                        chunk.get("filename", "Desconocido"),
                        chunk["chunk_index"],
                        chunk["text"],
                        embedding
                    ))
            conn.commit()
        finally:
            conn.close()

    def remove_document_chunks(self, document_id: str | int):
        """
        Elimina permanentemente los chunks de un documento de la base de datos.
        """
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM document_chunks WHERE document_id = %s;", (document_id,))
            conn.commit()
        finally:
            conn.close()

    def clear_all_chunks(self):
        """
        Limpia completamente el índice vectorial.
        """
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("TRUNCATE TABLE document_chunks;")
            conn.commit()
        finally:
            conn.close()

    def search(self, query: str, top_k: int = 6, document_id: str = None, 
               boost_id: str = None, use_rerank: bool = True, 
               use_hybrid: bool = True, min_score: float = 0.40,
               sql_threshold: float = 0.35, query_type: str = "general") -> List[Dict]:
        """
        Realiza una búsqueda de similitud coseno nativa en PostgreSQL.
        Umbral SQL: 0.35 (más estricto para calidad).
        Post-rerank filter: 0.40 (elimina chunks de baja calidad).
        Fallback automático a 0.25 si no hay resultados.
        """
        # 1. Recuperar más chunks inicialmente para re-ranking
        retrieval_k = top_k * 4 if (use_rerank or use_hybrid) else top_k
        
        query_embedding = self.embedding_service.get_embedding(query)
        conn = self.db.get_connection()
        register_vector(conn)

        from psycopg2.extras import RealDictCursor

        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                sql = """
                    SELECT document_id, filename, chunk_index, chunk_text,
                           1 - (embedding <=> %s::vector) AS score
                    FROM document_chunks
                    WHERE (1 - (embedding <=> %s::vector)) > %s
                """
                params = [query_embedding, query_embedding, sql_threshold]

                if document_id:
                    sql += " AND document_id = %s"
                    params.append(document_id)

                sql += " ORDER BY score DESC LIMIT %s;"
                params.append(retrieval_k)

                cur.execute(sql, params)
                rows = cur.fetchall()

                results = []
                for row in rows:
                    score = row['score']
                    if boost_id and str(row['document_id']) == str(boost_id):
                        score = min(1.0, score * 1.2)

                    results.append({
                        "document_id": row['document_id'],
                        "filename": row['filename'],
                        "chunk_index": row['chunk_index'],
                        "text": row['chunk_text'],
                        "score": score
                    })

                results.sort(key=lambda x: x["score"], reverse=True)
                
                # 2. Aplicar búsqueda híbrida si está habilitada
                if use_hybrid and len(results) > 3:
                    print(f"[HYBRID] Aplicando búsqueda híbrida a {len(results)} chunks...")
                    results = self.hybrid_service.hybrid_search(
                        query, results, top_k=len(results), query_type=query_type
                    )
                    print(f"[HYBRID] Búsqueda híbrida completada")
                
                # 3. Aplicar re-ranking si está habilitado y hay suficientes resultados
                if use_rerank and len(results) > top_k:
                    print(f"[RERANK] Re-rankeando {len(results)} chunks para query: {query[:50]}...")
                    results = self.rerank_service.rerank(query, results, top_k=top_k)
                    print(f"[RERANK] Retornando top {len(results)} chunks re-rankeados")
                
                # 4. FILTRO POST-RERANK: Eliminar chunks con score < min_score (default 0.40)
                filtered_results = [r for r in results if r['score'] >= min_score]
                print(f"[FILTER] Post-rerank: {len(results)} -> {len(filtered_results)} chunks (umbral {min_score})")
                
                # 5. FALLBACK AUTOMÁTICO: Si 0 resultados, reintentar con umbral más bajo (0.25)
                if len(filtered_results) == 0 and sql_threshold > 0.25:
                    print(f"[FALLBACK] 0 resultados con umbral {sql_threshold}, reintentando con 0.25...")
                    return self.search(
                        query=query,
                        top_k=top_k,
                        document_id=document_id,
                        boost_id=boost_id,
                        use_rerank=use_rerank,
                        use_hybrid=use_hybrid,
                        min_score=0.25,  # Bajar el filtro post-rerank también
                        sql_threshold=0.25  # Umbral SQL más permisivo
                    )
                
                return filtered_results[:top_k]
        finally:
            conn.close()

    def get_stats(self) -> Dict:
        """
        Obtiene estadísticas de ocupación del índice semántico.
        """
        conn = self.db.get_connection()
        from psycopg2.extras import RealDictCursor
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT COUNT(DISTINCT document_id) as total_docs,
                           COUNT(*) as total_chunks
                    FROM document_chunks;
                """)
                row = cur.fetchone()
                return {
                    "total_documents": row['total_docs'] if row['total_docs'] else 0,
                    "total_chunks": row['total_chunks'] if row['total_chunks'] else 0
                }
        finally:
            conn.close()
