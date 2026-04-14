import sys
from pathlib import Path

# Permitir resolución del directorio raíz del proyecto
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP
from mcp_server.dependencies import rag_service, document_service, db_conn, persistence, retrieval_service, web_scraper_service, generation_service
import json
import logging
import os
from datetime import datetime

logging.basicConfig(level=logging.INFO)

# Inicializamos el servidor MCP usando FastMCP
mcp = FastMCP("Servidor RAG EPIIS")

@mcp.tool()
def listar_documentos(
    estado: str = "all",
    limite: int = 20,
    tipo_fuente: str = "all"
) -> str:
    """
    Lista documentos del repositorio con filtros opcionales.

    Args:
        estado: Filtrar por estado ("all", "indexado", "pendiente", "error", "deleted")
        limite: Máximo de resultados (1-100)
        tipo_fuente: Filtrar por tipo ("all", "file", "web")

    Returns:
        JSON con lista de documentos filtrados
    """
    try:
        limite = max(1, min(100, limite))

        # Construir query dinámica
        where_clauses = []
        params = []

        if estado == "indexado":
            where_clauses.append("is_indexed = TRUE")
        elif estado == "pendiente":
            where_clauses.append("processing_status = 'pending'")
        elif estado == "error":
            where_clauses.append("processing_status = 'failed'")
        elif estado == "deleted":
            where_clauses.append("processing_status = 'deleted'")

        if tipo_fuente == "file":
            where_clauses.append("(source_type = 'file' OR source_type IS NULL)")
        elif tipo_fuente == "web":
            where_clauses.append("source_type = 'web'")

        where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        query = f"""
            SELECT id, filename, processing_status, is_indexed, chunk_count, source_type, created_at, uploaded_by
            FROM documents
            {where_sql}
            ORDER BY created_at DESC
            LIMIT %s;
        """

        if params:
            params.append(limite)
            rows = db_conn.execute_query(query, tuple(params), fetch=True)
        else:
            rows = db_conn.execute_query(query, (limite,), fetch=True)

        if not rows:
            return json.dumps({"status": "success", "message": "No hay documentos que coincidan con los filtros.", "data": [], "total": 0})

        # Limpieza para json.dumps (formateo el datetime)
        for r in rows:
            r['created_at'] = str(r['created_at'])
            r['estado'] = 'Indexado' if r['is_indexed'] else ('Error' if r['processing_status'] == 'failed' else ('Eliminado' if r['processing_status'] == 'deleted' else 'Pendiente'))
            r['tipo'] = 'Web' if r['source_type'] == 'web' else 'Archivo'

        return json.dumps({
            "status": "success",
            "total": len(rows),
            "filtros_aplicados": {"estado": estado, "limite": limite, "tipo_fuente": tipo_fuente},
            "data": rows
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})

