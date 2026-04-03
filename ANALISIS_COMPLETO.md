# 📊 ANÁLISIS COMPLETO DEL PROYECTO EPIIS MCP-DOCS

## 🎯 RESUMEN EJECUTIVO
Sistema RAG (Retrieval Augmented Generation) para gestión documental institucional con:
- **Autenticación y roles** (admin/user)
- **Procesamiento de documentos** (PDF, DOCX, TXT) con OCR
- **Consultas inteligentes** usando embeddings + LLM local (Ollama)
- **Generación documental** con IA

---

## 📋 FUNCIONALIDADES IMPLEMENTADAS

### 1. 🔐 SISTEMA DE AUTENTICACIÓN Y ROLES
| Función | Admin | Usuario Normal |
|---------|-------|----------------|
| Login/Logout | ✅ | ✅ |
| Ver dashboard | ✅ | ✅ |
| Subir documentos | ✅ | ❌ |
| Crear usuarios | ✅ | ❌ |
| Gestionar usuarios | ✅ | ❌ |
| Consultar RAG | ✅ | ✅ |
| Generar documentos | ✅ | ✅ |
| Ver historial | ✅ | ✅ |

**Credenciales por defecto:**
- Admin: `admin` / `password123`

### 2. 📁 GESTIÓN DE DOCUMENTOS
- **Upload**: Arrastrar y soltar PDF, DOCX, TXT
- **OCR**: Extrae texto de imágenes (Tesseract)
- **Indexación**: Embeddings automáticos con `mxbai-embed-large`
- **Chunking**: Fragmentos de 500 chars con overlap 50
- **Reindexar**: Regenerar embeddings
- **Eliminar**: Soft delete

### 3. 🔍 SISTEMA RAG (Consultas Inteligentes)
**Flujo:**
1. Usuario pregunta → Embeddings de la query
2. Búsqueda vectorial (similitud coseno, threshold 0.20)
3. Recupera top 10 chunks más relevantes
4. Prompt engineering → LLM (`qwen2.5:7b`)
5. Respuesta con fuentes citadas

**Características:**
- Detección automática de documento mencionado
- Filtro por documento específico
- Historial de conversación (últimos 5 turnos)
- Contexto semántico (entiende sinónimos)

### 4. 📝 GENERACIÓN DOCUMENTAL
**Modos:**
- Prompt libre: IA genera desde cero
- Basado en repositorio: Usa contexto de documentos subidos
- Basado en documento: Usa documento específico

**Formatos:** Markdown, DOCX, PDF

### 5. 👥 ADMINISTRACIÓN DE USUARIOS (Solo Admin)
- Listar usuarios
- Crear usuario (username, email, password, role)
- Editar usuario
- Cambiar contraseña
- Activar/Desactivar
- Eliminar (hard/soft)

---

## 🧪 CASOS DE USO Y PRUEBAS

### FLUJO 1: ADMIN - Setup Inicial
```
1. Login con admin/password123
2. Ir a "Administración de Usuarios"
3. Crear usuario normal: juan.perez / user@epiis.local / password123 / role=user
4. Ir a Documentos
5. Subir documentos de prueba (ver Tipos de Docs abajo)
6. Verificar indexación (status: completado)
```

### FLUJO 2: USUARIO NORMAL - Consulta RAG
```
1. Login con juan.perez / password123
2. Ir a "Consultar"
3. Preguntar sobre documentos
4. No puede subir archivos (botón deshabilitado/oculto)
5. No puede crear usuarios
```

### FLUJO 3: GENERACIÓN DOCUMENTAL
```
1. Ir a "Generar"
2. Seleccionar modo y formato
3. Descargar documento generado
```

---

## 📄 TIPOS DE DOCUMENTOS PARA PROBAR RAG

