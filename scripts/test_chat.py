import os
import requests
from dotenv import load_dotenv

# Cargar variables de entorno desde el archivo .env si existe
load_dotenv()

# Obtener configuracion
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
MODEL = os.environ.get("OLLAMA_CHAT_MODEL", "qwen2.5:3b")

def test_chat():
    print(f"Probando conexion con Ollama...")
    print(f"Endpoint: {OLLAMA_BASE_URL}")
    print(f"Modelo: {MODEL}\n")
    
    url = f"{OLLAMA_BASE_URL}/api/generate"
    
    payload = {
        "model": MODEL,
        "prompt": "Hola, ¿quién eres y de qué eres capaz? Responde en un maximo de 2 lineas.",
        "stream": False
    }
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        print("--- RESPUESTA DE LA IA ---")
        print(data.get("response", "No se encontró respuesta en la carga útil."))
        print("--------------------------\n")
        print("[OK] ¡Prueba de chat exitosa!")
        
    except requests.exceptions.ConnectionError:
        print("[ERROR] Error de conexion: No se pudo conectar a Ollama.")
        print("Asegurate de que Ollama este corriendo localmente.")
    except Exception as e:
        print(f"[ERROR] Ocurrio un error inesperado al conectar con Ollama: {e}")

if __name__ == "__main__":
    test_chat()
