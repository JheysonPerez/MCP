import math
from typing import List, Dict
from pgvector.psycopg2 import register_vector
from db.connection import DatabaseConnection
from services.embedding_service import EmbeddingService

class RetrievalService:
    def __init__(self, embedding_service: EmbeddingService):
        self.embedding_service = embedding_service
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

    def search(self, query: str, top_k: int = 6, document_id: str = None, boost_id: str = None) -> List[Dict]:
        """
        Realiza una búsqueda de similitud coseno nativa en PostgreSQL.
        Filtra por un score mínimo de 0.35 y opcionalmente por document_id.
        """
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
                    WHERE (1 - (embedding <=> %s::vector)) > 0.35
                """
                params = [query_embedding, query_embedding]

                if document_id:
                    sql += " AND document_id = %s"
                    params.append(document_id)

                sql += " ORDER BY score DESC LIMIT %s;"
                params.append(top_k)

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
                return results[:top_k]
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
