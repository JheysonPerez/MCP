import os
import requests
from dotenv import load_dotenv

load_dotenv()

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
EMBED_MODEL = os.environ.get("OLLAMA_EMBED_MODEL", "embeddinggemma")

def test_embeddings():
    print(f"Probando conexion con Ollama (Embeddings)...")
    print(f"Endpoint: {OLLAMA_BASE_URL}")
    print(f"Modelo de Embeddings: {EMBED_MODEL}\n")
    
    url = f"{OLLAMA_BASE_URL}/api/embeddings"
    
    payload = {
        "model": EMBED_MODEL,
        "prompt": "Este es un documento de prueba para la plataforma EPIIS."
    }
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        vector = data.get("embedding", [])
        
        print("--- RESULTADO DE EMBEDDINGS ---")
        print(f"Dimensiones del vector devuelto: {len(vector)}")
        print(f"Primeros 5 elementos: {vector[:5]}")
        print("-------------------------------\n")
        print("[OK] ¡Prueba de embeddings exitosa!")
        
    except requests.exceptions.ConnectionError:
        print("[ERROR] Error de conexion: No se pudo conectar a Ollama.")
        print("Asegurate de que Ollama este corriendo localmente.")
    except Exception as e:
        print(f"[ERROR] Ocurrio un error inesperado al conectar con Ollama para embeddings: {e}")

if __name__ == "__main__":
    test_embeddings()
