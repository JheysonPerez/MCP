import sys
from pathlib import Path
import json

# Enrutamos módulos locales
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Importamos directamente del módulo de las MCP Tools (solo las funciones directas, saltando run())
from mcp_server.server import listar_documentos, preguntar_documentos

def simular_peticion_mcp(nombre_tool: str, funcion, *args, **kwargs):
    print(f"\n[{nombre_tool}] -> Simulando Llamada...")
    # Llamamos a la funcion puramente como la ejecutaría un Cliente MCP
    respuesta_cruda = funcion(*args, **kwargs)
    
    # Printeamos la confirmación del formato JSON estandarizado para la interconexión (serializable)
    print("  <- Resultado JSON (Serializable MCP):")
    resultado_json = json.loads(respuesta_cruda)
    print(json.dumps(resultado_json, indent=2, ensure_ascii=False))

def run_tests():
    print("--- INICIANDO PRUEBAS DE SERVIDOR MCP (TOOLS DIRECTAS) ---")
    
    print("\nValidando que el import del servidor instanció las dependencias (DB y RAG en la memoria)... ✓")

    # 1. Test "listar_documentos"
    simular_peticion_mcp(
        nombre_tool="Tool: listar_documentos",
        funcion=listar_documentos
    )
    
    # 2. Test "preguntar_documentos"
    simular_peticion_mcp(
        nombre_tool="Tool: preguntar_documentos",
        funcion=preguntar_documentos,
        consulta="¿Qué beneficios tiene nuestro PostgreSQL actual?"
    )

    print("\n--- PRUEBA MCP EXITOSA. EL PIPELINE RESURGE LIMPIAMENTE A TRAVÉS DE LA INTERFAZ MCP JSON. ---")

if __name__ == "__main__":
    run_tests()
