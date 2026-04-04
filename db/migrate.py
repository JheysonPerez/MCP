#!/usr/bin/env python3
"""
Sistema de Migraciones Automático para MCP-DOCS

Este script verifica el estado actual de la base de datos y ejecuta
automáticamente las migraciones necesarias para que el proyecto funcione.

Uso:
    python db/migrate.py              # Ejecutar migraciones completas
    python db/migrate.py --check      # Solo verificar estado
    python db/migrate.py --verify     # Verificar que todo esté listo
    python db/migrate.py --status     # Mostrar estado detallado
"""

import os
import sys
import argparse
from pathlib import Path

# Agregar directorio padre al path para importar módulos del proyecto
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.connection import DatabaseConnection
from dotenv import load_dotenv

load_dotenv()


def execute_sql_safely(db: DatabaseConnection, sql: str, description: str) -> bool:
    """Ejecuta SQL capturando errores específicos"""
    try:
        db.execute_query(sql, commit=True)
        print(f"✅ {description}")
        return True
    except Exception as e:
        # Si el error es porque ya existe, lo consideramos éxito
        error_str = str(e).lower()
        if any(x in error_str for x in ['already exists', 'duplicate', 'exists']):
            print(f"✅ {description} (ya existía)")
            return True
        print(f"❌ Error en {description}: {e}")
        return False


def migrate_pgvector(db: DatabaseConnection) -> bool:
    """Asegura que la extensión pgvector esté instalada"""
    return execute_sql_safely(
        db,
        "CREATE EXTENSION IF NOT EXISTS vector;",
        "Extensión pgvector"
    )


def migrate_users_table(db: DatabaseConnection) -> bool:
    """Crea la tabla users si no existe"""
    sql = """
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username VARCHAR(100) UNIQUE NOT NULL,
        email VARCHAR(255) UNIQUE NOT NULL,
        password_hash VARCHAR(255),
        role VARCHAR(20) DEFAULT 'user' CHECK (role IN ('admin', 'user')),
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    """
    return execute_sql_safely(db, sql, "Tabla users")


def migrate_documents_table(db: DatabaseConnection) -> bool:
    """Crea la tabla documents con columnas base (si no existe)"""
    sql = """
    CREATE TABLE IF NOT EXISTS documents (
        id SERIAL PRIMARY KEY,
        filename VARCHAR(255) NOT NULL,
        original_path VARCHAR(500),
        processed_path VARCHAR(500),
        uploaded_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        processing_status VARCHAR(50) DEFAULT 'pending',
        is_indexed BOOLEAN DEFAULT FALSE,
        chunk_count INTEGER DEFAULT 0,
        last_indexed_at TIMESTAMP WITH TIME ZONE,
        error_log TEXT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT check_processing_status 
            CHECK (processing_status IN ('pending', 'completed', 'failed'))
    );
    """
    return execute_sql_safely(db, sql, "Tabla documents (base)")


def migrate_documents_web_columns(db: DatabaseConnection) -> bool:
    """Agrega columnas web scraping a documents (idempotente)"""
    columns = [
        ("source_url", "TEXT DEFAULT NULL"),
        ("source_type", "VARCHAR(20) DEFAULT 'file'"),
        ("auto_refresh", "BOOLEAN DEFAULT FALSE"),
        ("refresh_frequency", "VARCHAR(20) DEFAULT 'manual'"),
        ("last_scraped_at", "TIMESTAMP WITH TIME ZONE"),
    ]
    
    all_ok = True
    for col_name, col_type in columns:
        sql = f"ALTER TABLE documents ADD COLUMN IF NOT EXISTS {col_name} {col_type};"
        if not execute_sql_safely(db, sql, f"Columna documents.{col_name}"):
            all_ok = False
    
    # Agregar constraint check_source_type si no existe
    constraint_sql = """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'check_source_type'
        ) THEN
            ALTER TABLE documents ADD CONSTRAINT check_source_type 
                CHECK (source_type IN ('file', 'web'));
        END IF;
    END $$;
    """
    if not execute_sql_safely(db, constraint_sql, "Constraint check_source_type"):
        all_ok = False
    
    return all_ok


