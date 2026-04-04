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

SCHEMA_FILE = Path(__file__).parent / "schema.sql"


def run_schema_sql(db: DatabaseConnection) -> bool:
    """Ejecuta el archivo schema.sql completo (idempotente)"""
    print("🔄 Ejecutando schema.sql (idempotente)...")
    
    if not SCHEMA_FILE.exists():
        print(f"❌ No se encontró {SCHEMA_FILE}")
        return False
    
    try:
        with open(SCHEMA_FILE, 'r', encoding='utf-8') as f:
            schema_sql = f.read()
        
        # Ejecutar todo el schema en una transacción
        conn = db.get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(schema_sql)
            conn.commit()
            print("✅ Schema ejecutado correctamente")
            return True
        finally:
            conn.close()
    except Exception as e:
        print(f"❌ Error ejecutando schema: {e}")
        return False


def verify_core_functionality(db: DatabaseConnection) -> bool:
    """Verifica que todas las tablas e índices necesarios existan"""
    print("\n" + "=" * 60)
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
        ("Columnas web scraping", "SELECT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'documents' AND column_name = 'source_url') as exists"),
    ]
    
    all_ok = True
    for name, sql in checks:
        try:
            result = db.execute_query(sql, fetch=True)
            exists = result[0].get('exists', False) if result else False
            status = "✅" if exists else "❌"
            print(f"{status} {name}: {'OK' if exists else 'FALTANTE'}")
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
            print("\n" + "=" * 60)
            if ok:
                print("✅ Todo está listo! Ejecuta: python run_web.py")
            else:
                print("⚠️  Faltan elementos. Ejecuta: python db/migrate.py")
            sys.exit(0 if ok else 1)
        
        if args.status:
            verify_core_functionality(db)
            sys.exit(0)
        
        if args.check:
            print("🔍 Modo check - solo verificando...")
            ok = verify_core_functionality(db)
            sys.exit(0 if ok else 1)
        
        # Ejecutar migraciones completas
        print("=" * 60)
        print("🚀 MCP-DOCS Database Migration Runner")
        print("=" * 60)
        
        success = run_schema_sql(db)
        
        if success:
            print("\n" + "=" * 60)
            print("🔍 Verificación final...")
            print("=" * 60)
            ok = verify_core_functionality(db)
            if ok:
                print("\n✅ Base de datos lista!")
                print("   Ejecuta: python run_web.py")
                sys.exit(0)
            else:
                print("\n⚠️  Algunos elementos faltan.")
                sys.exit(1)
        else:
            print("\n❌ Error aplicando migraciones")
            sys.exit(1)
        
    except Exception as e:
        print(f"\n❌ Error fatal: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
