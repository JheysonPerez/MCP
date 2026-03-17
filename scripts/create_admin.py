import sys
from pathlib import Path
from werkzeug.security import generate_password_hash

# Add project root to sys path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.connection import DatabaseConnection

def create_admin_user():
    db = DatabaseConnection()
    
    # 1. Asegurarse que la columna de password exista
    print("Verificando esquema de la base de datos...")
    try:
        db.execute_query("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255);", commit=True)
        print("Columna 'password_hash' añadida exitosamente.")
    except Exception as e:
        # Se ignora si ya existe (psycopg2 arrojaría DuplicateColumn)
        pass
        
    username = "admin"
    email = "admin@epiis.local"
    # Contraseña fuerte por defecto para el MVP
    password_hash = generate_password_hash("password123")
    
    # 2. Upsert: siempre asignamos el username 'admin' al email institucional
    db.execute_query(
        "UPDATE users SET username=%s, password_hash=%s WHERE email=%s;",
        (username, password_hash, email), commit=True
    )
    # Si no existía, insertar
    count = db.execute_query("SELECT COUNT(*) as n FROM users WHERE email=%s;", (email,), fetch=True)[0]['n']
    if count == 0:
        db.execute_query(
            "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s);",
            (username, email, password_hash), commit=True
        )
        print(f"Usuario '{username}' CREADO con hash de contraseña. (password123)")
    else:
        print(f"Usuario '{username}' ACTUALIZADO con nuevo hash. (password123)")

if __name__ == "__main__":
    create_admin_user()