### Categoría A: Documentos Institucionales (Recomendados)
| Tipo | Contenido | Preguntas de Prueba |
|------|-----------|---------------------|
| **Certificados laborales** | Datos personales, fechas, estados | "¿Qué dice el certificado de [nombre]?" |
| **Resoluciones** | Números, fechas, disposiciones | "¿Qué resuelve la R.A. N° XXX?" |
| **Informes técnicos** | Análisis, conclusiones | "Resume el informe de..." |
| **Actas** | Participantes, acuerdos | "¿Qué se acordó en la reunión de...?" |
| **Contratos** | Cláusulas, partes, montos | "¿Cuál es la cláusula X del contrato?" |

### Categoría B: Documentos de Prueba Simple
| Tipo | Ejemplo | Valor de Prueba |
|------|---------|-----------------|
| CV/Resumen profesional | PDF con datos estructurados | Fácil de validar |
| Factura/Recibo | Datos numéricos precisos | Verificar números |
| Certificado académico | Fechas, cursos, notas | Validar datos exactos |
| Carta/nota simple | Texto corto | Verificar comprensión |

### ⚠️ Documentos que FALLAN (No usar para pruebas iniciales)
- Scans de baja calidad (OCR falla)
- PDFs solo imagen sin texto
- Documentos con tablas complejas
- Archivos > 50MB

---

## ✅ CHECKLIST DE VALIDACIÓN RAG

### Paso 1: Subida e Indexación
- [ ] Archivo aparece en lista "Documentos"
- [ ] Status: "Completado" (no "Pendiente" ni "Error")
- [ ] Chunk count > 0 (ej: 15 chunks)
- [ ] Botón "Reindexar" funciona sin error

### Paso 2: Consulta Básica
- [ ] Pregunta simple: "¿Qué dice el documento X?"
- [ ] Respuesta NO es "No tengo acceso..."
- [ ] Respuesta menciona contenido real del doc
- [ ] Fuentes muestran documento correcto

### Paso 3: Validación de Contenido
- [ ] Nombres propios coinciden con documento
- [ ] Fechas/numbers son correctos
- [ ] Cita información de múltiples secciones si aplica
- [ ] No inventa información no presente

### Paso 4: Consultas Avanzadas
- [ ] Sinónimos funcionan: "contrato" vs "acuerdo"
- [ ] Preguntas específicas por sección
- [ ] Comparativa entre documentos (si aplica)
- [ ] Historial de conversación mantiene contexto

### Paso 5: Límites y Errores
- [ ] Documento inexistente → respuesta apropiada
- [ ] Pregunta sin relación → "No encontré info..."
- [ ] Timeout >90s con modelo grande

---

## 🔧 DECISIÓN: ¿CAMBIAR MODELO?

### Configuración Actual
```env
OLLAMA_CHAT_MODEL=qwen2.5:7b      # 4.7GB - Lento pero preciso
OLLAMA_EMBED_MODEL=mxbai-embed-large  # 669MB - Bueno para español
```

### Opciones Comparadas

| Modelo | Tamaño | Velocidad | Calidad | Español | Recomendación |
|--------|--------|-----------|---------|---------|---------------|
| **qwen2.5:3b** | 1.9GB | ⚡ Rápido | Media | ✅ Bueno | 🟡 Para pruebas rápidas |
| **qwen2.5:7b** | 4.7GB | 🐢 Lento | Alta | ✅ Bueno | 🟢 Para producción |
| **qwen2.5-coder:7b** | 4.7GB | 🐢 Lento | Alta (código) | ✅ Bueno | 🔵 Si hay código/docs técnicos |
| **llama3.1:8b** | 4.9GB | 🐢 Lento | Muy Alta | ⚠️ Regular | 🟡 Mejor calidad, peor español |

### Mi Recomendación

**Para VALIDACIÓN AHORA:**
```bash
# Cambiar a 3B para tests rápidos
OLLAMA_CHAT_MODEL=qwen2.5:3b
```
- Ventaja: Respuestas en <30s vs >90s
- Desventaja: Menor capacidad de análisis profundo

