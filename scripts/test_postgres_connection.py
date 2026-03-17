import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Enrutar el sistema temporalmente a la base del proyecto
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.connection import DatabaseConnection

load_dotenv()

def run_tests():
    print("--- INICIANDO PRUEBAS DE CONEXIÓN POSTGRESQL ---")

    try:
        # 1. Verificar Conexión
        print("\n1. Probando conexión con DB...")
        db = DatabaseConnection()
        
        # Test de consulta hiper-básica de base de datos para asegurar el ping
        version_resp = db.execute_query("SELECT version();", fetch=True)
        print(f"  ✓ Conexión Exitosamente Establecida a: {version_resp[0]['version'][:40]}...")

        # 2. Imprimir archivo esquema e Instanciar base (Crear Tablas si no existen)
        schema_path = Path(__file__).resolve().parent.parent / "db" / "schema.sql"
        print(f"\n2. Verificando y creando estructura de tablas desde '{schema_path.name}'...")
        db.execute_script(str(schema_path))
        
        # 3. Limpiar base por si corremos los tests varias veces (para no colapsar la unicidad de usuarios)
        print("\n   Limpiando datos de prueba anteriores...")
        db.execute_query("DELETE FROM documents WHERE filename = 'prueba_db.pdf';", commit=True)
        db.execute_query("DELETE FROM users WHERE username = 'admin_prueba';", commit=True)

        # 4. Inserciones de registros de Prueba
        print("\n3. Insertando registro de Usuario Administrador Ficticio...")
        insert_user_query = "INSERT INTO users (username, email) VALUES (%s, %s) RETURNING id;"
        new_user = db.execute_query(insert_user_query, ("admin_prueba", "admin@epiis.local"), fetch=True, commit=True)
        user_id = new_user[0]['id']
        print(f"  ✓ Usuario de Test creado con ID: {user_id}")

        print("\n4. Insertando registro de Documento asociándolo al usuario...")
        insert_doc_query = """
            INSERT INTO documents (filename, original_path, processed_path, uploaded_by) 
            VALUES (%s, %s, %s, %s) RETURNING id;
        """
        new_doc = db.execute_query(
            insert_doc_query, 
            ("prueba_db.pdf", "/tmp/prueba_db.pdf", "data/processed/prueba_db.pdf.txt", user_id), 
            fetch=True, 
            commit=True
        )
        doc_id = new_doc[0]['id']
        print(f"  ✓ Documento de Test creado y almacenado con ID: {doc_id}")

        # 5. Consulta y Recuperación del Registro Insertado
        print("\n5. Consultando y extrayendo registro final desde la variable relacional persistida...")
        select_query = """
            SELECT d.id, d.filename, d.processed_path, u.username as propietario
            FROM documents d
            JOIN users u ON d.uploaded_by = u.id
            WHERE d.id = %s;
        """
        registro = db.execute_query(select_query, (doc_id,), fetch=True)
        
        print("\n  [RESULTADOS DE SQL EXTRACT]:")
        for k, v in registro[0].items():
            print(f"    - {k}: {v}")
            
        print("\n--- ¡BASE DE DATOS POSTGRESQL TOTAL Y COMPLETAMENTE FUNCIONAL Y CONECTADA! ---")

    except Exception as e:
        print(f"\n❌ Error General del Pipeline de Prueba Base de Datos: {e}")

if __name__ == "__main__":
    run_tests()
