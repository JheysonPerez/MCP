import re
from typing import Dict, Any, Optional, List
from werkzeug.security import generate_password_hash, check_password_hash


class UserService:
    """
    Servicio para gestión completa de usuarios: CRUD, roles, autenticación.
    """
    
    VALID_ROLES = ['admin', 'user']
    
    def __init__(self, db_connection):
        self.db = db_connection
    
    # --- Validaciones ---
    
    def _validate_email(self, email: str) -> bool:
        """Valida formato de email."""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    def _validate_username(self, username: str) -> bool:
        """Valida que username sea alfanumérico con guiones, 3-50 chars."""
        if not 3 <= len(username) <= 50:
            return False
        return bool(re.match(r'^[a-zA-Z0-9_-]+$', username))
    
    def _validate_password(self, password: str) -> tuple[bool, str]:
        """Valida fortaleza de password. Retorna (valido, mensaje_error)."""
        if len(password) < 8:
            return False, "La contraseña debe tener al menos 8 caracteres"
        if not re.search(r'[A-Z]', password):
            return False, "La contraseña debe contener al menos una mayúscula"
        if not re.search(r'[a-z]', password):
            return False, "La contraseña debe contener al menos una minúscula"
        if not re.search(r'[0-9]', password):
            return False, "La contraseña debe contener al menos un número"
        return True, ""
    
    def _check_email_exists(self, email: str, exclude_id: int = None) -> bool:
        """Verifica si email ya existe, opcionalmente excluyendo un user_id."""
        query = "SELECT id FROM users WHERE email = %s"
        params = [email]
        if exclude_id:
            query += " AND id != %s"
            params.append(exclude_id)
        result = self.db.execute_query(query, tuple(params), fetch=True)
        return bool(result)
    
    def _check_username_exists(self, username: str, exclude_id: int = None) -> bool:
        """Verifica si username ya existe, opcionalmente excluyendo un user_id."""
        query = "SELECT id FROM users WHERE username = %s"
        params = [username]
        if exclude_id:
            query += " AND id != %s"
            params.append(exclude_id)
        result = self.db.execute_query(query, tuple(params), fetch=True)
        return bool(result)
    
    # --- CRUD ---
    
    def create_user(self, username: str, email: str, password: str, 
                   role: str = 'user', is_active: bool = True) -> Dict[str, Any]:
        """
        Crea un nuevo usuario con validaciones completas.
        Retorna: {'success': bool, 'user_id': int|None, 'error': str|None}
        """
        # Validaciones
        if not self._validate_username(username):
            return {'success': False, 'user_id': None, 
                    'error': 'Username inválido (3-50 chars, alfanumérico con guiones)'}
        
        if not self._validate_email(email):
            return {'success': False, 'user_id': None, 'error': 'Email inválido'}
        
        valid_pwd, pwd_error = self._validate_password(password)
        if not valid_pwd:
            return {'success': False, 'user_id': None, 'error': pwd_error}
        
        if role not in self.VALID_ROLES:
            return {'success': False, 'user_id': None, 'error': 'Rol inválido'}
        
        if self._check_username_exists(username):
            return {'success': False, 'user_id': None, 'error': 'Username ya existe'}
        
        if self._check_email_exists(email):
            return {'success': False, 'user_id': None, 'error': 'Email ya registrado'}
        
        # Crear usuario
        password_hash = generate_password_hash(password)
        query = """
            INSERT INTO users (username, email, password_hash, role, is_active)
            VALUES (%s, %s, %s, %s, %s) RETURNING id;
        """
        result = self.db.execute_query(
            query, (username, email, password_hash, role, is_active), 
            fetch=True, commit=True
        )
        
        return {'success': True, 'user_id': result[0]['id'], 'error': None}
    
    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        """Obtiene usuario completo por ID."""
        query = """
            SELECT id, username, email, role, is_active, created_at
            FROM users WHERE id = %s;
        """
        result = self.db.execute_query(query, (user_id,), fetch=True)
        return result[0] if result else None
    
    def get_user_by_username(self, username: str) -> Optional[Dict]:
        """Obtiene usuario por username (incluye password_hash para auth)."""
        query = """
            SELECT id, username, email, password_hash, role, is_active, created_at
            FROM users WHERE username = %s;
        """
        result = self.db.execute_query(query, (username,), fetch=True)
        return result[0] if result else None
    
    def get_user_by_email(self, email: str) -> Optional[Dict]:
        """Obtiene usuario por email."""
        query = """
            SELECT id, username, email, role, is_active, created_at
            FROM users WHERE email = %s;
        """
        result = self.db.execute_query(query, (email,), fetch=True)
        return result[0] if result else None
    
    def list_users(self, include_inactive: bool = False) -> List[Dict]:
        """Lista todos los usuarios."""
        if include_inactive:
            query = "SELECT id, username, email, role, is_active, created_at FROM users ORDER BY created_at DESC;"
            return self.db.execute_query(query, fetch=True) or []
        else:
            query = """
                SELECT id, username, email, role, is_active, created_at 
                FROM users WHERE is_active = TRUE ORDER BY created_at DESC;
            """
            return self.db.execute_query(query, fetch=True) or []
    
    def update_user(self, user_id: int, **kwargs) -> Dict[str, Any]:
        """
        Actualiza campos de usuario. Permite: username, email, role, is_active.
        Para password usar update_password().
        Retorna: {'success': bool, 'error': str|None}
        """
        allowed_fields = ['username', 'email', 'role', 'is_active']
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
        
        if not updates:
            return {'success': False, 'error': 'No hay campos válidos para actualizar'}
        
        # Validaciones
        if 'username' in updates:
            if not self._validate_username(updates['username']):
                return {'success': False, 'error': 'Username inválido'}
            if self._check_username_exists(updates['username'], exclude_id=user_id):
                return {'success': False, 'error': 'Username ya existe'}
        
        if 'email' in updates:
            if not self._validate_email(updates['email']):
                return {'success': False, 'error': 'Email inválido'}
            if self._check_email_exists(updates['email'], exclude_id=user_id):
                return {'success': False, 'error': 'Email ya registrado'}
        
        if 'role' in updates and updates['role'] not in self.VALID_ROLES:
            return {'success': False, 'error': 'Rol inválido'}
        
        # Construir query dinámica
        set_clause = ", ".join([f"{k} = %s" for k in updates.keys()])
        values = list(updates.values()) + [user_id]
        
        query = f"UPDATE users SET {set_clause} WHERE id = %s;"
        self.db.execute_query(query, tuple(values), commit=True)
        
        return {'success': True, 'error': None}
    
    def update_password(self, user_id: int, new_password: str) -> Dict[str, Any]:
        """Actualiza password con validación de fortaleza."""
        valid, error = self._validate_password(new_password)
        if not valid:
            return {'success': False, 'error': error}
        
        password_hash = generate_password_hash(new_password)
        query = "UPDATE users SET password_hash = %s WHERE id = %s;"
        self.db.execute_query(query, (password_hash, user_id), commit=True)
        
        return {'success': True, 'error': None}
    
    def delete_user(self, user_id: int, soft_delete: bool = True) -> Dict[str, Any]:
        """
        Elimina usuario. Por defecto hace soft delete (desactiva).
        """
        if soft_delete:
            query = "UPDATE users SET is_active = FALSE WHERE id = %s;"
            self.db.execute_query(query, (user_id,), commit=True)
            return {'success': True, 'error': None, 'deleted': False, 'deactivated': True}
        else:
            query = "DELETE FROM users WHERE id = %s;"
            self.db.execute_query(query, (user_id,), commit=True)
            return {'success': True, 'error': None, 'deleted': True, 'deactivated': False}
    
    # --- Autenticación ---
    
    def authenticate(self, username: str, password: str) -> Optional[Dict]:
        """
        Autentica usuario. Retorna datos del usuario si OK, None si falla.
        """
        user = self.get_user_by_username(username)
        if not user:
            return None
        
        if not user.get('is_active'):
            return None
        
        if not user.get('password_hash'):
            return None
        
        if check_password_hash(user['password_hash'], password):
            # No devolver password_hash
            return {k: v for k, v in user.items() if k != 'password_hash'}
        
        return None
    
    def is_admin(self, user_id: int) -> bool:
        """Verifica si un usuario es admin."""
        user = self.get_user_by_id(user_id)
        return user and user.get('role') == 'admin'
