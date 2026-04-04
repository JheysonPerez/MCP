# EPIIS – MCP-DOCS: Sistema de Inteligencia Documental (RAG)

**EPIIS MCP-DOCS** es una plataforma de gestión y consulta documental potenciada por Inteligencia Artificial local. Permite transformar archivos estáticos (PDF, DOCX, TXT) en una base de conocimientos dinámica mediante un pipeline de **Generación Aumentada por Recuperación (RAG)**, garantizando la privacidad institucional al ejecutarse 100% en infraestructura propia.

## 1. ¿Qué hace el sistema?
El sistema resuelve la dificultad de encontrar información específica en grandes volúmenes de documentos técnicos e institucionales. A diferencia de una búsqueda tradicional por palabras clave, MCP-DOCS:
- **Entiende el contexto:** Responde preguntas basadas en el significado real del contenido.
- **Cita fuentes:** Indica exactamente de qué documento extrajo la respuesta y el nivel de confianza.
- **Audita el repositorio:** Provee estadísticas en tiempo real y reconciliación automática de archivos.
- **Multiusuario con roles:** Sistema de autenticación con roles de administrador y usuario.
- **Privacidad Local:** Utiliza **Ollama** para el procesamiento de lenguaje y generación de vectores, asegurando que los datos nunca salgan de la red local.
- **Web Scraping:** Extrae y indexa contenido de páginas web para consultarlos junto con documentos tradicionales.

## 2. Diferencias y Flujo de Datos
Para entender el sistema, es vital distinguir estos conceptos:
- **`data/uploads/`**: Carpeta que contiene los archivos originales tal cual fueron subidos por el usuario.
- **`data/processed/`**: Carpeta que contiene la extracción de texto puro (limpio) de los originales, lista para ser analizada.
- **Documento Procesado:** Aquel cuyo texto ha sido extraído con éxito (Estado: `completed`).
- **Documento Indexado:** Aquel cuyos fragmentos (chunks) ya han sido convertidos en vectores numéricos y persistidos en la base de datos.
- **Documento Consultable:** Un documento que está `completed` e `indexado`. Solo estos pueden responder preguntas de conocimiento.
- **Fuente Web:** URL scrapeada e indexada como documento consultable, con soporte para actualización automática.

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

### Web Scraping
- **Extracción de URLs:** Scrapea páginas web con `requests` + `BeautifulSoup4` y convierte HTML a texto markdown.
- **Indexación automática:** Las URLs extraídas se procesan, indexan y quedan disponibles para consultas inmediatamente.
- **Deduplicación:** Verifica que no existan URLs duplicadas antes de indexar.
- **Actualización manual:** Botón para refrescar contenido de una URL ya indexada.
- **Gestión visual:** Panel `/web` con stats, listado de fuentes y controles de eliminación.

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

### Guía de Inicio Rápido (macOS/Ubuntu)

#### 1. Clonar el repositorio
```bash
git clone https://github.com/JheysonPerez/MCP.git
cd MCP
```

#### 2. Entorno Virtual e Instalación de dependencias
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### 3. Base de Datos PostgreSQL + pgvector (Automático)

**Opción A: Usando el script de migraciones automático (Recomendado):**
```bash
python db/migrate.py
```

Este script verifica automáticamente qué migraciones faltan y las aplica:
- Crea la extensión `pgvector` si no existe
- Agrega columnas para web scraping (`source_url`, `source_type`, etc.)
- Verifica que todas las tablas core estén listas

**Opciones del script:**
```bash
python db/migrate.py --status    # Ver estado de migraciones
python db/migrate.py --check     # Solo verificar, no aplicar
python db/migrate.py --verify    # Verificar que todo esté listo
```

**Opción B: Manual paso a paso:**

**macOS (con Homebrew):**
```bash
# Instalar PostgreSQL y pgvector
brew install postgresql@17
brew install pgvector

# Iniciar PostgreSQL
brew services start postgresql@17

# Crear base de datos
psql postgres -c "CREATE DATABASE mcp_epiis;"
psql postgres -c "CREATE USER mcp_user WITH PASSWORD 'tu_password';"
psql postgres -c "GRANT ALL PRIVILEGES ON DATABASE mcp_epiis TO mcp_user;"

# Instalar extensión pgvector
psql mcp_epiis -c "CREATE EXTENSION IF NOT EXISTS vector;"

# Ejecutar schema inicial
psql mcp_epiis -f db/schema.sql
```

