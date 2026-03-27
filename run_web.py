import sys
from pathlib import Path

# Permitir a python encontrar app/ y modules superiores
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import create_app

app = create_app()

if __name__ == "__main__":
    print("\n--- INICIANDO SERVIDOR WEB (RAG EPIIS - FLASK MVP) ---")
    print("Accede a la interfaz desde tu navegador: http://127.0.0.1:5000\n")
    
    # Arrancamos con debug=True para desarrollo ágil y recarga en vivo de plantillas HTML
    app.run(host="0.0.0.0", port=5008, debug=True)
