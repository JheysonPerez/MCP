from flask import current_app as app
from flask import render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash
from pathlib import Path
import os
import re
from datetime import datetime, timezone

from .decorators import login_required, admin_required

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
    docs = app.db_conn.execute_query("""
        SELECT id, filename, created_at, processing_status, is_indexed, chunk_count 
        FROM documents 
        ORDER BY created_at DESC;
    """, fetch=True)
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
    
    try:
        app.rag_service.reindex_document(doc_id)
        flash(f"Documento #{doc_id} reindexado con éxito.", "success")
    except Exception as e:
        flash(f"Error al reindexar: {str(e)}", "error")
        
    return redirect(url_for("documentos"))

@app.route("/documentos/delete/<int:doc_id>", methods=["POST"])
@admin_required
def delete_document(doc_id):
    
    try:
        app.rag_service.delete_document(doc_id)
        flash(f"Documento #{doc_id} eliminado correctamente.", "success")
    except Exception as e:
        flash(f"Error al eliminar: {str(e)}", "error")
        
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
                    except Exception as e:
                        print(f"[ERROR] No se pudo obtener ID del documento: {e}")

            try:
                # Aumentado top_k=10 para recuperar más contexto del documento
                resultado = app.rag_service.generate_response(
                    pregunta, top_k=10, document_id=filtro_doc,
                    chat_history=chat_history
                )
                respuesta_rag = resultado["answer"].strip()
                
                # Deduplicar fuentes por filename, manteniendo el de mayor score
                sources = resultado.get("sources", [])
                seen_files = {}
                for source in sources:
                    fname = source.get("filename", "")
                    if fname not in seen_files or source.get("score", 0) > seen_files[fname].get("score", 0):
                        seen_files[fname] = source
                fuentes = list(seen_files.values())
                
                pregunta_hecha = pregunta

                # Actualizar historial en sesión para la PRÓXIMA consulta
                # (No agregamos el turno actual al chat_history que enviamos al template)
                chat_history.append({
                    "pregunta": pregunta,
                    "respuesta": respuesta_rag
                })
                session["chat_history"] = chat_history[-5:]
                session.modified = True

            except Exception as e:
                flash(f"Error al consultar el sistema RAG: {str(e)}", "error")

    # Turno actual para mostrar por separado del historial
    turno_actual = {
        "pregunta": pregunta_hecha, 
        "respuesta": respuesta_rag, 
        "fuentes": fuentes
    } if pregunta_hecha else None

    return render_template(
        "consultar.html",
        turno_actual=turno_actual,
        scope=scope,
        doc_seleccionado=doc_seleccionado,
        documentos_lista=documentos_lista,
        chat_history=chat_history[:-1] if turno_actual else chat_history, # Evitar mostrar el último si ya está en turno_actual
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
    
    documentos_lista = app.db_conn.execute_query(
        "SELECT id, filename FROM documents WHERE is_indexed = TRUE ORDER BY filename;",
        fetch=True
    ) or []
    
    generados = app.generation_service.get_all()
    
    return render_template("generar.html",
        documentos_lista=documentos_lista,
        generados=generados,
        username=session.get("username")
    )

@app.route("/generar/crear", methods=["POST"])
@login_required
def generar_crear():
    
    prompt = request.form.get("prompt", "").strip()
    mode = request.form.get("mode", "prompt_libre")
    doc_format = request.form.get("formato", "markdown")
    source_doc_id = request.form.get("source_doc_id", "").strip()
    
    if not prompt:
        flash("Debes ingresar instrucciones para generar el documento.", "error")
        return redirect(url_for("generar"))
    
    source_doc_ids = [int(source_doc_id)] if source_doc_id else []
    
    try:
        resultado = app.generation_service.generate(
            prompt=prompt,
            mode=mode,
            source_doc_ids=source_doc_ids,
            doc_format=doc_format,
            user_id=session.get("user_id")
        )
        
        if resultado["success"]:
            flash(f"Documento generado: {resultado['title']}", "success")
            return redirect(url_for("generar_ver", gen_id=resultado["id"]))
        else:
            flash(f"Error al generar: {resultado['error']}", "error")
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
            return Response(
                content,
                mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                headers={"Content-Disposition": 
                         f"attachment; filename={safe_title}.docx"}
            )
        except Exception as e:
            flash(f"Error al exportar DOCX: {str(e)}", "error")
            return redirect(url_for("generar_ver", gen_id=gen_id))

    elif fmt == "pdf":
        try:
            content = app.generation_service.export_pdf(gen_id)
            return Response(
                content,
                mimetype="application/pdf",
                headers={"Content-Disposition": 
                         f"attachment; filename={safe_title}.pdf"}
            )
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


# --- GESTIÓN DE FUENTES WEB ---

@app.route('/web')
@login_required
def web_sources():
    docs = app.db_conn.execute_query("""
        SELECT * FROM documents WHERE source_type = 'web' ORDER BY created_at DESC;
    """, fetch=True)
    total = len(docs)
    active = len([d for d in docs if d.get('is_indexed')])
    updating = len([d for d in docs if d.get('processing_status') == 'pending'])
    return render_template('web.html', web_docs=docs, total=total, active=active, updating=updating, now=datetime.utcnow())

@app.route('/web/add', methods=['POST'])
@login_required
def web_add():
    url = request.form.get('url', '').strip()
    auto_refresh = request.form.get('auto_refresh') == 'on'
    frequency = request.form.get('frequency', 'manual')
    
    scraper = app.web_scraper_service
    
    if not scraper.is_valid_url(url):
        flash('URL inválida. Asegúrate de incluir http:// o https://', 'error')
        return redirect(url_for('web_sources'))
    
    # Verificar si la URL ya existe (normalizar URL para comparación)
    existing = app.db_conn.execute_query(
        "SELECT id, filename FROM documents WHERE source_url = %s OR original_path = %s LIMIT 1",
        (url, url),
        fetch=True
    )
    if existing:
        flash(f'Esta URL ya está indexada como "{existing[0]["filename"]}". Elimínala primero si deseas re-indexarla.', 'warning')
        return redirect(url_for('web_sources'))
    
    try:
        result = scraper.scrape_url(url)
        if not result['success']:
            flash(f'Error al extraer: {result["error"]}', 'error')
            return redirect(url_for('web_sources'))
        
        # Guardar como archivo .txt procesado
        import uuid, os
        safe_name = re.sub(r'[^a-z0-9]', '_', url.lower())[:40]
        filename = f"web_{safe_name}.txt"
        safe_uuid = uuid.uuid4().hex[:8]
        processed_name = f"{safe_uuid}_{filename}"
        processed_path = os.path.join("data/processed", processed_name)
        
        os.makedirs("data/processed", exist_ok=True)
        with open(processed_path, 'w', encoding='utf-8') as f:
            f.write(result['content'])
        
        # Registrar en DB
        user_id = app.persistence.create_or_get_user(
            session.get('username'), session.get('username') + '@local'
        )
        doc_id = app.persistence.register_document(
            filename=result['title'][:100],
            original_path=url,
            processed_path=os.path.abspath(processed_path),
            user_id=user_id
        )
        app.persistence.update_document_status(
            doc_id,
            processing_status='completed',
            processed_path=os.path.abspath(processed_path)
        )
        
        # Actualizar campos web
        conn = app.db_conn.get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE documents SET source_url=%s, source_type='web',
                auto_refresh=%s, refresh_frequency=%s, last_scraped_at=NOW()
                WHERE id=%s
            """, (url, auto_refresh, frequency, doc_id))
        conn.commit()
        conn.close()
        
        # Indexar
        app.rag_service.index_document(doc_id, os.path.abspath(processed_path))
        flash(f'"{result["title"]}" indexado correctamente ({result["word_count"]} palabras)', 'success')
        
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('web_sources'))

@app.route('/web/delete/<int:doc_id>', methods=['POST'])
@login_required
def web_delete(doc_id):
    app.rag_service.delete_document(doc_id)
    flash('Fuente web eliminada', 'success')
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
