# 🧪 Testing para MCP-DOCS

## Estructura de Tests

```
tests/
├── conftest.py                    # Fixtures compartidos
├── pytest.ini                     # Configuración de pytest
├── README_TESTING.md              # Esta guía
├── unit/                          # Tests unitarios (rápidos)
│   └── services/
│       ├── test_chunk_service.py
│       ├── test_retrieval_service.py
│       └── test_rag_service_intent.py
└── integration/                   # Tests de integración (próximamente)
```

## Comandos Rápidos

```bash
# Ejecutar todos los tests
pytest

# Solo tests unitarios
pytest -m unit

# Con coverage report
pytest --cov=services --cov-report=term-missing

# Un archivo específico
pytest tests/unit/services/test_chunk_service.py -v

# Un test específico
pytest tests/unit/services/test_rag_service_intent.py::TestIntentClassification::test_detecta_saludo_simple -v

# Verbose con prints
pytest -v -s

# Tests lentos (con LLM, requieren Ollama)
pytest -m slow --timeout=300
```

## Marcadores (Markers)

| Marcador | Uso | Ejecución |
|----------|-----|-----------|
| `@pytest.mark.unit` | Tests rápidos, sin dependencias externas | `pytest -m unit` |
| `@pytest.mark.integration` | Requieren DB, Ollama, servicios | `pytest -m integration` |
| `@pytest.mark.slow` | LLM calls, embeddings, scraping | `pytest -m slow` |

## Ejemplo de Uso

```python
# Agregar a tu test
import pytest

@pytest.mark.unit
def test_mi_funcion():
    assert True

@pytest.mark.slow
@pytest.mark.integration
def test_con_llm():
    # Este test necesita Ollama corriendo
    pass
```

## Coverage

Después de correr tests con `--cov`, ver el reporte HTML:

```bash
open tests/coverage_html/index.html
```

## Tests Críticos para este Proyecto

### 1. Router de Intenciones (CRÍTICO)
Archivo: `test_rag_service_intent.py`
- ✅ Detecta saludos → 'greeting'
- ✅ Detecta consultas de metadatos → 'metadata'
- ✅ Detecta consultas de contenido → 'content'
- ✅ NO clasifica "de qué habla el documento" como metadata (bug fix)

### 2. Detección de Filtros
Archivo: `test_rag_service_intent.py`
- ✅ Extrae `doc_type` de consultas
- ✅ Extrae `doc_year` de consultas
- ✅ Funciona con ambos juntos

### 3. Chunking
Archivo: `test_chunk_service.py`
- ✅ Detecta headers correctamente
- ✅ Respeta tamaño máximo
- ✅ No genera chunks vacíos

### 4. Retrieval
Archivo: `test_retrieval_service.py`
- ✅ Aplica filtros SQL correctamente
- ✅ Retorna `document_id` en resultados
