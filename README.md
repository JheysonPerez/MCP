# EPIIS – MCP-DOCS: Sistema de Inteligencia Documental (RAG)

**EPIIS MCP-DOCS** es una plataforma de gestión y consulta documental potenciada por Inteligencia Artificial local. Permite transformar archivos estáticos (PDF, DOCX, TXT) en una base de conocimientos dinámica mediante un pipeline de **Generación Aumentada por Recuperación (RAG)**, garantizando la privacidad institucional al ejecutarse 100% en infraestructura propia.

## 1. ¿Qué hace el sistema?
El sistema resuelve la dificultad de encontrar información específica en grandes volúmenes de documentos técnicos e institucionales. A diferencia de una búsqueda tradicional por palabras clave, MCP-DOCS:
- **Entiende el contexto:** Responde preguntas basadas en el significado real del contenido.
- **Cita fuentes:** Indica exactamente de qué documento extrajo la respuesta y el nivel de confianza.
- **Audita el repositorio:** Provee estadísticas en tiempo real y reconciliación automática de archivos.
- **Privacidad Local:** Utiliza **Ollama** para el procesamiento de lenguaje y generación de vectores, asegurando que los datos nunca salgan de la red local.

## 2. Diferencias y Flujo de Datos
Para entender el sistema, es vital distinguir estos conceptos:
- **`data/uploads/`**: Carpeta que contiene los archivos originales tal cual fueron subidos por el usuario.
- **`data/processed/`**: Carpeta que contiene la extracción de texto puro (limpio) de los originales, lista para ser analizada.
- **Documento Procesado:** Aquel cuyo texto ha sido extraído con éxito (Estado: `completed`).
- **Documento Indexado:** Aquel cuyos fragmentos (chunks) ya han sido convertidos en vectores numéricos y cargados en la memoria semántica (Vector Store).
- **Documento Consultable:** Un documento que está `completed` e `indexado`. Solo estos pueden responder preguntas de conocimiento.

## 3. Funcionamiento Interno (IA & RAG)
1.  **Ingesta:** El usuario sube un archivo; el sistema detecta su tipo y lo guarda en `uploads/`.
2.  **Extracción:** `DocumentService` limpia el texto. Si el PDF no tiene texto (escaneado/imagen), el proceso se marca como `failed`.
3.  **Fragmentación (Chunking):** El texto se divide en segmentos lógicos para un análisis preciso.
4.  **Embeddings:** Cada segmento se convierte en un vector usando el modelo **`embeddinggemma`**.
5.  **Consulta (Intent Router):**
    - Si preguntas por metadatos (conteo/lista), el sistema responde desde PostgreSQL.
    - Si preguntas por contenido, el sistema recupera los fragmentos más relevantes y genera una respuesta con el LLM.
6.  **Contexto Automático:** Si mencionas el nombre de un archivo en la pregunta, el sistema prioriza o filtra la búsqueda solo en ese documento.

## 4. Instalación y Ejecución

### Requisitos Previos
- **Python 3.10+**
- **PostgreSQL 14+** (Base de datos recomendada: `mcp_epiis`).
- **Ollama** instalado y con los siguientes modelos descargados:
  ```bash
  ollama pull qwen2.5:3b      # Modelo de Chat
  ollama pull embeddinggemma  # Modelo de Embeddings
  ```

### Guía de Inicio Rápido
1.  **Entorno Virtual e Instalar Dependencias:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # Windows: venv\Scripts\activate
    pip install -r requirements.txt
    ```
2.  **Configuración (`.env`):**
    Crea un archivo `.env` basado en `.env.example`:
    ```env
    DATABASE_URL=postgresql://usuario:password@localhost:5432/mcp_epiis
    OLLAMA_BASE_URL=http://localhost:11434
    OLLAMA_CHAT_MODEL=qwen2.5:3b
    OLLAMA_EMBED_MODEL=embeddinggemma
    ```
3.  **Base de Datos y Acceso Inicial:**
    Crea la base de datos `mcp_epiis`, ejecuta el esquema y crea el primer usuario administrador:
    ```bash
    psql -d mcp_epiis -f db/schema.sql
    python scripts/create_admin.py
    ```
4.  **Arranque del Sistema:**
    ```bash
    python run_web.py
    ```

> **Nota Crítica sobre el Arranque:** Al iniciar, la aplicación ejecuta automáticamente una **Auditoría y Sincronización Global**. Este proceso reconstruye el índice semántico desde los archivos válidos en `data/processed/`. Si un archivo falta o está vacío, el sistema lo marcará como `failed` en la base de datos para mantener la integridad.

## 5. Validación Funcional
Prueba estos comandos en la sección de "Consultar" para validar el sistema:
- **Metadata:** "¿Cuántos documentos tienes indexados?" o "¿Qué archivos hay en el repositorio?".
- **RAG General:** "Haz un resumen de los puntos clave en los documentos cargados".
- **RAG Específico:** "¿Qué dice el archivo `manual_epiis_rag_db.txt` sobre la configuración de la base de datos?".
- **Prueba Negativa:** "¿Qué opinas del clima hoy?". El sistema debe responder que no tiene información sobre ese tema en los documentos actuales (no debe inventar).

## 6. Diccionario de Estados y Acciones
- **Estados:**
  - `Pending`: Esperando procesamiento inicial.
  - `Completed`: Texto extraído correctamente.
  - `Failed`: Error físico o de extracción (ej: PDF sin texto).
  - `Indexado`: Cargado en la memoria semántica de la IA.
  - **`Chunks`**: Cantidad de fragmentos en que se dividió el documento para su indexación semántica.
- **Acciones:**
  - **Reindexar:** Borra los vectores actuales de un documento y los vuelve a generar.
  - **Sincronizar Repositorio:** Auditoría global que reconcilia el estado de la base de datos con los archivos físicos.

## 7. Comandos Útiles
Reúne aquí los comandos más usados durante el desarrollo:
- **Entorno:** `source venv/bin/activate`
- **Correr App:** `python run_web.py`
- **Esquema DB:** `psql -d mcp_epiis -f db/schema.sql`
- **Ollama Status:** `ollama list`
- **Descargar Modelos:** `ollama pull qwen2.5:3b` y `ollama pull embeddinggemma`.

## 8. Guía para Desarrolladores
- **Backend & Rutas:** `app/routes.py`.
- **Interfaz (UI):**
    - `app/templates/base.html`: Layout global.
    - `app/templates/dashboard.html`: Panel principal de estadísticas.
    - `app/templates/consultar.html`: Vista del asistente documental interactivo.
    - `app/templates/documentos.html`: Gestión y administración del repositorio.
- **Lógica RAG:** `services/rag_service.py` y `services/retrieval_service.py`.
- **Procesamiento de Archivos:** `services/document_service.py`.
- **Persistencia de Datos:** `services/persistence_service.py`.

## 9. Limitaciones y Roadmap
- ⚠️ **Actual:** Los PDFs basados en imágenes (escaneos) no se procesan (requiere OCR externo).
- ⚠️ **Actual:** No existe memoria de chat (cada pregunta es independiente).
- 🚀 **Próximo:** Soporte para multilingüismo avanzado y panel de logs en tiempo real.

---
*Desarrollado para el fortalecimiento de la gestión del conocimiento institucional mediante IA Soberana.*
