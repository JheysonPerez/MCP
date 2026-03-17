from flask import current_app as app
from flask import render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash
from pathlib import Path
import os

ALLOWED_EXTENSIONS = {'pdf', 'docx', 'txt'}

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
            # Buscar usuario real con hash en la base de datos
            result = app.db_conn.execute_query(
                "SELECT id, username, password_hash FROM users WHERE username = %s LIMIT 1;",
                (username,), fetch=True
            )
            
            if result and result[0].get("password_hash") and check_password_hash(result[0]["password_hash"], password):
                session["user_id"] = result[0]["id"]
                session["username"] = result[0]["username"]
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
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    stats = _get_stats()
    return render_template("dashboard.html", stats=stats, username=session.get("username"))

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
def documentos():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    docs = app.db_conn.execute_query("""
        SELECT id, filename, created_at, processing_status, is_indexed, chunk_count 
        FROM documents 
        ORDER BY created_at DESC;
    """, fetch=True)
    return render_template("documentos.html", documentos=docs, username=session.get("username"))


@app.route("/upload", methods=["POST"])
def upload_document():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
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
def reindex_document(doc_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    try:
        app.rag_service.reindex_document(doc_id)
        flash(f"Documento #{doc_id} reindexado con éxito.", "success")
    except Exception as e:
        flash(f"Error al reindexar: {str(e)}", "error")
        
    return redirect(url_for("documentos"))

@app.route("/documentos/delete/<int:doc_id>", methods=["POST"])
def delete_document(doc_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    try:
        app.rag_service.delete_document(doc_id)
        flash(f"Documento #{doc_id} eliminado correctamente.", "success")
    except Exception as e:
        flash(f"Error al eliminar: {str(e)}", "error")
        
    return redirect(url_for("documentos"))

@app.route("/documentos/sync", methods=["POST"])
def sync_all():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    try:
        app.rag_service.sync_repository_to_index()
        flash("Repositorio sincronizado con éxito.", "success")
    except Exception as e:
        flash(f"Error en sincronización: {str(e)}", "error")
        
    return redirect(url_for("documentos"))


# --- CONSULTA RAG ---

@app.route("/consultar", methods=["GET", "POST"])
def consultar():
    if "user_id" not in session:
        return redirect(url_for("login"))

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
    if request.method == "POST":
        pregunta = request.form.get("pregunta", "").strip()
        scope = request.form.get("scope", "all")
        doc_seleccionado = request.form.get("doc_id", "").strip() or None

        if not pregunta:
            flash("Debes ingresar una pregunta válida.", "error")
        else:
            # Filtro real para el motor RAG
            filtro_doc = doc_seleccionado if (scope == "doc" and doc_seleccionado) else None

            try:
                resultado = app.rag_service.generate_response(
                    pregunta, top_k=3, document_id=filtro_doc
                )
                respuesta_rag = resultado["answer"].strip()
                fuentes = resultado["sources"]
                pregunta_hecha = pregunta
            except Exception as e:
                flash(f"Error al consultar el sistema RAG: {str(e)}", "error")

    return render_template(
        "consultar.html",
        respuesta_rag=respuesta_rag,
        pregunta_hecha=pregunta_hecha,
        fuentes=fuentes,
        scope=scope,
        doc_seleccionado=doc_seleccionado,
        documentos_lista=documentos_lista,
        username=session.get("username")
    )



# --- HISTORIAL ---

@app.route("/historial", methods=["GET"])
def historial():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    try:
        rows = app.db_conn.execute_query("""
            SELECT q.query_text, r.response_text, q.created_at, u.username
            FROM queries q
            LEFT JOIN responses r ON r.query_id = q.id
            LEFT JOIN users u ON u.id = q.user_id
            ORDER BY q.created_at DESC
            LIMIT 50;
        """, fetch=True)
    except:
        rows = []
    
    return render_template("historial.html", historial=rows, username=session.get("username"))