def migrate_chunks_table(db: DatabaseConnection) -> bool:
    """Crea la tabla chunks si no existe"""
    sql = """
    CREATE TABLE IF NOT EXISTS chunks (
        id SERIAL PRIMARY KEY,
        document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
        chunk_text TEXT NOT NULL,
        chunk_index INTEGER NOT NULL,
        embedding VECTOR(768),
        section_context TEXT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    """
    return execute_sql_safely(db, sql, "Tabla chunks")


def migrate_queries_table(db: DatabaseConnection) -> bool:
    """Crea la tabla queries si no existe"""
    sql = """
    CREATE TABLE IF NOT EXISTS queries (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
        query_text TEXT NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    """
    return execute_sql_safely(db, sql, "Tabla queries")


def migrate_responses_table(db: DatabaseConnection) -> bool:
    """Crea la tabla responses si no existe"""
    sql = """
    CREATE TABLE IF NOT EXISTS responses (
        id SERIAL PRIMARY KEY,
        query_id INTEGER REFERENCES queries(id) ON DELETE CASCADE,
        response_text TEXT NOT NULL,
        generated_by_model VARCHAR(100),
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    """
    return execute_sql_safely(db, sql, "Tabla responses")


def migrate_generated_docs_v2_table(db: DatabaseConnection) -> bool:
    """Crea la tabla generated_documents_v2 si no existe"""
    sql = """
    CREATE TABLE IF NOT EXISTS generated_documents_v2 (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        title VARCHAR(500) NOT NULL,
        prompt TEXT NOT NULL,
        content TEXT NOT NULL,
        format VARCHAR(20) DEFAULT 'markdown',
        generation_mode VARCHAR(50) DEFAULT 'prompt_libre',
        source_doc_ids INTEGER[],
        model_used VARCHAR(100),
        word_count INTEGER,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT check_format 
            CHECK (format IN ('txt', 'markdown', 'pdf', 'docx')),
        CONSTRAINT check_mode
            CHECK (generation_mode IN ('prompt_libre', 'basado_repositorio', 'basado_documento'))
    );
    """
    return execute_sql_safely(db, sql, "Tabla generated_documents_v2")


def migrate_indexes(db: DatabaseConnection) -> bool:
    """Crea todos los índices necesarios (idempotente)"""
    indexes = [
        ("idx_documents_indexed", "CREATE INDEX IF NOT EXISTS idx_documents_indexed ON documents(is_indexed)"),
        ("idx_documents_status", "CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(processing_status)"),
        ("idx_documents_source_type", "CREATE INDEX IF NOT EXISTS idx_documents_source_type ON documents(source_type)"),
        ("idx_chunks_document", "CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id)"),
        ("idx_chunks_embedding", "CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON chunks USING ivfflat (embedding vector_cosine_ops)"),
        ("idx_gendocs_user", "CREATE INDEX IF NOT EXISTS idx_gendocs_user ON generated_documents_v2(user_id)"),
        ("idx_gendocs_mode", "CREATE INDEX IF NOT EXISTS idx_gendocs_mode ON generated_documents_v2(generation_mode)"),
    ]
    
    all_ok = True
    for name, sql in indexes:
        if not execute_sql_safely(db, sql, f"Índice {name}"):
            all_ok = False
    
    return all_ok


def run_all_migrations(db: DatabaseConnection) -> bool:
    """Ejecuta todas las migraciones en orden correcto"""
    print("🔄 Iniciando migraciones...")
    print()
    
    migrations = [
        ("Extensiones", migrate_pgvector),
        ("Tabla users", migrate_users_table),
        ("Tabla documents (base)", migrate_documents_table),
        ("Columnas web scraping", migrate_documents_web_columns),
        ("Tabla chunks", migrate_chunks_table),
        ("Tabla queries", migrate_queries_table),
        ("Tabla responses", migrate_responses_table),
        ("Tabla generated_documents_v2", migrate_generated_docs_v2_table),
        ("Índices", migrate_indexes),
    ]
    
    all_ok = True
    for name, migration_func in migrations:
        print(f"🔄 {name}...")
        if not migration_func(db):
            all_ok = False
    
    print()
    return all_ok


