from flask import current_app as app
from flask import render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash
from pathlib import Path
import os
import re
from datetime import datetime, timezone
import json

from .decorators import login_required, admin_required
from .utils import render_markdown_safe

# Importar tools MCP para usarlas desde la web
from mcp_server.server import (
    consultar_documentos,
    listar_documentos,
    generar_documento,
    agregar_fuente_web,
    eliminar_documento,
    reindexar_documento,
    estadisticas_repositorio
)

ALLOWED_EXTENSIONS = {'pdf', 'docx', 'txt', 'jpg', 'jpeg', 'png'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- AUTENTICACIÓN ---

@app.route("/", methods=["GET"])
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        
        try:
            # Usar UserService para autenticar
            user = app.user_service.authenticate(username, password)
            
            if user:
                session["user_id"] = user["id"]
                session["username"] = user["username"]
                session["user_role"] = user["role"]
                flash("Bienvenido al sistema.", "success")
                return redirect(url_for("dashboard"))
            else:
                flash("Usuario o contraseña incorrectos.", "error")
        except Exception as e:
            flash(f"Error al autenticar: {str(e)}", "error")
            
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Sesión cerrada correctamente.", "info")
    return redirect(url_for("login"))

# --- DASHBOARD PRINCIPAL ---

@app.route("/dashboard", methods=["GET"])
@login_required
def dashboard():
    stats = _get_stats()
    return render_template("dashboard.html", stats=stats, username=session.get("username"), user_role=session.get("user_role"))

def _get_stats():
    try:
        doc_count = app.db_conn.execute_query("SELECT COUNT(*) as total FROM documents;", fetch=True)
        query_count = app.db_conn.execute_query("SELECT COUNT(*) as total FROM queries;", fetch=True)
        return {
            "total_docs": doc_count[0]["total"] if doc_count else 0,
            "total_queries": query_count[0]["total"] if query_count else 0,
        }
    except:
        return {"total_docs": 0, "total_queries": 0}

# --- GESTIÓN DE DOCUMENTOS ---

@app.route("/documentos", methods=["GET"])
@login_required
def documentos():
    # Obtener documentos directamente de la BD con metadatos completos
    from db.connection import DatabaseConnection
    db = DatabaseConnection()

    query = """
        SELECT id, filename, processing_status, is_indexed, chunk_count,
               doc_type, doc_year, summary, keywords, created_at
        FROM documents
        ORDER BY created_at DESC
        LIMIT 100;
    """
    try:
        docs = db.execute_query(query, fetch=True) or []
        # Convertir fechas de string a datetime para el template
        for doc in docs:
            if doc.get("created_at") and isinstance(doc["created_at"], str):
                try:
                    doc["created_at"] = datetime.fromisoformat(doc["created_at"])
                except (ValueError, TypeError):
                    pass
    except Exception as e:
        docs = []
        flash(f"Error al cargar documentos: {str(e)}", "error")

    return render_template("documentos.html", documentos=docs, username=session.get("username"), user_role=session.get("user_role"))


@app.route("/upload", methods=["POST"])
@admin_required
def upload_document():
    
    if 'file' not in request.files:
        flash("No se seleccionó ningún archivo.", "error")
        return redirect(url_for("documentos"))
    
    file = request.files['file']
    
    if file.filename == '':
        flash("El nombre del archivo está vacío.", "error")
        return redirect(url_for("documentos"))
    
    if not allowed_file(file.filename):
        flash(f"Formato no permitido. Solo se aceptan: {', '.join(ALLOWED_EXTENSIONS).upper()}.", "error")
        return redirect(url_for("documentos"))
    
    try:
        import tempfile
        filename = secure_filename(file.filename)
        
        # 1. Procesamiento físico y registro en DB
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / filename
            file.save(str(tmp_path))
            
            # process_and_save ahora devuelve doc_id
            _, processed_path, doc_id = app.document_service.process_and_save(tmp_path)
            
            # 2. Indexación semántica automática
            app.rag_service.index_document(doc_id, str(processed_path))
        
        flash(f"'{filename}' subido, procesado e indexado correctamente.", "success")
    except Exception as e:
        flash(f"Error al procesar el archivo: {str(e)}", "error")
    
    return redirect(url_for("documentos"))

@app.route("/documentos/reindex/<int:doc_id>", methods=["POST"])
@admin_required
def reindex_document(doc_id):
    # Usar tool MCP reindexar_documento
    resultado_json = reindexar_documento(doc_id=doc_id)
    resultado = json.loads(resultado_json)
    
    if resultado.get("status") == "success":
        flash(resultado.get("mensaje", f"Documento #{doc_id} reindexado con éxito."), "success")
    else:
        flash(f"Error al reindexar: {resultado.get('message', 'Error desconocido')}", "error")
        
    return redirect(url_for("documentos"))

@app.route("/documentos/delete/<int:doc_id>", methods=["POST"])
@admin_required
def delete_document(doc_id):
    # Usar tool MCP eliminar_documento con modo hard
    resultado_json = eliminar_documento(doc_id=doc_id, modo="hard")
    resultado = json.loads(resultado_json)
    
    if resultado.get("status") == "success":
        flash(resultado.get("mensaje", f"Documento #{doc_id} eliminado correctamente."), "success")
    else:
        flash(f"Error al eliminar: {resultado.get('message', 'Error desconocido')}", "error")
        
    return redirect(url_for("documentos"))


@app.route("/documentos/<int:doc_id>/download")
@login_required
def download_document(doc_id):
    """Descargar el archivo original de un documento (para usuarios regulares)."""
    doc = app.persistence.get_document_by_id(doc_id)
    
    if not doc:
        flash("Documento no encontrado.", "error")
        return redirect(url_for("documentos"))
    
    filename = doc.get("filename")
    
    # SIEMPRE buscar en data/uploads/ - ignorar el original_path de la BD
    base_dir = Path(__file__).parent.parent
    correct_path = base_dir / "data" / "uploads" / filename
    
    print(f"[DOWNLOAD] doc_id={doc_id}, filename={filename}")
    print(f"[DOWNLOAD] Buscando en: {correct_path}")
    
    if correct_path.exists():
        print(f"[DOWNLOAD] Archivo encontrado")
        from flask import send_file
        return send_file(
            str(correct_path),
            as_attachment=True,
            download_name=filename
        )
    
    print(f"[DOWNLOAD] ERROR: Archivo no existe en {correct_path}")
    flash("Archivo original no encontrado.", "error")
    return redirect(url_for("documentos"))


# --- CONSULTA RAG ---

@app.route("/consultar", methods=["GET", "POST"])
@login_required
def consultar():

    respuesta_rag = None
    pregunta_hecha = None
    fuentes = []
    
    # Parámetros iniciales de contexto
    scope = "all"
    doc_seleccionado = None # Nombre del archivo
    
    # 1. Capturar doc_id desde GET (viene de la lista de documentos)
    doc_id_get = request.args.get('doc_id')
    if doc_id_get:
        try:
            doc_data = app.persistence.get_document_by_id(int(doc_id_get))
            if doc_data:
                scope = "doc"
                doc_seleccionado = doc_data['filename']
        except:
            pass

    # 2. Cargar lista de documentos para el selector (siempre necesaria)
    try:
        documentos_lista = app.db_conn.execute_query(
            "SELECT filename FROM documents WHERE processing_status = 'completed' ORDER BY created_at DESC;", fetch=True
        )
    except:
        documentos_lista = []

    # 3. Manejar la consulta (POST)
    chat_history = session.get("chat_history", [])
    
    if request.method == "POST":
        pregunta = request.form.get("pregunta", "").strip()
        scope = request.form.get("scope", "all")
        doc_seleccionado = request.form.get("doc_id", "").strip() or None

        if not pregunta:
            flash("Debes ingresar una pregunta válida.", "error")
        else:
            # Filtro real para el motor RAG - soporta ID numérico o nombre de archivo
            filtro_doc = None
            if scope == "doc" and doc_seleccionado:
                # Primero intentar usar directamente como ID (si es numérico)
                if doc_seleccionado.isdigit():
                    filtro_doc = doc_seleccionado
                else:
                    # Si no es numérico, buscar por nombre de archivo
                    try:
                        doc_result = app.db_conn.execute_query(
                            "SELECT id FROM documents WHERE filename = %s LIMIT 1",
                            (doc_seleccionado,),
                            fetch=True
                        )
                        if doc_result:
                            filtro_doc = str(doc_result[0]['id'])
                            print(f"[SCRAPE] path={doc_seleccionado} url={filtro_doc} len={len(filtro_doc)} stderr=''")
                    except Exception as e:
                        print(f"[SCRAPE] path={doc_seleccionado} no JSON found in output. stderr={str(e)}")
                        filtro_doc = None

            try:
                # Usar tool MCP consultar_documentos
                resultado_json = consultar_documentos(
                    consulta=pregunta,
                    documento_id=filtro_doc,
                    incluir_fuentes=True,
                    top_k=10
                )
                resultado = json.loads(resultado_json)
                
                if resultado.get("status") == "success":
                    respuesta_raw = resultado.get("respuesta", "").strip()
                    fuentes = resultado.get("fuentes", [])
                    pregunta_hecha = pregunta
                    
                    # Procesar markdown a HTML seguro para mostrar
                    respuesta_rag = render_markdown_safe(respuesta_raw)

                    # Actualizar historial en sesión para la PRÓXIMA consulta (guardar raw)
                    chat_history.append({
                        "pregunta": pregunta,
                        "respuesta": respuesta_raw
                    })
                    session["chat_history"] = chat_history[-5:]
                    session.modified = True
                else:
                    flash(f"Error en consulta: {resultado.get('message', 'Error desconocido')}", "error")

            except Exception as e:
                flash(f"Error al consultar el sistema RAG: {str(e)}", "error")

    # Turno actual para mostrar por separado del historial
    turno_actual = {
        "pregunta": pregunta_hecha, 
        "respuesta": respuesta_rag, 
        "fuentes": fuentes
    } if pregunta_hecha else None

    # Procesar chat_history para convertir markdown a HTML en las respuestas
    chat_history_html = []
    for turno in (chat_history[:-1] if turno_actual else chat_history):
        chat_history_html.append({
            "pregunta": turno["pregunta"],
            "respuesta": render_markdown_safe(turno["respuesta"])
        })

    return render_template(
        "consultar.html",
        turno_actual=turno_actual,
        scope=scope,
        doc_seleccionado=doc_seleccionado,
        documentos_lista=documentos_lista,
        chat_history=chat_history_html,  # Historial con respuestas procesadas a HTML
        username=session.get("username")
    )

@app.route("/consultar/limpiar", methods=["POST"])
def limpiar_historial():
    session.pop("chat_history", None)
    return redirect(url_for("consultar"))



# --- HISTORIAL ---

@app.route("/historial", methods=["GET"])
@login_required
def historial():
    user_id = session.get("user_id")
    user_role = session.get("user_role")
    
    try:
        if user_role == 'admin':
            # Admin ve historial de todos los usuarios
            rows = app.db_conn.execute_query("""
                SELECT q.query_text, r.response_text, q.created_at, u.username
                FROM queries q
                LEFT JOIN responses r ON r.query_id = q.id
                LEFT JOIN users u ON u.id = q.user_id
                ORDER BY q.created_at DESC
                LIMIT 50;
            """, fetch=True)
        else:
            # Usuario normal solo ve su propio historial
            rows = app.db_conn.execute_query("""
                SELECT q.query_text, r.response_text, q.created_at, u.username
                FROM queries q
                LEFT JOIN responses r ON r.query_id = q.id
                LEFT JOIN users u ON u.id = q.user_id
                WHERE q.user_id = %s
                ORDER BY q.created_at DESC
                LIMIT 50;
            """, (user_id,), fetch=True)
    except:
        rows = []
    
    return render_template("historial.html", historial=rows, username=session.get("username"), user_role=user_role)

# --- GENERACIÓN DOCUMENTAL ---

@app.route("/generar", methods=["GET"])
@login_required
def generar():
    
    # Documentos de archivo (excluyendo web)
    documentos_lista = app.db_conn.execute_query(
        "SELECT id, filename FROM documents WHERE is_indexed = TRUE AND (source_type = 'file' OR source_type IS NULL) ORDER BY filename;",
        fetch=True
    ) or []
    
    # Documentos web
    web_lista = app.db_conn.execute_query(
        "SELECT id, filename, source_url FROM documents WHERE is_indexed = TRUE AND source_type = 'web' ORDER BY filename;",
        fetch=True
    ) or []
    
    generados = app.generation_service.get_all()
    
    return render_template("generar.html",
        documentos_lista=documentos_lista,
        web_lista=web_lista,
        generados=generados,
        username=session.get("username")
    )

@app.route("/generar/crear", methods=["POST"])
@login_required
def generar_crear():
    
    prompt = request.form.get("prompt", "").strip()
    mode = request.form.get("mode", "prompt_libre")
    doc_type = request.form.get("doc_type", "libre")
    doc_format = request.form.get("formato", "markdown")
    source_doc_id = request.form.get("source_doc_id", "").strip()
    
    if not prompt:
        flash("Debes ingresar instrucciones para generar el documento.", "error")
        return redirect(url_for("generar"))
    
    # Usar tool MCP generar_documento
    try:
        # Mapear modo de la web a modo del MCP
        modo_mcp = "prompt_libre"
        if mode == "source_doc":
            modo_mcp = "basado_documento"
        elif mode == "prompt_libre":
            modo_mcp = "basado_repositorio"
        
        resultado_json = generar_documento(
            prompt=prompt,
            tipo=doc_type,
            modo=modo_mcp,
            documento_base_id=source_doc_id if source_doc_id else None
        )
        resultado = json.loads(resultado_json)
        
        if resultado.get("status") == "success":
            gen_id = resultado.get("id_guardado")
            if gen_id:
                flash(f"Documento generado exitosamente", "success")
                return redirect(url_for("generar_ver", gen_id=gen_id))
            else:
                # Si no se guardó pero se generó, mostrar el contenido
                flash("Documento generado (sin guardar en historial)", "success")
        else:
            flash(f"Error al generar: {resultado.get('message', 'Error desconocido')}", "error")
    except Exception as e:
        flash(f"Error inesperado: {str(e)}", "error")
    
    return redirect(url_for("generar"))

@app.route("/generar/ver/<int:gen_id>", methods=["GET"])
@login_required
def generar_ver(gen_id):
    
    doc = app.generation_service.get_by_id(gen_id)
    if not doc:
        flash("Documento no encontrado.", "error")
        return redirect(url_for("generar"))
    
    return render_template("generar_ver.html", doc=doc,
        username=session.get("username"))

@app.route("/generar/descargar/<int:gen_id>")
@login_required
def generar_descargar(gen_id):

    from flask import Response
    fmt = request.args.get("fmt", "md")
    doc = app.generation_service.get_by_id(gen_id)
    if not doc:
        flash("Documento no encontrado.", "error")
        return redirect(url_for("generar"))

    safe_title = doc['title'][:50].replace(' ', '_').replace('/', '_')

    if fmt == "docx":
        try:
            content = app.generation_service.export_docx(gen_id)
            response = Response(
                content,
                mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                headers={
                    "Content-Disposition": f"attachment; filename=\"{safe_title}.docx\"",
                    "Content-Type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "X-Content-Type-Options": "nosniff",
                    "Cache-Control": "no-cache"
                }
            )
            return response
        except Exception as e:
            flash(f"Error al exportar DOCX: {str(e)}", "error")
            return redirect(url_for("generar_ver", gen_id=gen_id))

    elif fmt == "pdf":
        try:
            content = app.generation_service.export_pdf(gen_id)
            response = Response(
                content,
                mimetype="application/pdf",
                headers={
                    "Content-Disposition": f"attachment; filename=\"{safe_title}.pdf\"",
                    "Content-Type": "application/pdf",
                    "X-Content-Type-Options": "nosniff",
                    "Cache-Control": "no-cache"
                }
            )
            return response
        except Exception as e:
            flash(f"Error al exportar PDF: {str(e)}", "error")
            return redirect(url_for("generar_ver", gen_id=gen_id))

    else:
        return Response(
            doc["content"],
            mimetype="text/markdown",
            headers={"Content-Disposition": 
                     f"attachment; filename={safe_title}.md"}
        )

@app.route("/generar/eliminar/<int:gen_id>", methods=["POST"])
@login_required
def generar_eliminar(gen_id):
    
    app.generation_service.delete(gen_id)
    flash("Documento eliminado.", "info")
    return redirect(url_for("generar"))


# --- ADMIN: GESTIÓN DE USUARIOS ---

@app.route("/admin/dashboard", methods=["GET"])
@admin_required
def admin_dashboard():
    """Página de dashboard de administración."""
    stats = _get_stats()
    # Estadísticas adicionales de admin
    try:
        user_count = app.db_conn.execute_query("SELECT COUNT(*) as total FROM users;", fetch=True)
        stats["total_users"] = user_count[0]["total"] if user_count else 0
    except:
        stats["total_users"] = 0
    
    return render_template("admin/dashboard.html", 
                          stats=stats, 
                          username=session.get("username"),
                          user_role=session.get("user_role"))


@app.route("/admin/usuarios", methods=["GET"])
@admin_required
def admin_usuarios():
    """Página de administración de usuarios."""
    users = app.user_service.list_users(include_inactive=True)
    return render_template("admin/usuarios.html", 
                          users=users, 
                          username=session.get("username"),
                          user_role=session.get("user_role"))


@app.route("/api/usuarios", methods=["GET"])
@admin_required
def api_list_users():
    """API: Listar todos los usuarios."""
    include_inactive = request.args.get('include_inactive', 'false').lower() == 'true'
    users = app.user_service.list_users(include_inactive=include_inactive)
    return jsonify({'success': True, 'users': users})


@app.route("/api/usuarios", methods=["POST"])
@admin_required
def api_create_user():
    """API: Crear nuevo usuario."""
    data = request.get_json()
    
    if not data:
        return jsonify({'success': False, 'error': 'No se recibieron datos'}), 400
    
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    role = data.get('role', 'user')
    is_active = data.get('is_active', True)
    
    result = app.user_service.create_user(
        username=username,
        email=email,
        password=password,
        role=role,
        is_active=is_active
    )
    
    if result['success']:
        return jsonify({'success': True, 'user_id': result['user_id']}), 201
    else:
        return jsonify({'success': False, 'error': result['error']}), 400


@app.route("/api/usuarios/<int:user_id>", methods=["GET"])
@admin_required
def api_get_user(user_id):
    """API: Obtener datos de un usuario."""
    user = app.user_service.get_user_by_id(user_id)
    if user:
        return jsonify({'success': True, 'user': user})
    else:
        return jsonify({'success': False, 'error': 'Usuario no encontrado'}), 404


@app.route("/api/usuarios/<int:user_id>", methods=["PUT"])
@admin_required
def api_update_user(user_id):
    """API: Actualizar usuario (username, email, role, is_active)."""
    data = request.get_json()
    
    if not data:
        return jsonify({'success': False, 'error': 'No se recibieron datos'}), 400
    
    # No permitir actualizar el propio usuario para evitar bloquearse a sí mismo
    if user_id == session.get('user_id') and 'role' in data and data['role'] != 'admin':
        return jsonify({'success': False, 'error': 'No puedes quitarte el rol de administrador a ti mismo'}), 403
    
    if user_id == session.get('user_id') and 'is_active' in data and not data['is_active']:
        return jsonify({'success': False, 'error': 'No puedes desactivarte a ti mismo'}), 403
    
    result = app.user_service.update_user(user_id, **data)
    
    if result['success']:
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': result['error']}), 400


@app.route("/api/usuarios/<int:user_id>/password", methods=["PUT"])
@admin_required
def api_update_password(user_id):
    """API: Actualizar password de usuario."""
    data = request.get_json()
    
    if not data or 'password' not in data:
        return jsonify({'success': False, 'error': 'Contraseña requerida'}), 400
    
    result = app.user_service.update_password(user_id, data['password'])
    
    if result['success']:
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': result['error']}), 400


@app.route("/api/usuarios/<int:user_id>", methods=["DELETE"])
@admin_required
def api_delete_user(user_id):
    """API: Eliminar/desactivar usuario."""
    # No permitir eliminarse a sí mismo
    if user_id == session.get('user_id'):
        return jsonify({'success': False, 'error': 'No puedes eliminarte a ti mismo'}), 403
    
    # Por defecto soft delete (desactivar)
    hard_delete = request.args.get('hard', 'false').lower() == 'true'
    
    result = app.user_service.delete_user(user_id, soft_delete=not hard_delete)
    
    if result['success']:
        return jsonify({'success': True, 'deleted': result.get('deleted', False), 
                       'deactivated': result.get('deactivated', False)})
    else:
        return jsonify({'success': False, 'error': result['error']}), 400


# --- ADMIN: GESTIÓN DE DOCUMENTOS ---

@app.route("/admin/documentos", methods=["GET"])
@admin_required
def admin_documentos():
    """Página de administración de documentos."""
    docs = app.db_conn.execute_query("""
        SELECT id, filename, created_at, processing_status, is_indexed, chunk_count, original_path
        FROM documents 
        ORDER BY created_at DESC;
    """, fetch=True)
    return render_template("admin/documentos.html", 
                          documents=docs, 
                          username=session.get("username"),
                          user_role=session.get("user_role"))


@app.route("/admin/documentos/<int:doc_id>/download")
@admin_required
def admin_download_document(doc_id):
    """Descargar el archivo original de un documento."""
    doc = app.persistence.get_document_by_id(doc_id)
    
    if not doc:
        flash("Documento no encontrado.", "error")
        return redirect(url_for("admin_documentos"))
    
    original_path = doc.get("original_path")
    
    # Intentar path original
    if original_path and os.path.exists(original_path):
        from flask import send_file
        return send_file(
            original_path,
            as_attachment=True,
            download_name=doc["filename"]
        )
    
    # Fallback: si el path tiene 'app/data/uploads', intentar sin 'app/'
    if original_path and "app/data/uploads" in original_path:
        corrected_path = original_path.replace("app/data/uploads", "data/uploads")
        if os.path.exists(corrected_path):
            from flask import send_file
            return send_file(
                corrected_path,
                as_attachment=True,
                download_name=doc["filename"]
            )
    
    # Fallback: buscar en data/uploads por filename
    filename = doc.get("filename")
    if filename:
        base_dir = Path(__file__).parent.parent
        possible_path = base_dir / "data" / "uploads" / filename
        if possible_path.exists():
            from flask import send_file
            return send_file(
                str(possible_path),
                as_attachment=True,
                download_name=filename
            )
    
    flash("Archivo original no encontrado.", "error")
    return redirect(url_for("admin_documentos"))


@app.route("/admin/fuentes-web", methods=["GET"])
@admin_required
def admin_fuentes_web():
    """Página de administración de fuentes web."""
    docs = app.db_conn.execute_query("""
        SELECT * FROM documents WHERE source_type = 'web' ORDER BY created_at DESC;
    """, fetch=True)
    return render_template("admin/fuentes_web.html", 
                          web_docs=docs, 
                          username=session.get("username"),
                          user_role=session.get("user_role"))


# --- GESTIÓN DE FUENTES WEB ---

@app.route('/web')
@login_required
def web_sources():
    docs = app.db_conn.execute_query("""
        SELECT * FROM documents WHERE source_type = 'web' ORDER BY created_at DESC;
    """, fetch=True)
    
    # Normalizar todas las fechas a naive UTC para evitar mismatch con datetime.now()
    for doc in docs:
        for field in ['last_scraped_at', 'updated_at', 'created_at']:
            if doc.get(field) and hasattr(doc[field], 'tzinfo') and doc[field].tzinfo is not None:
                doc[field] = doc[field].replace(tzinfo=None)
    
    total = len(docs)
    active = len([d for d in docs if d.get('is_indexed')])
    updating = len([d for d in docs if d.get('processing_status') == 'pending'])
    return render_template('web.html', web_docs=docs, total=total, active=active, updating=updating, now=datetime.now())

@app.route('/web/add', methods=['POST'])
@login_required
def web_add():
    url = request.form.get('url', '').strip()
    auto_refresh = request.form.get('auto_refresh') == 'on'
    frequency = request.form.get('frequency', 'manual')
    
    # Usar tool MCP agregar_fuente_web
    try:
        resultado_json = agregar_fuente_web(
            url=url,
            verificar_duplicados=True,
            indexar_inmediatamente=True
        )
        resultado = json.loads(resultado_json)
        
        if resultado.get("status") == "success":
            doc_id = resultado.get("doc_id")
            titulo = resultado.get("titulo", "URL")
            caracteres = resultado.get("caracteres_extraidos", 0)
            
            # Actualizar campos adicionales de web en DB (auto_refresh, frequency)
            conn = app.db_conn.get_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE documents SET auto_refresh=%s, refresh_frequency=%s, last_scraped_at=NOW()
                    WHERE id=%s
                """, (auto_refresh, frequency, doc_id))
            conn.commit()
            conn.close()
            
            flash(f'"{titulo}" indexado correctamente ({caracteres} caracteres)', 'success')
        else:
            flash(f'Error: {resultado.get("message", "Error desconocido")}', 'error')
            
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('web_sources'))

@app.route('/web/delete/<int:doc_id>', methods=['POST'])
@login_required
def web_delete(doc_id):
    try:
        app.rag_service.delete_document(doc_id)
        # Si es una petición AJAX/fetch, devolver JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return jsonify({'success': True, 'message': 'Fuente web eliminada'})
        flash('Fuente web eliminada', 'success')
        return redirect(url_for('web_sources'))
    except Exception as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return jsonify({'success': False, 'error': str(e)}), 500
        flash(f'Error al eliminar: {str(e)}', 'error')
        return redirect(url_for('web_sources'))

@app.route('/web/refresh/<int:doc_id>', methods=['POST'])
@login_required
def web_refresh(doc_id):
    doc = app.persistence.get_document_by_id(doc_id)
    if not doc or not doc.get('source_url'):
        flash('No se encontró la URL original', 'error')
        return redirect(url_for('web_sources'))
    
    scraper = app.web_scraper_service
    result = scraper.scrape_url(doc['source_url'])
    
    if result['success']:
        with open(doc['processed_path'], 'w', encoding='utf-8') as f:
            f.write(result['content'])
        app.rag_service.reindex_document(doc_id)
        
        # Actualizar last_scraped_at
        conn = app.db_conn.get_connection()
        with conn.cursor() as cur:
            cur.execute("UPDATE documents SET last_scraped_at=NOW() WHERE id=%s", (doc_id,))
        conn.commit()
        conn.close()
        
        flash('Fuente actualizada y re-indexada', 'success')
    else:
        flash(f'Error al actualizar: {result["error"]}', 'error')
    
    return redirect(url_for('web_sources'))


# --- MÓDULO ACADÉMICO UNAS ---

@app.route("/academico")
@login_required
def academico():
    """Página principal de integración con sistema académico UNAS."""
    session_valid = session.get("academico_session_valid", False)
    academico_user = session.get("academico_user", None)
    pages = app.academico_service.get_pages()
    
    # Documentos ya indexados del sistema académico
    docs_academico = app.db_conn.execute_query("""
        SELECT id, filename, created_at, last_scraped_at 
        FROM documents 
        WHERE source_type = 'academico' 
        ORDER BY created_at DESC;
    """, fetch=True) or []
    
    return render_template("academico.html",
        session_valid=session_valid,
        academico_user=academico_user,
        pages=pages,
        docs_academico=docs_academico,
        username=session.get("username")
    )

@app.route("/academico/login", methods=["POST"])
@login_required
def academico_login():
    """Paso 1: Carga el login, rellena credenciales, captura CAPTCHA."""
    unas_user = request.form.get("unas_username", "").strip()
    unas_pass = request.form.get("unas_password", "").strip()
    
    if not unas_user or not unas_pass:
        flash("Ingresa tu usuario y contraseña de UNAS.", "error")
        return redirect(url_for("academico"))
    
    # Guardar credenciales temporalmente en sesion (solo para el proceso actual)
    session["_tmp_unas_user"] = unas_user
    session["_tmp_unas_pass"] = unas_pass
    
    result = app.academico_service.start_login_session(unas_user, unas_pass)
    
    if not result["success"]:
        flash(f"Error: {result['error']}", "error")
        return redirect(url_for("academico"))
    
    # Guardar session_id y usertoken para la segunda fase
    session["_academico_session_id"] = result.get("session_id")
    session["_academico_usertoken"] = result.get("usertoken", "")
    session.modified = True
    
    # Pasar imagen del captcha al template
    return render_template("academico.html",
        session_valid=False,
        academico_user=None,
        pages=app.academico_service.get_pages(),
        docs_academico=[],
        username=session.get("username"),
        show_captcha_modal=True,
        captcha_image=result.get("captcha_image"),
    )

@app.route("/academico/submit-captcha", methods=["POST"])
@login_required  
def academico_submit_captcha():
    captcha_solution = request.form.get("captcha_solution", "").strip()
    unas_user = session.get("_tmp_unas_user", "")
    unas_pass = session.get("_tmp_unas_pass", "")
    session_id = session.get("_academico_session_id", "")
    usertoken = session.get("_academico_usertoken", "")
    
    if not captcha_solution or not unas_user or not session_id:
        flash("Sesión expirada. Intenta nuevamente.", "error")
        return redirect(url_for("academico"))
    
    result = app.academico_service.complete_login_with_captcha(
        unas_user, unas_pass, captcha_solution, session_id, usertoken
    )
    
    print(f"[ACADEMICO] resultado: {result}")
    
    session.pop("_tmp_unas_user", None)
    session.pop("_tmp_unas_pass", None)
    session.pop("_academico_session_id", None)
    session.pop("_academico_usertoken", None)
    
    if result["success"]:
        app.academico_service.set_cookies(result["cookies"])
        session["academico_session_valid"] = True
        session["academico_user"] = result["username"]
        session["academico_cookies"] = result["cookies"]
        session.modified = True
        flash(f"✅ Conectado como {result['username']}", "success")
        return redirect(url_for("academico"))
    else:
        flash(f"Error: {result.get('error', 'desconocido')}", "error")
        new_captcha = app.academico_service.start_login_session(unas_user, unas_pass)
        session["_tmp_unas_user"] = unas_user
        session["_tmp_unas_pass"] = unas_pass
        session["_academico_session_id"] = new_captcha.get("session_id")
        session["_academico_usertoken"] = new_captcha.get("usertoken", "")
        session.modified = True
        return render_template("academico.html",
            session_valid=False, academico_user=None,
            pages=app.academico_service.get_pages(),
            docs_academico=[], username=session.get("username"),
            show_captcha_modal=True,
            captcha_image=new_captcha.get("captcha_image") if new_captcha.get("success") else None,
        )

@app.route("/academico/disconnect", methods=["POST"])
@login_required
def academico_disconnect():
    """Desconecta la sesión académica."""
    session.pop("academico_session_valid", None)
    session.pop("academico_user", None)
    session.pop("academico_cookies", None)
    app.academico_service.set_cookies("")
    flash("Sesión académica desconectada.", "info")
    return redirect(url_for("academico"))

@app.route("/academico/chat", methods=["POST"])
@login_required
def academico_chat():
    data = request.get_json()
    user_message = (data or {}).get("message", "").strip()
    
    if not user_message:
        return jsonify({"error": "Mensaje vacío"})
    
    if not session.get("academico_session_valid"):
        return jsonify({"response": "No hay sesión activa. Reconéctate en Académico."})
    
    cookies = session.get("academico_cookies", "")
    
    # Scraping en tiempo real
    try:
        academic_context = app.academico_service.query_realtime(user_message, cookies)
        print(f"[ACAD CONTEXT] len={len(academic_context)} preview={academic_context[:300]}")
    except Exception as e:
        print(f"[ACAD scrape error]: {e}")
        academic_context = ""
    
    if "SESION_EXPIRADA" in (academic_context or ""):
        session["academico_session_valid"] = False
        return jsonify({"response": "Tu sesión de UNAS expiró. Reconéctate en la pestaña Académico."})
    
    try:
        codsem = app.academico_service._get_current_semester(cookies)
    except:
        codsem = "2026-1"
    
    # Llamar directo a Ollama — mismo patrón que generation_service.generate()
    try:
        import requests as http_req
        import os
        
        ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        chat_model = os.environ.get("OLLAMA_CHAT_MODEL", "qwen2.5:3b")
        
        system = (
            "Eres un asistente académico de la UNAS (Universidad Nacional Agraria de la Selva). "
            "Responde en Markdown bien formateado.\n"
            "- Usa tablas Markdown para horarios y notas\n"
            "- Usa **negrita** para códigos de curso y datos importantes\n"
            "- Si un valor es 0 o vacío escribe 'Sin registro aún'\n"
            "- Solo usa la información provista, no inventes datos\n"
            "- Para orden de mérito: indica el puesto del estudiante, "
            "el total de alumnos y sus promedios. No listes todos los compañeros.\n\n"
            f"=== DATOS ACADÉMICOS EN TIEMPO REAL — UNAS {codsem} ===\n"
            f"{academic_context}\n"
            "=== FIN DE DATOS ==="
        )
        
        resp = http_req.post(
            f"{ollama_url}/api/chat",
            json={
                "model": chat_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_message}
                ],
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "num_predict": 1024
                }
            },
            timeout=180
        )
        resp.raise_for_status()
        content = resp.json().get("message", {}).get("content", "").strip()
        
        print(f"[ACAD] OK — context={len(academic_context)} response={len(content)}")
        return jsonify({"response": content or "El modelo no generó respuesta."})
    
    except http_req.exceptions.Timeout:
        return jsonify({"error": "⏱️ El modelo tardó demasiado. Intenta nuevamente."})
    except Exception as e:
        print(f"[ACAD ERROR]: {e}")
        import traceback; traceback.print_exc()
        return jsonify({"error": f"Error: {str(e)}"})

@app.route("/academico/extract", methods=["POST"])
@login_required
def academico_extract():
    """Extrae una página del sistema académico y la indexa."""
    if not session.get("academico_session_valid"):
        flash("Primero conecta tu sesión académica.", "error")
        return redirect(url_for("academico"))
    
    page_key = request.form.get("page_key", "").strip()
    pages = app.academico_service.get_pages()
    
    if page_key not in pages:
        flash("Página no válida.", "error")
        return redirect(url_for("academico"))
    
    page_info = pages[page_key]
    
    # Restaurar cookies
    cookies_str = session.get("academico_cookies", "")
    if cookies_str:
        app.academico_service.set_cookies(cookies_str)
    
    result = app.academico_service.scrape_page(page_info["path"])
    
    if not result["success"]:
        flash(f"Error al extraer: {result['error']}", "error")
        return redirect(url_for("academico"))
    
    import uuid
    
    processed_name = f"{uuid.uuid4().hex[:8]}_academico_{page_key}.txt"
    processed_path = os.path.join("data/processed", processed_name)
    
    os.makedirs("data/processed", exist_ok=True)
    with open(processed_path, "w", encoding="utf-8") as f:
        f.write(f"# {result['title']}\n")
        f.write(f"Fuente: {result['url']}\n")
        f.write(f"Usuario: {session.get('academico_user', 'N/A')}\n\n")
        f.write(result["content"])
    
    user_id = session.get("user_id")
    doc_id = app.persistence.register_document(
        filename=f"[UNAS] {page_info['label']}",
        original_path=result["url"],
        processed_path=os.path.abspath(processed_path),
        user_id=user_id
    )
    app.persistence.update_document_status(
        doc_id,
        processing_status="completed",
        processed_path=os.path.abspath(processed_path)
    )
    
    conn = app.db_conn.get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE documents SET source_url=%s, source_type='academico',
            last_scraped_at=NOW() WHERE id=%s
        """, (result["url"], doc_id))
    conn.commit()
    conn.close()
    
    app.rag_service.index_document(doc_id, os.path.abspath(processed_path))
    flash(f"'{page_info['label']}' indexado ({result['word_count']} palabras)", "success")
    return redirect(url_for("academico"))

@app.route("/academico/delete/<int:doc_id>", methods=["POST"])
@login_required
def academico_delete(doc_id):
    """Elimina un documento académico indexado."""
    app.rag_service.delete_document(doc_id)
    flash("Documento académico eliminado.", "info")
    return redirect(url_for("academico"))
