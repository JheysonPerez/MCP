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
- **Extracción Automática de Metadatos:**
  - **`MetadataExtractionService`:** Extrae automáticamente título, tipo de documento, año, fecha, autor y organización de documentos.
  - **Clasificación inteligente:** Identifica tipos de documento (resolución, informe, acta, carta, decreto, memorando, contrato, etc.).
  - **Extracción de años:** Detecta años del documento desde múltiples formatos de fecha.
  - **Procesamiento por lotes:** Capacidad de clasificar múltiples documentos simultáneamente.

### Integración Académica UNAS
- **`AcademicoService`:** Consulta en tiempo real al sistema académico de la UNAS.
- **Información disponible:** Notas, horarios, cursos, pagos, matrícula.
- **Sesiones autenticadas:** Manejo de cookies de sesión para acceso seguro.
- **Parseo inteligente:** Conversión de tablas HTML a Markdown legible.

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

## 5. Arquitectura MCP (Model Context Protocol)

El sistema implementa un **servidor MCP completo** que expone todas las funcionalidades RAG como herramientas estandarizadas, permitiendo que cualquier cliente MCP (Claude Desktop, IDEs, etc.) interactúe con el repositorio documental.

### ¿Qué es MCP?

**Model Context Protocol (MCP)** es un protocolo estándar que permite a los LLMs acceder a herramientas y datos externos de manera segura y estructurada. Nuestro servidor MCP convierte todo el sistema RAG en un conjunto de tools accesibles.

### Servidor MCP (`mcp_server/`)

```
mcp_server/
├── server.py          # Definición de tools MCP
├── dependencies.py    # Inyección de dependencias
└── __init__.py
```

**Inicio del servidor MCP:**
```bash
# Modo stdio (para Claude Desktop)
python -m mcp_server.server

# O usando el módulo
python mcp_server/server.py
```

### MCP Tools Disponibles

| Tool | Descripción | Parámetros Principales |
|------|-------------|------------------------|
| **`listar_documentos`** | Lista documentos con filtros avanzados | `estado`, `limite`, `tipo_fuente` |
| **`consultar_documentos`** | Consulta RAG al repositorio | `consulta`, `documento_id`, `incluir_fuentes`, `top_k` |
| **`resumir_documento`** | Genera resumen de documento específico | `document_id_name` |
| **`estadisticas_repositorio`** | Estadísticas completas del sistema | `incluir_detalle_documentos`, `incluir_estadisticas_consultas` |
| **`eliminar_documento`** | Elimina documento (soft/hard delete) | `doc_id`, `modo` |
| **`reindexar_documento`** | Fuerza reindexación semántica | `doc_id` |
| **`agregar_fuente_web`** | Indexa URL como documento | `url`, `verificar_duplicados`, `indexar_inmediatamente` |
| **`generar_documento`** | Genera documento con IA | `prompt`, `tipo`, `modo`, `documento_contexto` |

### Ejemplos de Uso MCP

**Consultar documentos:**
```python
from mcp_server.server import consultar_documentos

resultado_json = consultar_documentos(
    consulta="¿Qué trámites ofrece la UNAS?",
    documento_id="31",
    incluir_fuentes=True,
    top_k=10
)
# Retorna JSON con respuesta, fuentes y metadatos
```

**Listar documentos filtrados:**
```python
from mcp_server.server import listar_documentos

docs_json = listar_documentos(
    estado="indexado",
    limite=20,
    tipo_fuente="web"
)
# Retorna JSON con lista de documentos web indexados
```

**Agregar fuente web:**
```python
from mcp_server.server import agregar_fuente_web

resultado = agregar_fuente_web(
    url="https://unas.edu.pe/transparencia",
    verificar_duplicados=True,
    indexar_inmediatamente=True
)
```

### Integración Web + MCP

La interfaz web Flask (`app/routes.py`) ahora consume las **MCP Tools** directamente:

- `/consultar` → usa `consultar_documentos()`
- `/documentos` → usa `listar_documentos()`
- `/web/add` → usa `agregar_fuente_web()`
- `/generar/crear` → usa `generar_documento()`

Esto unifica la lógica: tanto la web como clientes MCP externos usan las mismas herramientas.

## 6. Arquitectura de Servicios

El sistema está organizado en servicios modulares que implementan **Single Responsibility** y están completamente cubiertos por tests unitarios:

| Servicio | Descripción | Tests |
|----------|-------------|-------|
| **`RagService`** | Orquestador principal del pipeline RAG. Clasificación de intenciones, generación de respuestas. | ✅ 14 tests |
| **`RetrievalService`** | Búsqueda y recuperación de chunks con filtros y búsqueda vectorial. | ✅ 4 tests |
| **`HybridSearchService`** | Fusión de resultados vectoriales y BM25 usando RRF. | ✅ 9 tests |
| **`RerankService`** | Reordenamiento inteligente con LLM y heurísticas de relevancia. | ✅ 9 tests |
| **`ChunkService`** | Fragmentación inteligente con detección de secciones. | ✅ 5 tests |
| **`EmbeddingService`** | Generación de embeddings vía Ollama API. | ✅ 5 tests |
| **`DocumentService`** | Gestión de archivos, procesamiento y OCR. | 🔄 En progreso |
| **`WebScraperService`** | Extracción de contenido web (HTML → Markdown). | ✅ 8 tests |
| **`GenerationService`** | Generación de documentos con IA (informes, actas, memorandos). | ✅ 12 tests |
| **`MetadataExtractionService`** | Extracción automática de metadatos con LLM. | ✅ 14 tests |
| **`PersistenceService`** | Abstracción de acceso a PostgreSQL. | ✅ 16 tests |
| **`UserService`** | Gestión de usuarios, autenticación y roles. | ✅ 17 tests |
| **`AcademicoService`** | Integración con sistema académico UNAS (notas, horarios, matrícula). | ✅ 14 tests |

