import asyncio
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Importamos las clases del cliente MCP nativo en Python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    print("--- INICIANDO CLIENTE MCP REAL PARA PRUEBA ---")
    
    # 1. Configuramos los parámetros para levantar el servidor como un subproceso
    # Esto es exáctamente lo que hace Claude Desktop internamente.
    server_path = str(Path(__file__).resolve().parent.parent / "mcp_server" / "server.py")
    
    server_params = StdioServerParameters(
        command=sys.executable, # Usa el binario de Python activo en el virtual environment
        args=[server_path]
    )
    
    print(f"1. Levantando subproceso del servidor MCP en: {server_path}")
    
    # stdio_client lanza el servicio y conecta las tuberías estándar (stdin/stdout)
    async with stdio_client(server_params) as (read, write):
        print("2. Iniciando sesión MCP y enviando paquete de Handshake ('initialize')...")
        
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("   ✓ Handshake completado exitosamente con el Servidor.")
            
            # 3. Listar herramientas
            print("\n3. Solicitando lista de herramientas (Tools) registradas...")
            tools_response = await session.list_tools()
            
            print("   [Herramientas Devueltas por Protocolo MCP]:")
            for tool in tools_response.tools:
                print(f"    - {tool.name}: {tool.description[:70]}...")
            
            # 4. Llamar a una herramienta y obtener la respuesta serializada
            print("\n4. Ejecutando la herramienta 'listar_documentos' vía JSON-RPC...")
            result = await session.call_tool("listar_documentos", arguments={})
            
            print("\n   [Respuesta Deserializada del Servidor]:")
            for content in result.content:
                if content.type == "text":
                    try:
                        # Si devuelve JSON la tool internamente, lo formateamos para verlo lindo
                        data = json.loads(content.text)
                        print(json.dumps(data, indent=2, ensure_ascii=False))
                    except json.JSONDecodeError:
                        print(content.text)
                        
    print("\n--- ¡PRUEBA DE PROTOCOLO MCP CLIENTE-SERVIDOR EXITOSA! ---")

if __name__ == "__main__":
    # Necesitamos asyncio para el cliente MCP, ya que su interfaz de transporte es asíncrona
    asyncio.run(main())
