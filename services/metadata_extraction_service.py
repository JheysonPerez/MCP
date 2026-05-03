"""
Servicio de extracción de metadatos de documentos usando LLM (Ollama).
Extrae: tipo, fecha, entidades, keywords y resumen automáticamente.
"""

import os
import json
import re
import time
import requests
from typing import Dict, List, Any, Optional
from datetime import datetime


class MetadataExtractionService:
    """
    Extrae metadatos estructurados de documentos usando LLM (Ollama).
    """

    # Tipos de documento soportados
    DOC_TYPES = [
        'carta', 'decreto', 'resolución', 'informe', 'acta', 'memorando',
        'contrato', 'certificado', 'constancia', 'proyecto', 'matriz',
        'formulario', 'reglamento', 'plan', 'convenio', 'oficio',
        'circular', 'directiva', 'web', 'otro'
    ]

    def __init__(self):
        self.base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        self.chat_model = os.environ.get("OLLAMA_CHAT_MODEL", "qwen2.5:3b")
        self.max_retries = 2
        self.delay_between_calls = 0.5  # segundos

    def _build_extraction_prompt(self, text: str, filename: str) -> str:
        """Construye el prompt para extracción de metadatos."""
        # Usar inicio y final del documento para contexto
        text_start = text[:3000] if len(text) > 3000 else text
        text_end = text[-500:] if len(text) > 3500 else ""

        combined_text = text_start
        if text_end:
            combined_text += f"\n\n[...contenido intermedio omitido...]\n\n{text_end}"

        return f"""Eres un analista documental experto. Analiza el siguiente documento y extrae información estructurada.

Nombre del archivo: {filename}

Texto del documento:
---
{combined_text}
---

Extrae la siguiente información en formato JSON:

{{
  "doc_type": "TIPO_DE_DOCUMENTO",
  "doc_date": "YYYY-MM-DD o null",
  "doc_year": NUMERO_AÑO o null,
  "personas": ["Nombre Persona 1", "Nombre Persona 2"],
  "organizaciones": ["Nombre Empresa/Institución 1"],
  "lugares": ["Ciudad", "País", "Dirección relevante"],
  "temas": ["tema principal 1", "tema 2", "tema 3"],
  "keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
  "summary": "Resumen del documento en 2-3 oraciones máximo"
}}

Instrucciones:
- doc_type: debe ser uno de: {', '.join(self.DOC_TYPES)}
- doc_date: fecha mencionada en el documento (NO la fecha de subida), formato ISO
- doc_year: año como número entero (ej: 2014)
- personas: nombres completos de personas mencionadas
- organizaciones: empresas, instituciones, departamentos
- lugares: ciudades, países, direcciones relevantes
- temas: 3-5 temas principales del documento
- keywords: 5-10 palabras clave relevantes
- summary: máximo 2-3 oraciones, captura la esencia del documento

REGLAS ESPECIALES PARA doc_type:
- Si el documento es una página web scrapeada (contiene URLs, estructura HTML, menús de navegación), usar tipo 'web'.
- Si es una matriz o tabla de consistencia (tabla con criterios/variables cruzadas), usar tipo 'matriz'.
- Usa 'otro' SOLO si realmente no encaja en ninguna categoría anterior.

Responde SOLO con el JSON válido, sin markdown, sin explicaciones adicionales."""

    def _extract_with_llm(self, text: str, filename: str, attempt: int = 1) -> Optional[Dict]:
        """Llama a Ollama para extraer metadatos."""
        try:
            prompt = self._build_extraction_prompt(text, filename)
            url = f"{self.base_url}/api/generate"

            response = requests.post(
                url,
                json={
                    "model": self.chat_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "top_p": 0.8
                    }
                },
                timeout=60
            )
            response.raise_for_status()
            result_text = response.json().get("response", "")

            # Limpiar posible markdown
            result_text = result_text.strip()
            if result_text.startswith("```json"):
                result_text = result_text[7:]
            if result_text.startswith("```"):
                result_text = result_text[3:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]
            result_text = result_text.strip()

            # Parsear JSON
            data = json.loads(result_text)

            # Validar campos requeridos
            if "doc_type" not in data:
                return None

            # Normalizar doc_type
            doc_type = data.get("doc_type", "otro").lower().strip()
            if doc_type not in self.DOC_TYPES:
                # Intentar mapear o usar 'otro'
                doc_type = self._normalize_doc_type(doc_type)
            data["doc_type"] = doc_type

            # Normalizar año y fecha
            data["doc_year"] = self._extract_year(data.get("doc_year"), data.get("doc_date"))
            data["doc_date"] = self._normalize_date(data.get("doc_date"))

            # Asegurar listas
            data["personas"] = data.get("personas", []) or []
            data["organizaciones"] = data.get("organizaciones", []) or []
            data["lugares"] = data.get("lugares", []) or []
            data["temas"] = data.get("temas", []) or []
            data["keywords"] = data.get("keywords", []) or []
            data["summary"] = data.get("summary", "") or ""

            return data

        except json.JSONDecodeError as e:
            print(f"[METADATA] Error parseando JSON (intento {attempt}): {e}")
            if attempt < self.max_retries:
                time.sleep(1)
                return self._extract_with_llm(text, filename, attempt + 1)
            return None

        except Exception as e:
            print(f"[METADATA] Error en extracción (intento {attempt}): {e}")
            if attempt < self.max_retries:
                time.sleep(1)
                return self._extract_with_llm(text, filename, attempt + 1)
            return None

    def _normalize_doc_type(self, doc_type: str) -> str:
        """Normaliza el tipo de documento a uno de los soportados."""
        doc_type = doc_type.lower().strip()

        mappings = {
            'carta': 'carta',
            'decreto': 'decreto',
            'decreta': 'decreto',
            'resolucion': 'resolución',
            'resolución': 'resolución',
            'informe': 'informe',
            'reporte': 'informe',
            'acta': 'acta',
            'memorandum': 'memorando',
            'memorando': 'memorando',
            'memo': 'memorando',
            'contrato': 'contrato',
            'certificado': 'certificado',
            'constancia': 'constancia',
            'proyecto': 'proyecto',
            'matriz': 'matriz',
            'matriz de consistencia': 'matriz',
            'formulario': 'formulario',
            'reglamento': 'reglamento',
            'plan': 'plan',
            'convenio': 'convenio',
            'oficio': 'oficio',
            'circular': 'circular',
            'directiva': 'directiva',
            'web': 'web',
            'página web': 'web',
            'website': 'web',
            'otro': 'otro',
        }

        return mappings.get(doc_type, 'otro')

    def _extract_year(self, year_val: Any, date_val: Any) -> Optional[int]:
        """Extrae el año del documento."""
        if year_val and isinstance(year_val, int):
            if 1900 <= year_val <= 2100:
                return year_val

        if date_val and isinstance(date_val, str):
            match = re.search(r'(\d{4})', date_val)
            if match:
                year = int(match.group(1))
                if 1900 <= year <= 2100:
                    return year

        return None

    def _normalize_date(self, date_val: Any) -> Optional[str]:
        """Normaliza la fecha a formato ISO."""
        if not date_val:
            return None

        if isinstance(date_val, str):
            # Intentar parsear diferentes formatos
            patterns = [
                (r'(\d{4})-(\d{2})-(\d{2})', lambda m: f"{m.group(1)}-{m.group(2)}-{m.group(3)}"),
                (r'(\d{2})/(\d{2})/(\d{4})', lambda m: f"{m.group(3)}-{m.group(2)}-{m.group(1)}"),
                (r'(\d{2})-(\d{2})-(\d{4})', lambda m: f"{m.group(3)}-{m.group(2)}-{m.group(1)}"),
            ]

            for pattern, formatter in patterns:
                match = re.match(pattern, date_val)
                if match:
                    try:
                        result = formatter(match)
                        # Validar que sea fecha válida
                        datetime.strptime(result, '%Y-%m-%d')
                        return result
                    except ValueError:
                        continue

        return None

    def extract_metadata(self, text: str, filename: str) -> Dict[str, Any]:
        """
        Extrae metadatos de un documento.

        Retorna dict con:
        - doc_type, doc_date, doc_year
        - extracted_entities (personas, organizaciones, lugares, temas)
        - keywords, summary
        - classification_confidence
        - metadata_extraction_failed (bool)
        """
        print(f"[METADATA] Extrayendo metadatos de: {filename}")

        raw_data = self._extract_with_llm(text, filename)

        if raw_data is None:
            print(f"[METADATA] ❌ Falló extracción para: {filename}")
            return {
                "doc_type": None,
                "doc_date": None,
                "doc_year": None,
                "extracted_entities": None,
                "keywords": None,
                "summary": None,
                "classification_confidence": 0.0,
                "metadata_extraction_failed": True
            }

        # Construir entities JSONB
        entities = {
            "personas": raw_data.get("personas", []),
            "organizaciones": raw_data.get("organizaciones", []),
            "lugares": raw_data.get("lugares", []),
            "temas": raw_data.get("temas", [])
        }

        # Calcular confianza simplificada
        confidence = self._calculate_confidence(raw_data)

        result = {
            "doc_type": raw_data.get("doc_type"),
            "doc_date": raw_data.get("doc_date"),
            "doc_year": raw_data.get("doc_year"),
            "extracted_entities": entities,
            "keywords": raw_data.get("keywords", []),
            "summary": raw_data.get("summary", ""),
            "classification_confidence": confidence,
            "metadata_extraction_failed": False
        }

        print(f"[METADATA] ✓ Extraído: {result['doc_type']} ({result['doc_year']}) conf={confidence:.2f}")
        return result

    def _calculate_confidence(self, data: Dict) -> float:
        """Calcula una confianza simple basada en campos completados."""
        score = 0.0
        total = 6  # campos principales

        if data.get("doc_type") and data["doc_type"] != "otro":
            score += 1
        if data.get("doc_year"):
            score += 1
        if data.get("doc_date"):
            score += 1
        if data.get("personas"):
            score += 1
        if data.get("keywords") and len(data["keywords"]) >= 3:
            score += 1
        if data.get("summary") and len(data["summary"]) > 20:
            score += 1

        return score / total

    def classify_batch(self, doc_ids: List[int], persistence_service) -> Dict[str, Any]:
        """
        Procesa múltiples documentos en lote.

        Args:
            doc_ids: Lista de IDs de documentos
            persistence_service: Servicio de persistencia para obtener/guardar datos

        Retorna resumen del procesamiento.
        """
        print(f"[METADATA BATCH] Iniciando procesamiento de {len(doc_ids)} documentos")

        processed = 0
        failed = 0
        type_counts = {}

        for doc_id in doc_ids:
            try:
                # Obtener documento
                doc = persistence_service.get_document_by_id(doc_id)
                if not doc:
                    print(f"[METADATA BATCH] ⚠ Documento {doc_id} no encontrado")
                    failed += 1
                    continue

                # Si ya tiene metadatos, saltar
                if doc.get("doc_type") and not doc.get("metadata_extraction_failed"):
                    print(f"[METADATA BATCH] ⏭ Saltando {doc['filename']} (ya tiene metadatos)")
                    continue

                # Leer texto procesado
                processed_path = doc.get("processed_path")
                if not processed_path or not os.path.exists(processed_path):
                    print(f"[METADATA BATCH] ⚠ No hay texto procesado para {doc['filename']}")
                    failed += 1
                    continue

                with open(processed_path, 'r', encoding='utf-8') as f:
                    text = f.read()

                # Extraer metadatos
                metadata = self.extract_metadata(text, doc['filename'])

                # Guardar en DB
                persistence_service.update_document_metadata(doc_id, metadata)

                if metadata["metadata_extraction_failed"]:
                    failed += 1
                else:
                    processed += 1
                    doc_type = metadata.get("doc_type", "otro")
                    type_counts[doc_type] = type_counts.get(doc_type, 0) + 1

                    print(f"[METADATA BATCH] ✓ {doc['filename']} → {doc_type} ({metadata.get('doc_year')}) conf={metadata['classification_confidence']:.2f}")

                # Delay para no saturar Ollama
                time.sleep(self.delay_between_calls)

            except Exception as e:
                print(f"[METADATA BATCH] ❌ Error procesando doc {doc_id}: {e}")
                failed += 1

        # Resumen final
        print(f"\n[METADATA BATCH] === RESUMEN ===")
        print(f"[METADATA BATCH] Total procesados: {processed}")
        print(f"[METADATA BATCH] Fallidos: {failed}")
        print(f"[METADATA BATCH] Tipos encontrados:")
        for doc_type, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            print(f"  - {doc_type}: {count}")

        return {
            "total_processed": processed,
            "total_failed": failed,
            "type_distribution": type_counts
        }
