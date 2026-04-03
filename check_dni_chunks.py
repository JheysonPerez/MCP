from db.connection import DatabaseConnection
from pgvector.psycopg2 import register_vector
from psycopg2.extras import RealDictCursor

db = DatabaseConnection()
conn = db.get_connection()
register_vector(conn)

with conn.cursor(cursor_factory=RealDictCursor) as cur:
    cur.execute("""
        SELECT chunk_index, chunk_text, 
               1 - (embedding <=> (
                   SELECT embedding FROM document_chunks 
                   WHERE document_id = 26 AND chunk_text LIKE '%75579282%'
                   LIMIT 1
               )) as self_score
        FROM document_chunks 
        WHERE document_id = 26 
        AND chunk_text LIKE '%75579282%'
    """)
    rows = cur.fetchall()
    for r in rows:
        print(f"Chunk {r['chunk_index']}: {r['chunk_text'][:200]}")

conn.close()
