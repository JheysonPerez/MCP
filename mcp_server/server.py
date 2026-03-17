import sys
from pathlib import Path

# Permitir resolución del directorio raíz del proyecto
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP
from mcp_server.dependencies import rag_service, document_service, db_conn
import json
import logging

logging.basicConfig(level=logging.INFO)

# Inicializamos el servidor MCP usando FastMCP
mcp = FastMCP("Servidor RAG EPIIS")

@mcp.tool()
def listar_documentos() -> str:
    """
    Recupera y devuelve una lista de todo el historial de documentos registrados en la Base de Datos PostgreSQL.
    """
    try:
        query = "SELECT id, filename, uploaded_by, created_at FROM documents ORDER BY id DESC LIMIT 50;"
        rows = db_conn.execute_query(query, fetch=True)
        if not rows:
            return json.dumps({"status": "success", "message": "No hay documentos en la base de datos.", "data": []})
            
        # Limpieza para json.dumps (formateo el datetime)
        for r in rows:
            r['created_at'] = str(r['created_at'])
            
        return json.dumps({"status": "success", "data": rows}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})

@mcp.tool()
def preguntar_documentos(consulta: str) -> str:
    """
    Ejecuta el pipeline RAG. Toma el contexto de la BBDD Vectorial In-Memory y llama a Ollama Generativo
    para que conteste formuladamente, persistiendo la query a la DB relacional.
    """
    try:
        resultado = rag_service.generate_response(consulta, top_k=3)
        return json.dumps({
            "status": "success",
            "respuesta": resultado["answer"],
            "fuentes_usadas": [{"documento": f["document_id"], "puntaje": f["score"]} for f in resultado["sources"]]
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})

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
def generar_informe_simple(tema: str) -> str:
    """
    Redacta un reporte estilo informe en crudo partiendo del conocimiento transversal extraído del RAG base.
    """
    try:
         prompt = f"Escribe de forma formal y estructurada un corto informe gerencial en torno a la temática: '{tema}'. Usa únicamente el contexto."
         resultado = rag_service.generate_response(prompt, top_k=5)
         return json.dumps({
             "status": "success",
             "informe": resultado["answer"]
         }, ensure_ascii=False)
    except Exception as e:
         return json.dumps({"status": "error", "message": str(e)})

def run():
    """
    Inicia el transporte stdio, ideal para que lo consuma Claude Desktop u otros clientes MCP.
    """
    logging.info("Iniciando MCP Server 'Servidor RAG EPIIS' sobre STDIO...")
    mcp.run(transport='stdio')

if __name__ == "__main__":
    run()
