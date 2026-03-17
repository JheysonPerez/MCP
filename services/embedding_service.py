import os
import requests
from typing import List

class EmbeddingService:
    def __init__(self):
        """
        Servicio para generar embeddings usando la configuración local de Ollama.
        """
        self.base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        self.model = os.environ.get("OLLAMA_EMBED_MODEL", "embeddinggemma")

    def get_embedding(self, text: str) -> List[float]:
        """
        Llama al endpoint de Ollama para convertir un texto en su vector representativo empotrado.
        """
        url = f"{self.base_url}/api/embeddings"
        payload = {
            "model": self.model,
            "prompt": text
        }
        
        response = requests.post(url, json=payload, timeout=60)
        response.raise_for_status()
        
        data = response.json()
        return data.get("embedding", [])