**Cobertura actual:** 161 tests unitarios pasando, ~39% coverage de servicios.

## 7. Funcionamiento Interno (IA & RAG)
1.  **Ingesta:** El usuario sube un archivo; el sistema detecta su tipo y lo guarda en `uploads/`.
2.  **Extracción:** `DocumentService` limpia el texto. Si el PDF no tiene texto, activa automáticamente el pipeline de OCR.
3.  **Fragmentación (Chunking):** El texto se divide en segmentos lógicos con contexto de sección para análisis preciso.
4.  **Embeddings:** Cada segmento se convierte en un vector usando el modelo **`embeddinggemma`**.
5.  **Indexación Persistente:** Los vectores y fragmentos se guardan en la base de datos PostgreSQL.
6.  **Consulta Híbrida:** 
    - Recuperación inicial de 40 chunks via búsqueda híbrida (vectorial + BM25).
    - Re-ranking con LLM para seleccionar los 10 mejores.
    - Generación de respuesta contextualizada.

## 8. Instalación y Ejecución

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

## 9. Schema y Migraciones de Base de Datos

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

## 10. Tests Unitarios

El proyecto cuenta con una suite completa de tests unitarios para todos los servicios, garantizando la calidad y estabilidad del código.

### Ejecutar Tests

```bash
# Ejecutar todos los tests de servicios
pytest tests/unit/services/ -v

# Ejecutar con cobertura
pytest tests/unit/services/ -v --cov=services --cov-report=html

# Ejecutar un servicio específico
pytest tests/unit/services/test_rag_service.py -v
pytest tests/unit/services/test_user_service.py -v
pytest tests/unit/services/test_persistence_service.py -v

# Ejecutar con resumen corto de errores
pytest tests/unit/services/ -v --tb=short
```

### Estructura de Tests

```
tests/
├── unit/
│   └── services/
│       ├── test_academico_service.py          # 14 tests - Integración UNAS
│       ├── test_chunk_service.py                # 5 tests - Fragmentación
│       ├── test_embedding_service.py            # 5 tests - Embeddings
│       ├── test_generation_service.py           # 12 tests - Generación IA
│       ├── test_hybrid_search_service.py         # 9 tests - Búsqueda híbrida
│       ├── test_metadata_extraction_service.py  # 14 tests - Extracción metadatos
│       ├── test_persistence_service.py          # 16 tests - Base de datos
│       ├── test_rag_service.py                  # 14 tests - Pipeline RAG
│       ├── test_rag_service_intent.py           # 9 tests - Clasificación intenciones
│       ├── test_rerank_service.py               # 9 tests - Re-ranking
│       ├── test_retrieval_service.py            # 4 tests - Recuperación
│       ├── test_user_service.py                 # 17 tests - Gestión usuarios
│       └── test_web_scraper_service.py          # 8 tests - Web scraping
├── conftest.py                                  # Fixtures y configuración pytest
└── pytest.ini                                   # Configuración pytest
```

### Coverage Actual

- **Total:** 161 tests unitarios pasando
- **Coverage servicios:** ~39%
- **Servicios testeados:** 12/13 (DocumentService en progreso)

### Herramientas de Testing

- **pytest:** Framework principal de testing
- **pytest-cov:** Medición de cobertura de código
- **pytest-mock:** Mocking integrado con pytest
- **unittest.mock:** MagicMock, patch, mock_open

---

## 11. Limitaciones y Roadmap

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
- ✅ **Web Scraping:** Extracción e indexación de contenido web.
- ✅ **MCP Server:** Protocolo Model Context para integración con clientes MCP (Claude Desktop, IDEs).
- ✅ **MCP Tools:** 8 herramientas expuestas vía MCP (`consultar_documentos`, `listar_documentos`, etc.).
- ✅ **Markdown Rendering:** Respuestas RAG renderizadas como HTML con headers, listas y formato limpio.
- ✅ **Sanitización XSS:** Protección contra XSS en respuestas markdown usando `bleach`.
- ✅ **Tests Unitarios:** 161 tests unitarios cubriendo 12 servicios.
- ✅ **Extracción Automática de Metadatos:** Clasificación de documentos con LLM.
- ✅ **Integración UNAS:** Consulta de notas, horarios y matrícula en tiempo real.

### Roadmap (Pendiente 🚀)
- ⚠️ OCR para imágenes JPG/PNG sueltas.
- ⚠️ Deploy producción Ubuntu con systemd/nginx.
- ⚠️ Benchmark de evaluación RAG (RAGAS/TruLens).
- ⚠️ Panel de logs avanzado en la UI.
- ⚠️ Colecciones y carpetas documentales.
- ⚠️ Tests para DocumentService (OCR y procesamiento de archivos).

---
*Desarrollado para el fortalecimiento de la gestión del conocimiento institucional mediante IA Soberana.*
