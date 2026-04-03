# EPIIS – MCP-DOCS: Sistema de Inteligencia Documental (RAG)

**EPIIS MCP-DOCS** es una plataforma de gestión y consulta documental potenciada por Inteligencia Artificial local. Permite transformar archivos estáticos (PDF, DOCX, TXT) en una base de conocimientos dinámica mediante un pipeline de **Generación Aumentada por Recuperación (RAG)**, garantizando la privacidad institucional al ejecutarse 100% en infraestructura propia.

## 1. ¿Qué hace el sistema?
El sistema resuelve la dificultad de encontrar información específica en grandes volúmenes de documentos técnicos e institucionales. A diferencia de una búsqueda tradicional por palabras clave, MCP-DOCS:
- **Entiende el contexto:** Responde preguntas basadas en el significado real del contenido.
- **Cita fuentes:** Indica exactamente de qué documento extrajo la respuesta y el nivel de confianza.
- **Audita el repositorio:** Provee estadísticas en tiempo real y reconciliación automática de archivos.
- **Multiusuario con roles:** Sistema de autenticación con roles de administrador y usuario.
- **Privacidad Local:** Utiliza **Ollama** para el procesamiento de lenguaje y generación de vectores, asegurando que los datos nunca salgan de la red local.

## 2. Diferencias y Flujo de Datos
Para entender el sistema, es vital distinguir estos conceptos:
- **`data/uploads/`**: Carpeta que contiene los archivos originales tal cual fueron subidos por el usuario.
- **`data/processed/`**: Carpeta que contiene la extracción de texto puro (limpio) de los originales, lista para ser analizada.
- **Documento Procesado:** Aquel cuyo texto ha sido extraído con éxito (Estado: `completed`).
- **Documento Indexado:** Aquel cuyos fragmentos (chunks) ya han sido convertidos en vectores numéricos y persistidos en la base de datos.
- **Documento Consultable:** Un documento que está `completed` e `indexado`. Solo estos pueden responder preguntas de conocimiento.

## 3. Arquitectura de Datos y Stack
El sistema utiliza una arquitectura de persistencia robusta y moderna:
- **Metadatos e Historial:** PostgreSQL 17 maneja la información de usuarios, documentos y auditoría de consultas.
- **Vectores Semánticos:** Se utiliza la extensión **pgvector (0.8.2)** para almacenar y buscar embeddings de alta dimensión (768 para `embeddinggemma`).
- **Tesseract OCR 5.5+**: Soporte para PDFs escaneados con idiomas español e inglés.
- **Poppler 26+**: Conversión de PDF a imagen para el pipeline de OCR.
- **Librerías Clave:** `pytesseract`, `pdf2image`, `Pillow`, `fpdf2` (exportación PDF), `python-docx` (exportación DOCX).

## 4. Funcionalidades Implementadas

### Consulta Documental (RAG Avanzado)
- **Búsqueda Híbrida:** Combina búsqueda vectorial semántica con BM25 (palabras clave) usando Reciprocal Rank Fusion (RRF) para resultados superiores.
- **Re-ranking Inteligente:** Reordena los chunks recuperados usando un LLM para maximizar relevancia.
- **Intent Router Híbrido:** Clasificación (reglas + Ollama) para separar consultas de metadata vs contenido.
- **Contexto Automático:** Detección de documentos mencionados en la pregunta con aplicación de filtros y boosts.
- **Memoria Conversacional:** Historial multi-turno (últimos 5 turnos) por sesión para mantener el hilo de la charla.
- **Transparencia:** Respuestas con fuentes citadas y score de confianza.

### Procesamiento Documental
- **Multi-formato:** Extracción desde PDF, DOCX, TXT.
- **OCR en Dos Fases:** OCR automático con Tesseract para PDFs sin texto embebido.
- **Chunking Inteligente:** Fragmentación con detección de secciones, contexto semántico y overlap configurable.
- **Indexación Persistente:** Embeddings con `embeddinggemma` y almacenamiento vectorial en PostgreSQL.

### Gestión de Usuarios y Roles
- **Autenticación:** Sistema de login con sesiones.
- **Roles:** Administrador (gestión completa) y Usuario (solo consulta).
- **Permisos granulares:**
  - **Admin:** Subir, eliminar, reindexar documentos; gestionar usuarios.
  - **Usuario:** Consultar documentos, ver historial personal.
- **Historial por usuario:** Auditoría de consultas individualizada.

