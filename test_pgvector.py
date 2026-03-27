import sys
sys.path.insert(0, '.')

from db.connection import DatabaseConnection
from pgvector.psycopg2 import register_vector
from services.embedding_service import EmbeddingService

db = DatabaseConnection()

print("--- Prueba 1: Extensión pgvector ---")
try:
    conn = db.get_connection()
    register_vector(conn)
    cur = conn.cursor()
    cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector';")
    row = cur.fetchone()
    print(f"✅ pgvector activo: {row[0]}" if row else "❌ Extensión no encontrada")
    conn.close()
except Exception as e:
    print(f"❌ Error: {e}")

print("\n--- Prueba 2: Tabla document_chunks ---")
try:
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'document_chunks' ORDER BY ordinal_position;
    """)
    cols = [r[0] for r in cur.fetchall()]
    print(f"✅ Columnas: {cols}" if cols else "❌ Tabla no encontrada")
    conn.close()
except Exception as e:
    print(f"❌ Error: {e}")

print("\n--- Prueba 3: Escritura y lectura ---")
try:
    emb = EmbeddingService()
    vector = emb.get_embedding("prueba de conexión pgvector")
    conn = db.get_connection()
    register_vector(conn)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO document_chunks (document_id, filename, chunk_index, chunk_text, embedding)
        VALUES (NULL, 'test', 0, 'prueba de conexión pgvector', %s) RETURNING id;
    """, (vector,))
    test_id = cur.fetchone()[0]
    cur.execute("""
        SELECT 1 - (embedding <=> %s::vector) AS score
        FROM document_chunks WHERE id = %s;
    """, (vector, test_id))
    score = cur.fetchone()[0]
    cur.execute("DELETE FROM document_chunks WHERE id = %s;", (test_id,))
    conn.commit()
    conn.close()
    print(f"✅ Escritura/lectura OK, score: {score:.4f}")
except Exception as e:
    print(f"❌ Error: {e}")

print("\n--- Prueba 4: Stats ---")
try:
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(DISTINCT document_id) AS total_documents,
               COUNT(*) AS total_chunks
        FROM document_chunks;
    """)
    row = cur.fetchone()
    print(f"✅ Documentos: {row[0]}, Chunks: {row[1]}")
    conn.close()
except Exception as e:
    print(f"❌ Error: {e}")
