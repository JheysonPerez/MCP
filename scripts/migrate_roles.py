#!/usr/bin/env python3
"""
Script de migración para activar el sistema de roles de usuarios.
- Agrega columnas 'role' y 'is_active' a la tabla users si no existen
- Asigna rol 'admin' al usuario 'admin' existente
- Marca todos los usuarios existentes como activos
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.connection import DatabaseConnection


def migrate_roles():
    db = DatabaseConnection()
    
    print("=" * 60)
    print("MIGRACIÓN: Sistema de Roles de Usuarios")
    print("=" * 60)
    
    # 1. Agregar columna 'role' si no existe
    print("\n[1/3] Verificando columna 'role'...")
    try:
        db.execute_query(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) DEFAULT 'user';",
            commit=True
        )
        print("   ✓ Columna 'role' verificada")
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return False
    
    # 2. Agregar columna 'is_active' si no existe
    print("\n[2/3] Verificando columna 'is_active'...")
    try:
        db.execute_query(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;",
            commit=True
        )
        print("   ✓ Columna 'is_active' verificada")
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return False
    
    # 3. Agregar constraint CHECK para roles válidos
    print("\n[3/3] Aplicando constraint de roles válidos...")
    try:
        # PostgreSQL no permite ALTER TABLE ADD CONSTRAINT IF NOT EXISTS directamente
        # Verificamos si el constraint existe
        check_result = db.execute_query(
            """
            SELECT conname FROM pg_constraint 
            WHERE conrelid = 'users'::regclass AND conname = 'users_role_check';
            """,
            fetch=True
        )
        
        if not check_result:
            db.execute_query(
                "ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN ('admin', 'user'));",
                commit=True
            )
            print("   ✓ Constraint 'users_role_check' agregado")
        else:
            print("   ℹ Constraint ya existe")
    except Exception as e:
        print(f"   ⚠ Warning (no crítico): {e}")
    
    # 4. Asignar rol 'admin' al usuario 'admin'
    print("\n[4/4] Asignando rol 'admin' al usuario 'admin'...")
    try:
        result = db.execute_query(
            "UPDATE users SET role = 'admin', is_active = TRUE WHERE username = 'admin';",
            commit=True
        )
        
        # Verificar
        admin_user = db.execute_query(
            "SELECT id, username, email, role, is_active FROM users WHERE username = 'admin';",
            fetch=True
        )
        
        if admin_user and admin_user[0].get('role') == 'admin':
            print(f"   ✓ Usuario 'admin' ahora tiene rol 'admin'")
            print(f"     ID: {admin_user[0]['id']}")
            print(f"     Email: {admin_user[0]['email']}")
            print(f"     Activo: {admin_user[0]['is_active']}")
        else:
            print("   ⚠ No se encontró usuario 'admin'")
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return False
    
    # 5. Marcar todos los usuarios existentes como activos y con rol 'user' si no tienen rol
    print("\n[5/5] Actualizando usuarios existentes...")
    try:
        db.execute_query(
            "UPDATE users SET role = 'user', is_active = TRUE WHERE role IS NULL;",
            commit=True
        )
        
        # Contar usuarios por rol
        counts = db.execute_query(
            "SELECT role, COUNT(*) as n FROM users GROUP BY role;",
            fetch=True
        )
        
        print("   ✓ Usuarios actualizados:")
        for row in counts:
            print(f"     - {row['role']}: {row['n']} usuario(s)")
    except Exception as e:
        print(f"   ⚠ Warning: {e}")
    
    print("\n" + "=" * 60)
    print("MIGRACIÓN COMPLETADA")
    print("=" * 60)
    print("\nPuedes iniciar sesión con:")
    print("  Usuario: admin")
    print("  Contraseña: (la que tenías configurada)")
    print("\nAccede a /admin/usuarios para gestionar usuarios.")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    success = migrate_roles()
    sys.exit(0 if success else 1)
