from functools import wraps
from flask import session, redirect, url_for, flash


def login_required(f):
    """Decorador: Requiere que el usuario esté autenticado."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Debes iniciar sesión para acceder a esta página.", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Decorador: Requiere que el usuario sea administrador."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Debes iniciar sesión para acceder a esta página.", "error")
            return redirect(url_for("login"))
        
        # Verificar rol admin en sesión (más eficiente)
        if session.get("user_role") != "admin":
            flash("No tienes permisos de administrador.", "error")
            return redirect(url_for("dashboard"))
        
        return f(*args, **kwargs)
    return decorated_function
