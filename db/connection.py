import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

class DatabaseConnection:
    def __init__(self):
        """
        Inicializa la conexión a PostgreSQL usando la variable 'DATABASE_URL' definida en el archivo .env.
        No requiere modificar URLs ni contraseñas hardkodeadas, usa el standard de Postgres URI.
        """
        self.db_url = os.environ.get("DATABASE_URL")
        
        if not self.db_url:
            raise ValueError("La variable DATABASE_URL no se encontró en el entorno.")

    def get_connection(self):
        """
        Crea y devuelve una conexión nueva a la base de datos.
        Asegúrate de cerrarla después de usarla (conn.close()).
        """
        try:
            conn = psycopg2.connect(self.db_url)
            return conn
        except psycopg2.OperationalError as e:
            print(f"[ERROR] Error conectando a PostgreSQL. Verifica que la base de datos esté activa: {e}")
            raise

    def execute_query(self, query: str, params: tuple = None, fetch: bool = False, commit: bool = False):
        """
        Ejecuta una consulta SQL en un cursor.
        fetch: si es True, hace un fetchall() de los resultados.
        commit: si es True, hace commit de los cambios a la base (necesario para INSERT/UPDATE).
        Devuelve list[dict] si fetch=True, gracias a RealDictCursor.
        """
        conn = self.get_connection()
        # Usamos RealDictCursor para que las respuestas sean diccionarios (columna: valor)
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                
                if commit:
                    conn.commit()
                    
                if fetch:
                    return cursor.fetchall()
                return None
        finally:
             conn.close()

    def execute_script(self, script_path: str):
        """
        Ejecuta un archivo de script .sql completo, útil para crear las tablas desde db/schema.sql.
        """
        with open(script_path, 'r', encoding='utf-8') as file:
            sql_script = file.read()
            
        conn = self.get_connection()
        try:
             with conn.cursor() as cursor:
                 cursor.execute(sql_script)
             conn.commit()
             print(f"[OK] Script '{os.path.basename(script_path)}' ejecutado correctamente.")
        except Exception as e:
             conn.rollback()
             print(f"[ERROR] Falló al intentar ejecutar el script: {e}")
        finally:
             conn.close()

    def update_document_metadata(self, doc_id: int, **kwargs):
        """
        Actualiza dinámicamente campos en la tabla 'documents'.
        Ejemplo: update_document_metadata(1, processing_status='completed', is_indexed=True)
        """
        if not kwargs:
            return
            
        fields = ", ".join([f"{k} = %s" for k in kwargs.keys()])
        values = list(kwargs.values())
        values.append(doc_id)
        
        query = f"UPDATE documents SET {fields} WHERE id = %s"
        self.execute_query(query, tuple(values), commit=True)