**Ubuntu/Debian:**
```bash
# Instalar PostgreSQL 17
sudo apt update
sudo apt install -y postgresql-17 postgresql-server-dev-17

# Instalar pgvector desde fuente
sudo apt install -y cmake
sudo apt install -y postgresql-server-dev-17
cd /tmp
git clone https://github.com/pgvector/pgvector.git
cd pgvector
git checkout v0.8.0
make
sudo make install

# Crear base de datos y usuario
sudo -u postgres psql -c "CREATE DATABASE mcp_epiis;"
sudo -u postgres psql -c "CREATE USER mcp_user WITH PASSWORD 'tu_password';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE mcp_epiis TO mcp_user;"

# Instalar extensión y schema
sudo -u postgres psql mcp_epiis -c "CREATE EXTENSION IF NOT EXISTS vector;"
psql mcp_epiis -f db/schema.sql
```

#### 4. Ollama (Modelos de IA)
```bash
# Instalar Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Descargar modelos requeridos
ollama pull qwen2.5:3b
ollama pull embeddinggemma

# Verificar instalación
ollama list
```

#### 5. Configuración (`.env`)
Crear archivo `.env` en la raíz del proyecto:
```env
DATABASE_URL=postgresql://mcp_user:tu_password@localhost:5432/mcp_epiis
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_CHAT_MODEL=qwen2.5:3b
OLLAMA_EMBED_MODEL=embeddinggemma
SECRET_KEY=tu_secreto_seguro_aqui
```

#### 6. Crear usuario administrador
```bash
python scripts/create_admin.py
```

#### 7. Iniciar la aplicación
```bash
python run_web.py
```

Acceder a: http://127.0.0.1:5000

---

## 8. Schema y Migraciones de Base de Datos

### Schema Completo (`db/schema.sql`)

El archivo `db/schema.sql` contiene **todo el schema de la base de datos** en un solo archivo idempotente:

- ✅ Extensión `pgvector` para vectores
- ✅ Tablas: `users`, `documents`, `chunks`, `queries`, `responses`, `generated_documents_v2`
- ✅ Columnas para web scraping (`source_url`, `source_type`, etc.)
- ✅ Índices optimizados para búsquedas

**Características:**
- **Idempotente:** Puedes ejecutarlo 100 veces, solo creará lo que falte
- **Completo:** Contiene todo desde la instalación inicial hasta las últimas features
- **Actualizado:** Siempre refleja el estado actual del proyecto

### Script de Migraciones Automático (`db/migrate.py`)

Este script ejecuta el schema completo y verifica que todo esté listo:

```bash
# Ejecutar migraciones (aplica schema.sql completo)
python db/migrate.py

# Verificar estado sin aplicar cambios
python db/migrate.py --check

# Ver estado detallado de todas las tablas
python db/migrate.py --status

# Verificar que todo funcione correctamente
python db/migrate.py --verify
```

**¿Qué hace el script?**
1. Ejecuta `db/schema.sql` completo (idempotente)
2. Verifica que existan todas las tablas necesarias
3. Comprueba que la extensión `pgvector` esté instalada
4. Valida columnas de web scraping
5. Muestra ✅ o ❌ por cada componente

### Uso Manual del Schema (alternativa)

Si prefieres no usar el script de migraciones:

```bash
# Ejecutar schema manualmente
psql $DATABASE_URL -f db/schema.sql

# O especificando la base de datos
psql mcp_epiis -f db/schema.sql
```

### Actualizaciones Futuras

Cuando el proyecto evolucione y se agreguen nuevas tablas/columnas:

1. **Actualizar `db/schema.sql`:** Agregar las nuevas definiciones con `IF NOT EXISTS`
2. **Ejecutar migraciones:** `python db/migrate.py`

El script detectará automáticamente qué falta y lo creará.

---

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
- ✅ **Web Scraping:** Extracción e indexación de contenido web.
- ⚠️ OCR para imágenes JPG/PNG sueltas.
- ⚠️ Deploy producción Ubuntu con systemd/nginx.
- ⚠️ Benchmark de evaluación RAG (RAGAS/TruLens).
- ⚠️ Panel de logs avanzado en la UI.
- ⚠️ Colecciones y carpetas documentales.

---
*Desarrollado para el fortalecimiento de la gestión del conocimiento institucional mediante IA Soberana.*
