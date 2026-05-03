import os
import requests
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from services.retrieval_service import RetrievalService
from services.chunk_service import ChunkService

class RagService:
    # Templates de prompts dinámicos por tipo de pregunta
    PROMPT_TEMPLATES = {
        'factual': {
            'system': "Eres un analista documental experto. Tu tarea es EXTRAER datos específicos del documento con precisión. Responde de forma concisa y directa, citando solo la información solicitada.",
            'instruction': "Extrae y responde con el dato específico solicitado. Si es una fecha, nombre, número o código, proporciona únicamente ese valor.",
            'options': {'temperature': 0.1, 'top_p': 0.3}
        },
        'synthesis': {
            'system': "Eres un analista documental experto. Tu tarea es proporcionar un RESUMEN ESTRUCTURADO del documento, identificando los puntos clave y la información más relevante.",
            'instruction': "Proporciona un resumen estructurado del documento, destacando: 1) Tema principal, 2) Puntos clave, 3) Información relevante encontrada.",
            'options': {'temperature': 0.4, 'top_p': 0.7}
        },
        'analysis': {
            'system': "Eres un analista documental experto. Tu tarea es ANALIZAR e INTERPRETAR la información del documento, explicando implicaciones y relaciones.",
            'instruction': "Analiza la información proporcionada y explica las implicaciones, causas, efectos o relaciones relevantes. Proporciona un análisis fundamentado en el texto.",
            'options': {'temperature': 0.5, 'top_p': 0.8}
        },
        'procedural': {
            'system': "Eres un analista documental experto. Tu tarea es EXTRAER y PRESENTAR los pasos o procedimientos descritos en el documento de forma clara y ordenada.",
            'instruction': "Extrae y lista los pasos, procedimientos o instrucciones descritos en el documento. Presenta la información de forma numerada y secuencial.",
            'options': {'temperature': 0.2, 'top_p': 0.5}
        },
        'general': {
            'system': "Eres un analista documental experto. Tu tarea es EXTRAER Y LISTAR TODA la información relevante del documento: nombres, fechas, números, estados, datos identificativos, cláusulas, resoluciones.",
            'instruction': "Responde basándote exclusivamente en el contexto proporcionado. Extrae y lista la información relevante que responda a la pregunta.",
            'options': {'temperature': 0.3, 'top_p': 0.6}
        }
    }

    def __init__(self, retrieval_service: RetrievalService, chunk_service: ChunkService, persistence_service=None):
        """
        Garantiza un pipeline completo RAG uniéndose con RetrievalService y Ollama (Generation).
        Incluye un Enrutador de Intenciones y Detección de Contexto Documental.
        """
        self.retrieval_service = retrieval_service
        self.chunk_service = chunk_service
        self.persistence = persistence_service
        self.base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        self.chat_model = os.environ.get("OLLAMA_CHAT_MODEL", "qwen2.5:3b")

    def index_document(self, doc_id: int, processed_path: str):
        """
        REGLA 1: Solo documentos 'completed' pueden ser indexados.
        REGLA 2: is_indexed = true solo si chunk_count > 0.
        Incluye el filename en los chunks para facilitar la visualización.
        """
        if not self.persistence: return
        doc = self.persistence.get_document_by_id(doc_id)
        
        if not doc or doc['processing_status'] != 'completed':
            print(f"[WARN] Saltando indexación: Documento {doc_id} no está en estado 'completed'.")
            return

        if not os.path.exists(processed_path):
            error_msg = f"El archivo procesado no existe: {processed_path}"
            self.persistence.update_document_status(doc_id, error_log=error_msg)
            return

        with open(processed_path, "r", encoding="utf-8") as f:
            text = f.read()

        chunks = self.chunk_service.chunk_text(text, str(doc_id))

        # Inyectar filename en cada chunk para el RetrievalService
        for c in chunks:
            c["filename"] = doc["filename"]

        has_chunks = len(chunks) > 0
        self.retrieval_service.remove_document_chunks(doc_id)

        if has_chunks:
            self.retrieval_service.add_chunks(chunks)
            print(f"[OK] Documento {doc_id} indexado con {len(chunks)} chunks.")
        else:
            print(f"[INFO] Documento {doc_id} no generó chunks (posible archivo vacío).")

        self.persistence.update_document_status(
            doc_id,
            is_indexed=has_chunks,
            chunk_count=len(chunks),
            last_indexed_at=datetime.now() if has_chunks else None
        )

        # NUEVO: Extraer metadatos con LLM después del chunking
        if has_chunks and text:
            try:
                from services.metadata_extraction_service import MetadataExtractionService
                metadata_service = MetadataExtractionService()
                metadata = metadata_service.extract_metadata(text, doc["filename"])

                if metadata and not metadata.get("metadata_extraction_failed"):
                    self.persistence.update_document_metadata(doc_id, metadata)
                    print(f"[OK] Metadatos extraídos para documento {doc_id}")
                elif metadata:
                    # Guardar aunque haya fallado para marcarlo
                    self.persistence.update_document_metadata(doc_id, metadata)
                    print(f"[WARN] Extracción de metadatos falló para documento {doc_id}")
            except Exception as e:
                print(f"[ERROR] Error extrayendo metadatos para doc {doc_id}: {e}")

    def reindex_document(self, doc_id: int):
        if not self.persistence: return
        doc = self.persistence.get_document_by_id(doc_id)
        if doc:
            self.index_document(doc["id"], doc["processed_path"])

    def delete_document(self, doc_id: int) -> bool:
        """
        Elimina por completo un documento: Vector Store (PostgreSQL), Archivos y Base de Datos.
        """
        # 1. Eliminar Chunks del Vector Store
        self.retrieval_service.remove_document_chunks(doc_id)
        
        # 2. Eliminar de DB y Archivos
        if self.persistence:
            return self.persistence.delete_document(doc_id)
        return False

    def _normalize_text(self, text: str) -> str:
        """ Normaliza texto para comparaciones seguras (minúsculas, sin extensiones ni símbolos). """
        if not text: return ""
        t = text.strip()
        # Limpiar comillas y puntuación del inicio/final
        t = re.sub(r'^["\'\u201c\u201d\.\s]+|["\'\u201c\u201d\.\s]+$', '', t)
        t = t.lower()
        t = re.sub(r'\.(pdf|docx|txt)$', '', t)
        t = re.sub(r'[^a-z0-9\s]', ' ', t)
        return " ".join(t.split())

    def _detect_question_type(self, question: str) -> str:
        """
        Detecta el tipo de pregunta para seleccionar el prompt adecuado.
        Retorna: 'factual', 'synthesis', 'analysis', 'procedural', 'general'
        """
        q_lower = question.lower()
        
        # Patrones para cada tipo
        factual_patterns = [
            r'\b(cu[aá]l|qui[eé]n|cu[aá]ndo|cu[aá]nto|d[oó]nde|qu[eé])\s+(es|son|fue|fueron|tiene|tienen|est[aá]|fue|est[áa]n)\b',
            r'\b(n[uú]mero|fecha|dni|codigo|c[oó]digo|nombre|monto|cantidad|valor|estado)\b',
            r'\b(d[oó]nde|cu[aá]ndo|en qu[eé] fecha)\b'
        ]
        
        synthesis_patterns = [
            r'\b(de qu[eé] trata|sobre qu[eé]|resumen|sintesis|s[ií]ntesis|contenido|de qu[eé] habla|qu[eé] dice|qu[eé] information)\b',
            r'\b(hablame|cu[eé]ntame|dime|explicame|expl[ií]came)\s+(sobre|de|acerca de)\b',
            r'\b(en resumen|en pocas palabras|brevemente)\b'
        ]
        
        analysis_patterns = [
            r'\b(implicaciones?|consecuencias?|impacto|efecto|por qu[eé]|causa|raz[oó]n|motivo)\b',
            r'\b(analiza|analizar|interpreta|eval[uú]a|significado|qu[eé] significa)\b',
            r'\b(c[oó]mo afecta|qu[eé] implica|qu[eé] consecuencias)\b'
        ]
        
        procedural_patterns = [
            r'\b(c[oó]mo\s+(se\s+)?hace|c[oó]mo\s+(se\s+)?realiza|procedimiento|proceso|pasos?)\b',
            r'\b(qu[eé] debo hacer|c[uú]ales son los pasos|gu[ií]a|c[oó]mo proceder)\b',
            r'\b(instrucciones?|requisitos?|paso a paso)\b'
        ]
        
        # Verificar cada categoría
        for pattern in factual_patterns:
            if re.search(pattern, q_lower):
                return 'factual'
        
        for pattern in synthesis_patterns:
            if re.search(pattern, q_lower):
                return 'synthesis'
        
        for pattern in analysis_patterns:
            if re.search(pattern, q_lower):
                return 'analysis'
        
        for pattern in procedural_patterns:
            if re.search(pattern, q_lower):
                return 'procedural'
        
        return 'general'

    # Tipos de documento soportados para detección en queries
    DOC_TYPE_KEYWORDS = {
        'carta': ['carta', 'cartas', 'correspondencia'],
        'decreto': ['decreto', 'decretos', 'decreta'],
        'resolución': ['resolución', 'resolucion', 'resoluciones'],
        'informe': ['informe', 'informes', 'reporte', 'reportes'],
        'acta': ['acta', 'actas'],
        'memorando': ['memorando', 'memorandum', 'memo', 'memos'],
        'contrato': ['contrato', 'contratos'],
        'certificado': ['certificado', 'certificados', 'certificación'],
        'constancia': ['constancia', 'constancias'],
        'proyecto': ['proyecto', 'proyectos'],
        'matriz': ['matriz', 'matrices', 'matriz de consistencia'],
        'formulario': ['formulario', 'formularios'],
        'reglamento': ['reglamento', 'reglamentos'],
        'plan': ['plan', 'planes'],
        'convenio': ['convenio', 'convenios', 'acuerdo', 'acuerdos'],
        'oficio': ['oficio', 'oficios'],
        'circular': ['circular', 'circulares'],
        'directiva': ['directiva', 'directivas'],
        'web': ['web', 'página web', 'website', 'sitio web'],
    }

    def _detect_metadata_filters(self, question: str) -> Dict:
        """
        Detecta filtros de metadatos en la consulta del usuario.
        Retorna: {'doc_type': str|None, 'doc_year': int|None}
        """
        q_lower = question.lower()
        filters = {'doc_type': None, 'doc_year': None}

        # Detectar tipo de documento
        for doc_type, keywords in self.DOC_TYPE_KEYWORDS.items():
            for keyword in keywords:
                # Buscar palabra completa (con límites de palabra)
                pattern = r'\b' + re.escape(keyword) + r'\b'
                if re.search(pattern, q_lower):
                    filters['doc_type'] = doc_type
                    print(f"[METADATA FILTER] Detectado tipo: {doc_type}")
                    break
            if filters['doc_type']:
                break

        # Detectar año (4 dígitos entre 1900-2100)
        year_patterns = [
            r'\b(19\d{2}|20\d{2})\b',  # 1900-2099
            r'(?:año|del|de el)\s+(19\d{2}|20\d{2})',  # "año 2023", "del 2014"
        ]
        for pattern in year_patterns:
            match = re.search(pattern, q_lower)
            if match:
                year_str = match.group(1) if match.groups() else match.group(0)
                try:
                    year = int(year_str)
                    if 1900 <= year <= 2100:
                        filters['doc_year'] = year
                        print(f"[METADATA FILTER] Detectado año: {year}")
                        break
                except ValueError:
                    continue

        return filters

    def _detect_document_context(self, question: str) -> Dict:
        """
        Detecta si la pregunta menciona algún documento del repositorio.
        Nivel 1: Coincidencia Exacta/Fuerte -> Filtro Duro
        Nivel 2: Coincidencia Parcial -> Boost
        """
        if not self.persistence: return {"filter_id": None, "boost_id": None, "doc_name": None}
        
        docs = self.persistence.get_all_documents()
        q_norm = self._normalize_text(question)
        
        # 1. Búsqueda de Coincidencia Exacta o Fuerte (Filtro Duro)
        for doc in docs:
            fname = doc['filename']
            fname_norm = self._normalize_text(fname)
            
            # Caso exacto: el nombre real aparece en la pregunta
            if fname.lower() in question.lower():
                return {"filter_id": doc['id'], "boost_id": None, "doc_name": fname}
            
            # Caso fuerte: el nombre normalizado aparece como frase exacta
            if fname_norm and fname_norm in q_norm:
                return {"filter_id": doc['id'], "boost_id": None, "doc_name": fname}

        # 2. Búsqueda de Coincidencia Parcial (Boost)
        for doc in docs:
            fname_norm = self._normalize_text(doc['filename'])
            if not fname_norm: continue
            
            # Si alguna palabra significativa (>3 letras) del nombre está en la pregunta
            keywords = [kw for kw in fname_norm.split() if len(kw) > 3]
            if any(kw in q_norm for kw in keywords):
                return {"filter_id": None, "boost_id": doc['id'], "doc_name": doc['filename']}

        return {"filter_id": None, "boost_id": None, "doc_name": None}

    def _is_numeric_query(self, question: str) -> bool:
        """
        Detecta si la query busca datos numéricos exactos (DNI, códigos, fechas).
        Estas queries necesitan mayor peso BM25 para encontrar coincidencias exactas.
        """
        q_lower = question.lower()
        numeric_keywords = [
            r'\bdni\b', r'\bcodigo\b', r'\bc[oó]digo\b', r'\bnumero\b', 
            r'\bn[uú]mero\b', r'\bfecha\b', r'\bruc\b', r'\bexpediente\b',
            r'\btelefono\b', r'\btel[eé]fono\b', r'\bcelular\b',
            r'\bdocumento\b.*\bidentidad\b', r'\bidentificaci[oó]n\b',
            r'\bpartida\b', r'\blibreta\b', r'\belectoral\b', r'\bpasaporte\b',
            r'\bmatricula\b', r'\bregistro\b', r'\bserial\b', r'\bserie\b',
            r'\bcuenta\b', r'\bcontrato\b', r'\borden\b', r'\bacta\b',
            r'\bfolio\b', r'\btomo\b', r'\bficha\b', r'\bfile\b',
            r'\bcertificado\b', r'\blicencia\b', r'\btarjeta\b',
            r'\bplaca\b', r'\bchasis\b', r'\bmotor\b', r'\bvin\b',
            r'\bclave\b', r'\bcontraseña\b', r'\bpin\b', r'\bpassword\b',
            r'\bip\b', r'\bmac\b', r'\bimei\b', r'\bimsi\b', r'\besn\b',
            r'\bmonto\b', r'\bsaldo\b', r'\bimporte\b', r'\bcantidad\b',
            r'\bvalor\b', r'\bprecio\b', r'\bcosto\b', r'\btarifa\b',
            r'\bafp\b', r'\bips\b', r'\bcuspp\b', r'\bessalud\b',
            r'\bsunedu\b', r'\brnec\b', r'\bruc\b', r'\bdni\b', r'\bce\b',
            r'\bptp\b', r'\bcie\b', r'\bpas\b', r'\bcm\b', r'\ble\b',
        ]
        for pattern in numeric_keywords:
            if re.search(pattern, q_lower):
                return True
        return False

    def _classify_intent(self, question: str) -> str:
        """
        Clasifica la intención en 4 categorías:
        'greeting', 'metadata', 'content', 'unknown'
        """
        q = self._normalize_text(question)
        
        # Nivel 1 — Metadata PRIMERO (tiene prioridad sobre saludos)
        # FIX: Negative lookahead para excluir preguntas de contenido ("de qué habla/trata/contiene")
        metadata_patterns = [
            r'\b(qu[eé]|cu[aá]les?|cu[aá]ntos?)\b(?!.{0,30}\b(habla|trata|contiene|dice|sobre|acerca|explica))\b.{0,25}\b(documentos?|archivos?)\b',
            r'\b(documentos?|archivos?)\b(?!.{0,30}\b(habla|trata|contiene|dice|sobre|acerca|explica))\b.{0,20}\b(indexados?|procesados?|disponibles?|listos?)',
            r'\b(listar?|mostrar?|ver|dame)\b.{0,15}\b(documentos?|archivos?)\b(?!.{0,30}\b(habla|trata|contiene|dice|sobre))',
            r'\brepositorio\b(?!.{0,30}\b(habla|trata|contiene|dice|sobre))',
            r'\bqu[eé]\s+(tienes?|hay)\s+(disponible|indexado)(?!.{0,30}\b(habla|trata|contiene|dice|sobre))',
        ]
        for p in metadata_patterns:
            if re.search(p, q):
                print(f"[ROUTER] METADATA detectado: '{question}'")
                return 'metadata'
        
        # Nivel 2 — Saludos PUROS (sin pregunta de fondo)
        greeting_patterns = [
            r'^(hola|buenos|buenas|hey|hi|hello)$',  # ← solo si es SOLO el saludo
            r'^(gracias|ok|okay|perfecto|entendido|listo|genial|excelente)$',
            r'^(adios|hasta|chao|bye)$',
        ]
        for p in greeting_patterns:
            if re.search(p, q):
                print(f"[ROUTER] GREETING detectado: '{question}'")
                return 'greeting'
        
        # Nivel 3 — Contenido obvio
        content_patterns = [
            r'(hablame|cuentame|explica|resume|describe|analiza)',
            r'(que\s+dice|que\s+contiene|que\s+trata)',
            r'(cuando\s+(fue|es|vence|expira|caduca|emitido|nace))',
            r'(fecha\s+(de\s+)?(emision|vencimiento|caducidad|nacimiento))',
            r'\b(dni|ruc|telefono|celular|correo|domicilio)\b',
            r'\b(cu[aá]l|qui[eé]n|cu[aá]nto|d[oó]nde)\b',
            # NUEVO: Capturar antes de que lleguen a metadata
            r'\b(de\s+qu[eé])\b.{0,20}\b(habla|trata|tratan)\b.{0,20}\b(documentos?|archivos?|texto)\b',
            r'\b(sobre\s+qu[eé])\b.{0,20}\b(habla|trata|tratan)\b.{0,20}\b(documentos?|archivos?|texto)\b',
            r'\b(documentos?|archivos?)\b.{0,15}\b(habla|trata|dice|contiene|explica)\b',
        ]
        for p in content_patterns:
            if re.search(p, q):
                return 'content'
        
        # Nivel 4 — Ollama para ambiguos
        try:
            prompt = f"""Clasifica esta pregunta en UNA palabra.

GREETING = saludo o mensaje sin pregunta real
METADATA = pregunta sobre cuántos archivos hay o lista de documentos
CONTENT = pregunta sobre el contenido de algún documento

Si hay duda, responde CONTENT.
Pregunta: "{question}"
Responde solo: GREETING, METADATA o CONTENT"""

            url = f"{self.base_url}/api/generate"
            response = requests.post(url, json={"model": self.chat_model, "prompt": prompt, "stream": False}, timeout=10)
            result = response.json().get("response", "CONTENT").strip().upper().split()[0]
            print(f"[ROUTER] Ollama clasificó '{result}': '{question}'")
            return result.lower() if result in ['GREETING', 'METADATA', 'CONTENT'] else 'content'
        except:
            return 'content'

    def _is_metadata_query(self, question: str) -> bool:
        """Deprecated: usar _classify_intent() en su lugar."""
        return self._classify_intent(question) == 'metadata'

    def _handle_metadata_query(self) -> Dict:
        if not self.persistence:
            return {"answer": "Error: Persistencia no disponible.", "sources": []}
        docs = self.persistence.get_all_documents()
        total = len(docs)
        indexed = len([d for d in docs if d.get('is_indexed')])
        failed = len([d for d in docs if d.get('processing_status') == 'failed'])
        if total == 0:
            return {"answer": "Actualmente no hay documentos registrados en el sistema.", "sources": []}
        answer = f"Actualmente el repositorio cuenta con {total} documentos en total.\n\n"
        answer += f"- Listos para consulta: {indexed}\n"
        if failed > 0:
            answer += f"- Con errores de procesamiento: {failed}\n"
        answer += "\nLista de archivos:\n"
        for d in docs:
            status_label = "Listo" if d.get('is_indexed') else ("Error" if d.get('processing_status') == 'failed' else "Pendiente")
            answer += f"- {d['filename']} ({status_label})\n"
        return {"answer": answer, "sources": []}

    def _clean_response(self, text: str) -> str:
        """
        Limpia y normaliza el formato de la respuesta del LLM.
        Elimina asteriscos sueltos, normaliza markdown y mejora legibilidad.
        """
        if not text:
            return text
            
        # 1. Eliminar patrones de asteriscos sueltos (*** o ** sin contenido)
        text = re.sub(r'\*\*\*+', '', text)  # *** → vacío
        text = re.sub(r'\*\*\s*\*\*', '', text)  # ** ** → vacío
        
        # 2. Normalizar negritas: **texto** con espacios internos extra
        text = re.sub(r'\*\*\s+([^*]+?)\s+\*\*', r'**\1**', text)
        
        # 3. Eliminar asteriscos sueltos al inicio/final de líneas
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            # Quitar ** o * sueltos al inicio/final
            line = re.sub(r'^[\*\s]+', '', line)
            line = re.sub(r'[\*\s]+$', '', line)
            cleaned_lines.append(line)
        text = '\n'.join(cleaned_lines)
        
        # 4. Normalizar espacios múltiples
        text = re.sub(r' {2,}', ' ', text)
        
        # 5. Eliminar líneas vacías múltiples (más de 2 seguidas)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # 6. Limpiar espacios alrededor de puntuación
        text = re.sub(r'\s+([.,;:!?])', r'\1', text)
        text = re.sub(r'([.,;:!?])\s+', r'\1 ', text)
        
        # 7. Strip final
        text = text.strip()
        
        return text

    def generate_response(self, question: str, top_k: int = 10, document_id: str = None, chat_history: list = None) -> Dict:
        # Limpiar pregunta de comillas y puntos extras del frontend
        question = question.strip().strip('"\'.,')
        
        intent = self._classify_intent(question)
        print(f"[ROUTER] Intent: '{intent}' para: '{question}'")
        
        if intent == 'greeting':
            return {
                "answer": "¡Hola! Soy el asistente documental EPIIS. Puedo ayudarte a consultar documentos del repositorio, buscar información específica o responder preguntas sobre los archivos indexados. ¿En qué te puedo ayudar?",
                "sources": []
            }
        
        # FIX: Solo procesar como metadata si NO hay un document_id explícito
        # Si hay filtro de documento, forzar RAG aunque el router diga metadata
        if intent == 'metadata' and not document_id:
            return self._handle_metadata_query()
        
        # --- DETECCIÓN DE CONTEXTO AUTOMÁTICO ---
        auto_ctx = self._detect_document_context(question)

        # NUEVO: Detectar filtros de metadatos (tipo y año)
        metadata_filters = self._detect_metadata_filters(question)

        final_filter_id = document_id or auto_ctx["filter_id"]
        final_boost_id = auto_ctx["boost_id"]

        # --- LOG DE CONTEXTO ---
        if final_filter_id:
            print(f"[INFO] Aplicando FILTRO DURO por detección: {final_filter_id}")
        elif final_boost_id:
            print(f"[INFO] Aplicando BOOST por detección parcial: {final_boost_id}")

        if metadata_filters['doc_type'] or metadata_filters['doc_year']:
            print(f"[INFO] Filtros de metadatos detectados: {metadata_filters}")

        # Detectar si es query numérica y pasar query_type
        query_type = "numeric" if self._is_numeric_query(question) else "general"
        if query_type == "numeric":
            print(f"[INFO] Query numérica detectada: '{question}'")

        # --- EJECUCIÓN DE BÚSQUEDA ---
        retrieval_results = self.retrieval_service.search(
            question,
            top_k=top_k,
            document_id=final_filter_id,
            boost_id=final_boost_id,
            sql_threshold=0.35,
            min_score=0.40,
            query_type=query_type,
            # NUEVO: Pasar filtros de metadatos
            doc_type_filter=metadata_filters.get('doc_type'),
            doc_year_filter=metadata_filters.get('doc_year')
        )

        # --- FILTRO DE CALIDAD ---
        # El filtro de score > 0.35 ahora se maneja dentro del retrieval_service (SQL)
        valid_results = retrieval_results
        
        if not valid_results:
            return {
                "answer": "No se encontró información relevante en los documentos procesados para responder a esta consulta con seguridad.",
                "sources": [],
                "auto_detected_doc": auto_ctx["doc_name"] if (final_filter_id or final_boost_id) else None
            }

        # NUEVO: Si hay filtro de tipo y múltiples documentos, listar en vez de mezclar RAG
        if metadata_filters.get('doc_type') and not final_filter_id:
            unique_doc_ids = set(r['document_id'] for r in valid_results)

            if len(unique_doc_ids) > 1:
                # Múltiples documentos → listar y pedir especificación
                doc_list = self.persistence.get_documents_by_type(
                    metadata_filters['doc_type'],
                    metadata_filters.get('doc_year')
                )

                answer = f"Encontré {len(doc_list)} documentos de tipo "
                answer += f"'{metadata_filters['doc_type']}'"
                if metadata_filters.get('doc_year'):
                    answer += f" del año {metadata_filters['doc_year']}"
                answer += ":\n\n"

                for i, doc in enumerate(doc_list[:20], 1):  # Limitar a 20
                    year = f" ({doc['doc_year']})" if doc.get('doc_year') else ""
                    summary = f"\n   {doc['summary'][:100]}..." if doc.get('summary') else ""
                    answer += f"{i}. {doc['filename']}{year}{summary}\n"

                if len(doc_list) > 20:
                    answer += f"\n... y {len(doc_list) - 20} más."

                answer += "\n¿Sobre cuál te gustaría consultar?"

                return {"answer": answer, "sources": []}

        # Detectar tipo de pregunta ANTES de construir el contexto (para limitar según tipo)
        question_type = self._detect_question_type(question)
        
        # 2. Formateo de las fuentes de Contexto (limitado según tipo)
        # Limitar contexto según tipo — numeric SIEMPRE tiene prioridad
        if query_type == "numeric":
            max_chunks = 8
        elif question_type == 'synthesis':
            max_chunks = 5
        elif question_type == 'factual':
            max_chunks = 4
        else:
            max_chunks = 6
        
        context_parts = [res['text'] for res in valid_results[:max_chunks]]
        context_text = "\n\n".join(context_parts)
        
        # --- DEBUG: Imprimir lo que se recuperó ---
        print(f"[DEBUG] Chunks recuperados: {len(valid_results)}, usados: {len(context_parts)} (tipo: {question_type})")
        for i, r in enumerate(valid_results[:3]):
            print(f"[DEBUG] Chunk {i}: score={r.get('score', 0):.3f}, doc_id={r.get('document_id')}, text[:100]={r.get('text', '')[:100]}...")
        print(f"[DEBUG] Contexto total length: {len(context_text)} chars")
        
        # 2.5 Formateo del Historial (Memoria)
        historial_texto = ""
        if chat_history:
            turnos = []
            for turno in chat_history[-3:]:  # últimos 3 turnos
                turnos.append(f"Usuario: {turno['pregunta']}")
                turnos.append(f"Asistente: {turno['respuesta'][:800]}...")  # Expandido de 300 a 800
            historial_texto = "\n".join(turnos)

        # 3. Construcción del Prompt Instruccional para Qwen
        seccion_historial = ""
        if historial_texto:
            seccion_historial = f"---\nCONVERSACIÓN PREVIA (para mantener coherencia):\n{historial_texto}\n"

        # Agregar info del documento detectado si existe
        doc_context = ""
        if auto_ctx["doc_name"]:
            doc_context = f"""\nDOCUMENTO CONSULTADO: {auto_ctx['doc_name']}
El usuario está preguntando específicamente sobre este documento. Analiza TODO el contenido proporcionado.\n"""

        # Obtener template según tipo de pregunta (ya detectado arriba)
        template = self.PROMPT_TEMPLATES.get(question_type, self.PROMPT_TEMPLATES['general'])

        # Sobrescribir template SOLO si hay filtro de tipo de documento activo
        # y no es una query numérica (para no afectar búsquedas de DNI/códigos)
        if metadata_filters.get('doc_type') and query_type != 'numeric':
            template = self.PROMPT_TEMPLATES['synthesis']
            system_msg = (
                f"Eres un analista documental experto. Se encontraron documentos "
                f"de tipo '{metadata_filters['doc_type']}' en el repositorio. "
                f"Describe y lista la información encontrada de forma clara y directa."
            )
        else:
            system_msg = template['system']
        
        # Nuevo orden: PREGUNTA → INSTRUCCIÓN → TEXTO DEL DOCUMENTO
        user_msg = f"PREGUNTA: {question}\n\n{template['instruction']}\n\nTEXTO DEL DOCUMENTO:\n{context_text}"
        
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.chat_model,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg}
            ],
            "stream": False,
            "options": template['options']  # Usar options específicas del template
        }
        
        try:
            # Timeout según complejidad
            timeout = 60 if question_type == 'factual' else 90
            response = requests.post(url, json=payload, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            final_answer = data.get("message", {}).get("content", "Error: No se recibió respuesta válida.")
            
            # LIMPIAR FORMATO: Eliminar *** y normalizar markdown
            final_answer = self._clean_response(final_answer)
            
        except requests.exceptions.Timeout:
            final_answer = "⏱️ El procesamiento tardó demasiado. Intenta con una pregunta más específica o espera un momento."
        except Exception as e:
            final_answer = f"Error de comunicación con el motor de IA: {str(e)}"
            
        if self.persistence:
             user_id = self.persistence.create_or_get_user("sistema", "sistema@local.epiis")
             query_id = self.persistence.register_query(user_id, question)
             self.persistence.register_response(query_id, final_answer, self.chat_model)

        # 6. Estructurar fuentes para la UI
        sources = [
            {
                "document_id": item["document_id"],
                "filename": item.get("filename", "Archivo desconocido"),
                "chunk_index": item["chunk_index"],
                "score": item["score"],
                "text": item['text']
            }
            for item in valid_results
        ]
            
        return {
            "answer": final_answer, 
            "sources": sources,
            "auto_detected_doc": auto_ctx["doc_name"] if (final_filter_id or final_boost_id) else None
        }