**Para PRODUCCIÓN:**
```bash
# Mantener 7B si el hardware soporta la espera
OLLAMA_CHAT_MODEL=qwen2.5:7b
# Aumentar timeout a 180s
```

**Híbrido Sugerido:**
- Usar `3b` para consultas simples/metadata
- Usar `7b` para análisis profundo (implementar selector)

---

## 🚀 SCRIPT DE PRUEBA RÁPIDA

```bash
# 1. Activar entorno
source venv/bin/activate

# 2. Verificar modelos
curl http://localhost:11434/api/tags | grep -E "(qwen|mxbai)"

# 3. Test embedding
curl -X POST http://localhost:11434/api/embeddings \
  -H "Content-Type: application/json" \
  -d '{"model": "mxbai-embed-large", "prompt": "test"}'

# 4. Test chat
curl -X POST http://localhost:11434/api/generate \
  -H "Content-Type: application/json" \
  -d '{"model": "qwen2.5:3b", "prompt": "Responde: hola", "stream": false}'

# 5. Iniciar app
python run_web.py

# 6. Abrir navegador
open http://127.0.0.1:5008
```

---

## 📊 MÉTRICAS ESPERADAS

| Métrica | Valor Esperado | Rango Aceptable |
|---------|---------------|-----------------|
| Tiempo indexación (10 págs) | 5-15 seg | <30 seg |
| Tiempo respuesta (3B) | 10-30 seg | <60 seg |
| Tiempo respuesta (7B) | 30-90 seg | <120 seg |
| Score retrieval (chunks) | 0.60-0.90 | >0.40 |
| Chunks recuperados | 6-10 | >3 |
| Precisión factual | 85-95% | >70% |

---

## 🐛 PROBLEMAS CONOCIDOS Y SOLUCIONES

| Problema | Causa | Solución |
|----------|-------|----------|
| "Error de comunicación con motor IA" | Timeout corto | Aumentar timeout a 120s |
| "No tengo acceso al documento" | Prompt confuso | Usar formato [INICIO DOCUMENTO] |
| "expected 768 dimensions, not 1024" | Cambio de modelo embed | Ejecutar SQL: `ALTER TABLE...` |
| Respuesta genérica/vacía | Threshold alto | Bajar a 0.20 en retrieval_service.py |
| Chunks no recuperados | Query vs chunks mismatch | Verificar embeddings funcionan |

---

## ✅ PLAN DE VALIDACIÓN SUGERIDO

### Día 1: Setup y Pruebas Básicas
1. Crear admin + 2 usuarios (1 admin, 1 normal)
2. Subir 3 documentos: 1 certificado, 1 resolución, 1 informe
3. Validar indexación correcta
4. Probar consultas básicas con ambos roles

### Día 2: Pruebas RAG Exhaustivas
1. 10 preguntas variadas por documento
2. Validar precisión factual (nombres, fechas, números)
3. Probar sinónimos y reformulaciones
4. Comparar respuestas 3B vs 7B

### Día 3: Pruebas de Estrés
1. Documento grande (20+ páginas)
2. Consultas complejas (multi-documento)
3. Historial de conversación largo
4. Tiempo de respuesta promedio

### Día 4: Validación de Roles
1. Intentar acciones no permitidas como user normal
2. Verificar permisos de admin funcionan
3. Crear/eliminar usuarios
4. Validar que user normal no ve botones de admin

---

## 🎯 PRÓXIMAS MEJORAS SUGERIDAS

1. **Chunks inteligentes**: Aumentar tamaño a 1500 con contexto de sección
2. **Re-ranking**: Segunda pasada con modelo ligero
3. **Feedback usuario**: Thumbs up/down para fine-tuning
4. **Cache de respuestas**: Redis para queries repetidas
5. **Streaming**: Mostrar respuesta palabra por palabra
6. **Multi-idioma**: Detectar idioma del documento