### Generación Documental
- **Modos de Creación:** Generación por prompt libre, basada en repositorio (RAG) o basada en documento específico.
- **Exportación:** Descarga de documentos generados en Markdown (.md), DOCX y PDF.
- **Historial:** Registro y gestión de todos los documentos creados por IA.

## 5. Arquitectura de Servicios

El sistema está organizado en servicios modulares:
- **`RagService`:** Orquestador principal del pipeline RAG.
- **`RetrievalService`:** Búsqueda y recuperación de chunks con filtros.
- **`HybridSearchService`:** Fusión de resultados vectoriales y BM25.
- **`RerankService`:** Reordenamiento inteligente de resultados.
- **`ChunkService`:** Fragmentación inteligente con contexto.
- **`EmbeddingService`:** Generación de embeddings.
- **`DocumentService`:** Gestión de archivos y procesamiento.

## 6. Funcionamiento Interno (IA & RAG)
1.  **Ingesta:** El usuario sube un archivo; el sistema detecta su tipo y lo guarda en `uploads/`.
2.  **Extracción:** `DocumentService` limpia el texto. Si el PDF no tiene texto, activa automáticamente el pipeline de OCR.
3.  **Fragmentación (Chunking):** El texto se divide en segmentos lógicos con contexto de sección para análisis preciso.
4.  **Embeddings:** Cada segmento se convierte en un vector usando el modelo **`embeddinggemma`**.
5.  **Indexación Persistente:** Los vectores y fragmentos se guardan en la base de datos PostgreSQL.
6.  **Consulta Híbrida:** 
    - Recuperación inicial de 40 chunks via búsqueda híbrida (vectorial + BM25).
    - Re-ranking con LLM para seleccionar los 10 mejores.
    - Generación de respuesta contextualizada.

## 7. Instalación y Ejecución

### Requisitos Previos
- **Python 3.10+**
- **PostgreSQL 17+** con **pgvector 0.8.2**
- **Ollama** con los modelos `qwen2.5:3b` y `embeddinggemma`.

### Instalación Ubuntu (Producción)
```bash
# Dependencias del sistema
sudo apt update
sudo apt install -y tesseract-ocr tesseract-ocr-spa poppler-utils
sudo apt install -y python3-pip python3-venv

# pgvector (compilar desde fuente para PostgreSQL)
sudo apt install -y postgresql-server-dev-all cmake
git clone https://github.com/pgvector/pgvector.git
cd pgvector && make && sudo make install
psql -U postgres -d mcp_epiis -c "CREATE EXTENSION vector;"

# Dependencias Python
pip install -r requirements.txt
```

### Guía de Inicio Rápido
1.  **Entorno Virtual:**
    ```bash
    python -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```
2.  **Configuración (`.env`):**
    ```env
    DATABASE_URL=postgresql://usuario:password@localhost:5432/mcp_epiis
    OLLAMA_BASE_URL=http://localhost:11434
    OLLAMA_CHAT_MODEL=qwen2.5:3b
    OLLAMA_EMBED_MODEL=embeddinggemma
    ```
3.  **Base de Datos:**
    ```bash
    psql -d mcp_epiis -f db/schema.sql
    python scripts/create_admin.py
    ```
4.  **Arranque:**
    ```bash
    python run_web.py
    ```

## 7. Limitaciones y Roadmap

### Roadmap (Completado ✅)
- ✅ **pgvector:** Indexación persistente y rápida en PostgreSQL.
- ✅ **OCR Tesseract:** Procesamiento de PDFs escaneados.
- ✅ **Memoria Conversacional:** Seguimiento del hilo de la conversación.
- ✅ **Generación Documental:** Creación de nuevos documentos desde el conocimiento base.
- ✅ **Exportación PDF/DOCX:** Descarga de resultados en formatos editables.
- ✅ **Multiusuario con roles:** Sistema de autenticación y permisos.
- ✅ **Búsqueda Híbrida:** Combinación vectorial + BM25.
- ✅ **Re-ranking:** Reordenamiento inteligente con LLM.
- ✅ **Chunking Inteligente:** Detección de secciones y contexto.

### Roadmap (Pendiente 🚀)
- ⚠️ OCR para imágenes JPG/PNG sueltas.
- ⚠️ Deploy producción Ubuntu con systemd/nginx.
- ⚠️ Benchmark de evaluación RAG (RAGAS/TruLens).
- ⚠️ Panel de logs avanzado en la UI.
- ⚠️ Colecciones y carpetas documentales.

---
*Desarrollado para el fortalecimiento de la gestión del conocimiento institucional mediante IA Soberana.*