@mcp.tool()
def consultar_documentos(
    consulta: str,
    documento_id: str = None,
    incluir_fuentes: bool = True,
    top_k: int = 5
) -> str:
    """
    Realiza una consulta RAG al repositorio documental.

    Args:
        consulta: Pregunta en lenguaje natural
        documento_id: ID numérico o nombre de archivo para filtrar (opcional)
        incluir_fuentes: Incluir documentos fuente en la respuesta
        top_k: Número de chunks a recuperar (1-10)

    Returns:
        JSON con respuesta del RAG y fuentes utilizadas
    """
    try:
        # Validar top_k
        top_k = max(1, min(10, top_k))

        # Convertir documento_id a filtro si existe
        filtro_doc = None
        if documento_id:
            if documento_id.isdigit():
                filtro_doc = documento_id
            else:
                # Buscar por nombre de archivo
                doc_result = db_conn.execute_query(
                    "SELECT id FROM documents WHERE filename = %s LIMIT 1",
                    (documento_id,), fetch=True
                )
                if doc_result:
                    filtro_doc = str(doc_result[0]['id'])

        # Ejecutar consulta RAG
        resultado = rag_service.generate_response(
            consulta,
            top_k=top_k,
            document_id=filtro_doc
        )

        response = {
            "status": "success",
            "respuesta": resultado["answer"],
            "documento_filtrado": documento_id if filtro_doc else None
        }

        if incluir_fuentes:
            response["fuentes"] = [
                {"documento": f.get("filename", f"ID:{f.get('document_id', 'unknown')}"), "score": round(f.get("score", 0), 3)}
                for f in resultado.get("sources", [])[:3]
            ]

        return json.dumps(response, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


# Alias para compatibilidad hacia atrás
@mcp.tool()
def preguntar_documentos(consulta: str) -> str:
    """
    [DEPRECATED] Usar consultar_documentos() en su lugar.
    Ejecuta el pipeline RAG con parámetros por defecto.
    """
    return consultar_documentos(consulta, documento_id=None, incluir_fuentes=True, top_k=3)

@mcp.tool()
def resumir_documento(document_id_name: str) -> str:
    """
    Genera un resumen específico para un nombre de documento almacenado mediante RAG condicionado.
    """
    try:
        prompt = f"Resume los puntos principales que traten acerca de o provengan exclusivamente del archivo '{document_id_name}', si no hay info, devuélvelo."
        resultado = rag_service.generate_response(prompt, top_k=4)
        return json.dumps({
            "status": "success",
            "resumen_generado": resultado["answer"]
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


@mcp.tool()
def estadisticas_repositorio(
    incluir_detalle_documentos: bool = False,
    incluir_estadisticas_consultas: bool = True
) -> str:
    """
    Obtiene estadísticas del estado del repositorio documental.

    Args:
        incluir_detalle_documentos: Incluir lista detallada de documentos
        incluir_estadisticas_consultas: Incluir stats de consultas RAG

    Returns:
        JSON con estadísticas completas
    """
    try:
        stats = {
            "status": "success",
            "timestamp": str(datetime.now())
        }

        # Conteos principales
        doc_count = db_conn.execute_query(
            "SELECT COUNT(*) as total FROM documents;", fetch=True
        )[0]["total"]

        indexed_count = db_conn.execute_query(
            "SELECT COUNT(*) as total FROM documents WHERE is_indexed = TRUE;", fetch=True
        )[0]["total"]

        pending_count = db_conn.execute_query(
            "SELECT COUNT(*) as total FROM documents WHERE processing_status = 'pending';", fetch=True
        )[0]["total"]

        failed_count = db_conn.execute_query(
            "SELECT COUNT(*) as total FROM documents WHERE processing_status = 'failed';", fetch=True
        )[0]["total"]

        web_count = db_conn.execute_query(
            "SELECT COUNT(*) as total FROM documents WHERE source_type = 'web';", fetch=True
        )[0]["total"]

        file_count = doc_count - web_count

        stats["documentos"] = {
            "total": doc_count,
            "indexados": indexed_count,
            "pendientes": pending_count,
            "con_error": failed_count,
            "fuentes_web": web_count,
            "archivos": file_count,
            "tasa_indexacion": round(indexed_count / doc_count * 100, 1) if doc_count > 0 else 0
        }

        # Estadísticas de consultas
        if incluir_estadisticas_consultas:
            query_count = db_conn.execute_query(
                "SELECT COUNT(*) as total FROM queries;", fetch=True
            )[0]["total"]

            recent_queries = db_conn.execute_query(
                """SELECT COUNT(*) as total FROM queries
                   WHERE created_at > NOW() - INTERVAL '24 hours';""", fetch=True
            )[0]["total"]

            stats["consultas"] = {
                "total_historicas": query_count,
                "ultimas_24h": recent_queries
            }

        # Detalle de documentos (opcional)
        if incluir_detalle_documentos:
            docs = db_conn.execute_query(
                """SELECT id, filename, processing_status, is_indexed, chunk_count, source_type, created_at
                   FROM documents ORDER BY created_at DESC LIMIT 20;""", fetch=True
            )
            for d in docs:
                d['created_at'] = str(d['created_at'])
            stats["ultimos_documentos"] = docs

        # Resumen del sistema
        query_count_str = f"{stats.get('consultas', {}).get('total_historicas', 0)} consultas históricas"
        stats["resumen"] = (
            f"Repositorio con {doc_count} documentos ({indexed_count} indexados, "
            f"{web_count} fuentes web). {query_count_str}."
        )

        return json.dumps(stats, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


@mcp.tool()
def eliminar_documento(
    doc_id: int,
    modo: str = "soft"
) -> str:
    """
    Elimina un documento del repositorio.

    Args:
        doc_id: ID del documento a eliminar
        modo: "soft" (desactiva) o "hard" (elimina físicamente)

    Returns:
        JSON confirmando eliminación
    """
    try:
        # Verificar que existe
        doc = persistence.get_document_by_id(doc_id)
        if not doc:
            return json.dumps({"status": "error", "message": f"Documento {doc_id} no encontrado"})

        filename = doc['filename']

        if modo == "hard":
            # Eliminar físicamente via RAG service
            rag_service.delete_document(doc_id)
            mensaje = f"Documento '{filename}' (ID: {doc_id}) eliminado permanentemente."
        else:
            # Soft delete: marcar como deleted e inactivo
            db_conn.execute_query(
                "UPDATE documents SET processing_status = 'deleted', is_indexed = FALSE WHERE id = %s",
                (doc_id,)
            )
            # Remover de vector store si está disponible
            if hasattr(retrieval_service, 'remove_document_chunks'):
                retrieval_service.remove_document_chunks(doc_id)
            mensaje = f"Documento '{filename}' (ID: {doc_id}) desactivado (soft delete)."

        return json.dumps({
            "status": "success",
            "doc_id": doc_id,
            "modo": modo,
            "mensaje": mensaje
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


@mcp.tool()
def reindexar_documento(doc_id: int) -> str:
    """
    Fuerza la reindexación semántica de un documento.
    Util si el documento ya existe pero no está indexado correctamente.

    Args:
        doc_id: ID del documento a reindexar

    Returns:
        JSON con resultado de la operación
    """
    try:
        # Verificar que existe y está procesado
        doc = persistence.get_document_by_id(doc_id)
        if not doc:
            return json.dumps({"status": "error", "message": f"Documento {doc_id} no encontrado"})

        if doc['processing_status'] != 'completed':
            return json.dumps({
                "status": "error",
                "message": f"Documento no está procesado (estado: {doc['processing_status']})"
            })

        processed_path = doc.get('processed_path')
        if not processed_path or not os.path.exists(processed_path):
            return json.dumps({"status": "error", "message": "Archivo procesado no encontrado"})

        # Ejecutar reindexación
        rag_service.reindex_document(doc_id)

        # Obtener estado actualizado
        doc_updated = persistence.get_document_by_id(doc_id)

        return json.dumps({
            "status": "success",
            "doc_id": doc_id,
            "filename": doc['filename'],
            "chunks_indexados": doc_updated.get('chunk_count', 0),
            "mensaje": f"Documento '{doc['filename']}' reindexado correctamente."
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


@mcp.tool()
def agregar_fuente_web(
    url: str,
    verificar_duplicados: bool = True,
    indexar_inmediatamente: bool = True
) -> str:
    """
    Scrapea una URL web y la agrega como fuente documental al repositorio.

    Args:
        url: URL completa a scrapear (debe incluir http:// o https://)
        verificar_duplicados: Rechazar si la URL ya está indexada
        indexar_inmediatamente: Procesar e indexar tras scrapear

    Returns:
        JSON con resultado del scraping y metadata del documento
    """
    try:
        import uuid
        import re
        import requests

        # Validar URL
        if not web_scraper_service.is_valid_url(url):
            return json.dumps({
                "status": "error",
                "message": "URL inválida. Debe incluir http:// o https://"
            })

        # Verificar duplicados
        if verificar_duplicados:
            existing = db_conn.execute_query(
                "SELECT id, filename FROM documents WHERE source_url = %s OR original_path = %s LIMIT 1",
                (url, url), fetch=True
            )
            if existing:
                return json.dumps({
                    "status": "error",
                    "message": f"URL ya indexada como '{existing[0]['filename']}' (ID: {existing[0]['id']})"
                })

        # Scrapear
        result = web_scraper_service.scrape_url(url)
        if not result.get('success'):
            return json.dumps({
                "status": "error",
                "message": f"Error al extraer: {result.get('error', 'Error desconocido')}"
            })

        # Guardar como documento
        content = result.get('content', '')
        title = result.get('title', 'Web sin titulo')
        safe_title = re.sub(r'[^\w\s-]', '', title).strip()[:50]
        filename = f"web_{safe_title}_{uuid.uuid4().hex[:8]}.txt"

        # Guardar en processed
        processed_path = document_service.processed_dir / filename
        processed_path.write_text(content, encoding='utf-8')

        # Registrar en DB
        user_id = persistence.create_or_get_user("sistema", "sistema@local.epiis")
        doc_id = persistence.register_document(
            filename=filename,
            original_path=url,
            processed_path=str(processed_path),
            user_id=user_id,
            source_type='web',
            source_url=url
        )

        # Indexar si se solicita
        chunks_count = 0
        if indexar_inmediatamente:
            rag_service.index_document(doc_id, str(processed_path))
            doc_updated = persistence.get_document_by_id(doc_id)
            chunks_count = doc_updated.get('chunk_count', 0)

        return json.dumps({
            "status": "success",
            "doc_id": doc_id,
            "url": url,
            "titulo": title,
            "filename": filename,
            "caracteres_extraidos": len(content),
            "indexado": indexar_inmediatamente,
            "chunks_generados": chunks_count,
            "mensaje": f"URL agregada exitosamente como '{filename}'"
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


@mcp.tool()
def generar_documento(
    prompt: str,
    tipo: str = "libre",
    modo: str = "prompt_libre",
    documento_base_id: str = None
) -> str:
    """
    Genera un documento usando IA basado en el repositorio o un documento específico.

    Args:
        prompt: Instrucciones para la generacion del documento
        tipo: Tipo de documento ("libre", "informe", "acta", "memo", "resolucion", "oficio")
        modo: Fuente de contexto ("prompt_libre", "basado_repositorio", "basado_documento")
        documento_base_id: ID o nombre del documento base (si modo = "basado_documento")

    Returns:
        JSON con documento generado y metadatos
    """
    try:
        # Validar modo basado_documento
        if modo == "basado_documento" and not documento_base_id:
            return json.dumps({
                "status": "error",
                "message": "documento_base_id es requerido cuando modo = 'basado_documento'"
            })

        # Construir prompt enriquecido según modo
        if modo == "basado_repositorio":
            enriched_prompt = f"Basandote en el repositorio documental: {prompt}"
            top_k = 8
            filtro_doc = None
        elif modo == "basado_documento":
            # Resolver documento_base_id a ID numerico
            if documento_base_id.isdigit():
                filtro_doc = documento_base_id
                doc_name = f"ID:{documento_base_id}"
            else:
                doc_result = db_conn.execute_query(
                    "SELECT id FROM documents WHERE filename = %s LIMIT 1",
                    (documento_base_id,), fetch=True
                )
                if not doc_result:
                    return json.dumps({"status": "error", "message": f"Documento '{documento_base_id}' no encontrado"})
                filtro_doc = str(doc_result[0]['id'])
                doc_name = documento_base_id

            enriched_prompt = f"Basandote exclusivamente en el documento '{doc_name}': {prompt}"
            top_k = 10
        else:  # prompt_libre
            enriched_prompt = prompt
            top_k = 5
            filtro_doc = None

        # Agregar tipo de documento al prompt
        if tipo != "libre":
            enriched_prompt = f"Genera un {tipo} institucional universitario. {enriched_prompt}"

        # Generar via RAG service
        resultado = rag_service.generate_response(
            enriched_prompt,
            top_k=top_k,
            document_id=filtro_doc
        )

        doc_generado = resultado.get("answer", "")

        # Guardar en DB via generation_service
        gen_id = None
        try:
            gen_result = generation_service.generate(
                prompt=prompt,
                doc_type=tipo,
                mode=modo,
                source_doc_ids=[int(filtro_doc)] if filtro_doc else [],
                user_id=None
            )
            gen_id = gen_result.get('id')
        except Exception:
            # Si falla el guardado, continuamos sin ID
            pass

        return json.dumps({
            "status": "success",
            "documento_generado": doc_generado,
            "tipo": tipo,
            "modo": modo,
            "id_guardado": gen_id,
            "tokens_fuente": len(resultado.get("sources", []))
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


# Alias legacy para compatibilidad
@mcp.tool()
def generar_informe_simple(tema: str) -> str:
    """
    [DEPRECATED] Usar generar_documento() en su lugar.
    Genera un informe simple sobre un tema.
    """
    return generar_documento(
        prompt=f"Escribe un informe gerencial sobre: {tema}",
        tipo="informe",
        modo="basado_repositorio"
    )


def run():
    """
    Inicia el transporte stdio, ideal para que lo consuma Claude Desktop u otros clientes MCP.
    """
    logging.info("Iniciando MCP Server 'Servidor RAG EPIIS' sobre STDIO...")
    mcp.run(transport='stdio')

if __name__ == "__main__":
    run()