def verify_core_functionality(db: DatabaseConnection) -> bool:
    """Verifica que todas las tablas e índices necesarios existan"""
    print("=" * 60)
    print("🔍 Verificación de funcionalidad core")
    print("=" * 60)
    
    checks = [
        ("Extensión pgvector", "SELECT EXISTS (SELECT FROM pg_extension WHERE extname = 'vector') as exists"),
        ("Tabla users", "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'users') as exists"),
        ("Tabla documents", "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'documents') as exists"),
        ("Tabla chunks", "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'chunks') as exists"),
        ("Tabla queries", "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'queries') as exists"),
        ("Tabla responses", "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'responses') as exists"),
        ("Tabla generated_documents_v2", "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'generated_documents_v2') as exists"),
        ("Columna source_url", "SELECT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'documents' AND column_name = 'source_url') as exists"),
        ("Columna source_type", "SELECT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'documents' AND column_name = 'source_type') as exists"),
        ("Índice idx_documents_source_type", "SELECT EXISTS (SELECT FROM pg_indexes WHERE indexname = 'idx_documents_source_type') as exists"),
    ]
    
    all_ok = True
    for name, sql in checks:
        try:
            result = db.execute_query(sql, fetch=True)
            exists = result[0].get('exists', False) if result else False
            status = "✅" if exists else "❌"
            print(f"{status} {name}")
            if not exists:
                all_ok = False
        except Exception as e:
            print(f"❌ Error verificando {name}: {e}")
            all_ok = False
    
    return all_ok


def main():
    parser = argparse.ArgumentParser(
        description="Sistema de migraciones automático para MCP-DOCS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python db/migrate.py           # Ejecutar todo el schema
  python db/migrate.py --verify    # Verificar que todo funcione
  python db/migrate.py --status    # Ver estado detallado
        """
    )
    parser.add_argument(
        '--check', 
        action='store_true', 
        help='Solo verificar, no aplicar migraciones'
    )
    parser.add_argument(
        '--status', 
        action='store_true', 
        help='Mostrar estado detallado'
    )
    parser.add_argument(
        '--verify', 
        action='store_true', 
        help='Verificar que todo esté listo para funcionar'
    )
    
    args = parser.parse_args()
    
    try:
        # Verificar que DATABASE_URL esté configurado
        if not os.environ.get("DATABASE_URL"):
            print("❌ Error: DATABASE_URL no está configurado")
            print("   Crea un archivo .env con: DATABASE_URL=postgresql://...")
            sys.exit(1)
        
        db = DatabaseConnection()
        
        if args.verify:
            ok = verify_core_functionality(db)
            print()
            print("=" * 60)
            if ok:
                print("✅ Todo está listo! Ejecuta: python run_web.py")
            else:
                print("⚠️  Faltan elementos. Ejecuta: python db/migrate.py")
            sys.exit(0 if ok else 1)
        
        if args.status or args.check:
            ok = verify_core_functionality(db)
            sys.exit(0 if ok else 1)
        
        # Ejecutar migraciones
        print("=" * 60)
        print("🚀 MCP-DOCS Database Migration Runner")
        print("=" * 60)
        print()
        
        success = run_all_migrations(db)
        
        if success:
            print("=" * 60)
            print("🔍 Verificación final...")
            ok = verify_core_functionality(db)
            print()
            if ok:
                print("✅ Base de datos lista! Ejecuta: python run_web.py")
                sys.exit(0)
            else:
                print("⚠️  Algunos elementos faltan.")
                sys.exit(1)
        else:
            print()
            print("❌ Error aplicando migraciones")
            sys.exit(1)
        
    except Exception as e:
        print(f"\n❌ Error fatal: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
