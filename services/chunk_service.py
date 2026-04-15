from typing import List, Dict, Optional, Tuple
import re


class ChunkService:
    def __init__(self, chunk_size: int = 800, overlap: int = 100):
        """
        Fragmentador inteligente con:
        - Detección de headers ampliada (markdown, numerados, romanos, negrita, etc.)
        - Contexto jerárquico con breadcrumbs (Capítulo > Sección > Subsección)
        - Respeto de párrafos, listas y tablas como unidades
        - Metadatos de posición (chunk N de M, porcentaje)
        - Detección de formularios mejorada
        """
        self.chunk_size = chunk_size
        self.overlap = overlap

        # ── Patrones de headers ordenados de mayor a menor jerarquía ──────────
        # Cada tupla: (nivel, regex)
        self.header_patterns: List[Tuple[int, str]] = [
            # Nivel 1 – títulos principales
            (1, r'^#{1}\s+\S'),                              # # Título (markdown)
            (1, r'^[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s]{4,}$'),        # TODO EN MAYÚSCULAS
            (1, r'^(CAP[IÍ]TULO|PARTE|TÍTULO|TITLE)\s+[\dIVXivx]+', ),
            # Nivel 2 – secciones
            (2, r'^#{2}\s+\S'),                              # ## Sección
            (2, r'^(SECCI[ÓO]N|SECCIÓN|SECTION)\s+[\d\.]+'),
            (2, r'^\d+\.\s+[A-ZÁÉÍÓÚÑ]'),                   # 1. Sección
            (2, r'^[IVXLC]+\.\s+[A-ZÁÉÍÓÚÑ]'),              # I. Sección (romano)
            (2, r'^[A-Z]\.\s+[A-ZÁÉÍÓÚÑ]'),                  # A. Sección
            # Nivel 3 – subsecciones
            (3, r'^#{3,}\s+\S'),                             # ### Subsección
            (3, r'^\d+\.\d+\s+\S'),                          # 1.1 Subsección
            (3, r'^\d+\.\d+\.\d+\s+\S'),                     # 1.1.1 Sub-sub
            (3, r'^(ART[IÍ]CULO|ARTÍCULO|INCISO)\s+\d+'),
            (3, r'^\*\*[^*]{3,60}\*\*\s*$'),                 # **Título en negrita**
            (3, r'^[A-ZÁÉÍÓÚÑa-záéíóúñ][^:]{2,50}:\s*$'),  # Clave: (valor en siguiente línea)
        ]

        # Pre-compilar los patrones
        self._compiled = [
            (lvl, re.compile(pat, re.IGNORECASE))
            for lvl, pat in self.header_patterns
        ]

    # ──────────────────────────────────────────────────────────────────────────
    # DETECCIÓN DE TIPO DE DOCUMENTO
    # ──────────────────────────────────────────────────────────────────────────

    def _is_form_document(self, text: str) -> bool:
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        if not lines:
            return False

        form_count = 0
        for line in lines:
            if re.match(r'^[^:]{2,50}:\s*\S', line):        # Clave: Valor
                form_count += 1
            elif re.match(r'^[^:]{2,50}:\s*$', line):        # Clave:
                form_count += 1
            elif len(line) < 40 and not line.endswith('.') and not line.startswith('•'):
                form_count += 1

        ratio = form_count / len(lines)
        print(f"[CHUNK] Ratio formulario: {ratio:.2f} ({form_count}/{len(lines)} líneas)")
        return ratio > 0.30

    def _is_table_line(self, line: str) -> bool:
        """Detecta líneas que forman parte de una tabla markdown o ascii."""
        return bool(re.match(r'^\|.+\|', line) or re.match(r'^[\+\-]{3,}', line))

    def _is_list_line(self, line: str) -> bool:
        """Detecta ítems de lista (bullet o numerada)."""
        return bool(re.match(r'^[\-\*\•]\s+', line) or re.match(r'^\d+[\.\)]\s+', line))

    # ──────────────────────────────────────────────────────────────────────────
    # DETECCIÓN DE HEADERS Y CONSTRUCCIÓN DE JERARQUÍA
    # ──────────────────────────────────────────────────────────────────────────

    def _detect_header_level(self, line: str) -> Optional[Tuple[int, str]]:
        """
        Devuelve (nivel, texto_limpio) si la línea es un header, o None.
        """
        clean = line.strip()
        if not clean or len(clean) > 120:
            return None
        for level, pattern in self._compiled:
            if pattern.match(clean):
                # Limpiar marcadores markdown y espacios extra
                title = re.sub(r'^#+\s*', '', clean)
                title = re.sub(r'^\*\*(.+)\*\*$', r'\1', title)
                return (level, title.strip())
        return None

    def _build_breadcrumb(self, hierarchy: Dict[int, str]) -> str:
        """
        Construye el breadcrumb jerárquico:
        'CAPÍTULO 1: Introducción > SECCIÓN 1.2: Requisitos > Subsección'
        """
        parts = [hierarchy[lvl] for lvl in sorted(hierarchy) if hierarchy.get(lvl)]
        return ' > '.join(parts) if parts else 'DOCUMENTO'

    # ──────────────────────────────────────────────────────────────────────────
    # AGRUPACIÓN EN BLOQUES LÓGICOS (párrafos / listas / tablas)
    # ──────────────────────────────────────────────────────────────────────────

    def _split_into_blocks(self, text: str) -> List[Dict]:
        """
        Divide el texto en bloques semánticos:
          - header: encabezado de sección
          - table:  tabla completa
          - list:   lista completa
          - paragraph: párrafo de texto normal
        Nunca rompe un bloque por la mitad.
        """
        lines = text.split('\n')
        blocks: List[Dict] = []
        buffer: List[str] = []
        current_type: str = 'paragraph'

        def flush(buf: List[str], btype: str):
            content = '\n'.join(buf).strip()
            if content:
                blocks.append({'type': btype, 'content': content})

        for raw_line in lines:
            line = raw_line.rstrip()

            # ¿Es un header?
            header_info = self._detect_header_level(line)
            if header_info:
                flush(buffer, current_type)
                buffer = []
                level, title = header_info
                blocks.append({'type': 'header', 'level': level, 'content': title, 'raw': line})
                current_type = 'paragraph'
                continue

            # ¿Es línea de tabla?
            if self._is_table_line(line):
                if current_type != 'table':
                    flush(buffer, current_type)
                    buffer = []
                    current_type = 'table'
                buffer.append(line)
                continue

            # ¿Es ítem de lista?
            if self._is_list_line(line):
                if current_type != 'list':
                    flush(buffer, current_type)
                    buffer = []
                    current_type = 'list'
                buffer.append(line)
                continue

            # Línea vacía → cierra el bloque actual
            if not line.strip():
                if current_type in ('table', 'list'):
                    flush(buffer, current_type)
                    buffer = []
                    current_type = 'paragraph'
                elif buffer:
                    flush(buffer, 'paragraph')
                    buffer = []
                continue

            # Línea de texto normal
            if current_type in ('table', 'list'):
                flush(buffer, current_type)
                buffer = []
                current_type = 'paragraph'
            buffer.append(line)

        flush(buffer, current_type)
        return blocks

    # ──────────────────────────────────────────────────────────────────────────
    # CHUNKING DE FORMULARIOS
    # ──────────────────────────────────────────────────────────────────────────

    def _chunk_form(self, text: str, document_id: str) -> List[Dict]:
        """
        Para documentos tipo formulario: agrupa campos en chunks de 4 líneas con overlap=1.
        """
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        chunks: List[Dict] = []
        group_size = 4
        ov = 1
        total = len(chunks)  # se actualizará al final

        i = 0
        while i < len(lines):
            group = lines[i: i + group_size]
            if group:
                chunk_text = '\n'.join(group)
                chunks.append({
                    "document_id": document_id,
                    "chunk_index": len(chunks),
                    "text": f"## DATOS DEL DOCUMENTO\n{chunk_text}",
                    "section": "DATOS DEL DOCUMENTO",
                    "breadcrumb": "DATOS DEL DOCUMENTO",
                    "position_pct": 0,  # se rellena al final
                })
            i += group_size - ov

        # Rellenar metadatos de posición
        total = len(chunks)
        for idx, ch in enumerate(chunks):
            ch["chunk_total"] = total
            ch["position_pct"] = round((idx / max(total - 1, 1)) * 100)
            ch["text"] = (
                f"{ch['text']}\n\n"
                f"[Fragmento {idx + 1} de {total} · Posición: {ch['position_pct']}%]"
            )

        return chunks

    # ──────────────────────────────────────────────────────────────────────────
    # CHUNKING PRINCIPAL
    # ──────────────────────────────────────────────────────────────────────────

    def chunk_text(self, text: str, document_id: str) -> List[Dict]:
        """
        Pipeline principal:
        1. Detecta si es formulario → estrategia específica.
        2. Divide el texto en bloques semánticos (headers, tablas, listas, párrafos).
        3. Acumula bloques respetando chunk_size; nunca parte un bloque por la mitad.
        4. Agrega breadcrumb jerárquico y metadatos de posición a cada chunk.
        """
        if self._is_form_document(text):
            print("[CHUNK] Documento tipo formulario detectado.")
            return self._chunk_form(text, document_id)

        blocks = self._split_into_blocks(text)
        chunks: List[Dict] = []

        # Jerarquía actual: {nivel: título}
        hierarchy: Dict[int, str] = {}
        current_section = "DOCUMENTO"

        # Buffer de acumulación
        buffer_blocks: List[str] = []
        buffer_len: int = 0

        def flush_buffer(buf: List[str], section: str, breadcrumb: str) -> Optional[Dict]:
            content = '\n\n'.join(buf).strip()
            if not content:
                return None
            header_line = f"## {breadcrumb}\n"
            return {
                "document_id": document_id,
                "chunk_index": len(chunks),
                "text": header_line + content,
                "section": section,
                "breadcrumb": breadcrumb,
            }

        for block in blocks:
            # ── Bloque header: actualiza jerarquía, no genera chunk por sí solo ──
            if block['type'] == 'header':
                level = block.get('level', 2)
                title = block['content']

                # Actualizar jerarquía: limpiar niveles iguales o inferiores
                for lvl in list(hierarchy.keys()):
                    if lvl >= level:
                        del hierarchy[lvl]
                hierarchy[level] = title
                current_section = title
                continue

            # ── Calcular breadcrumb actual ────────────────────────────────────
            breadcrumb = self._build_breadcrumb(hierarchy) if hierarchy else "DOCUMENTO"

            block_text = block['content']
            block_len = len(block_text)

            # ── Si el bloque solo (tabla/lista) supera chunk_size, se divide ──
            if block['type'] in ('table', 'list') and block_len > self.chunk_size:
                # Primero volcamos el buffer existente
                if buffer_blocks:
                    ch = flush_buffer(buffer_blocks, current_section, breadcrumb)
                    if ch:
                        chunks.append(ch)
                    buffer_blocks = []
                    buffer_len = 0

                # Dividir el bloque grande en partes respetando líneas
                sub_lines = block_text.split('\n')
                sub_buf: List[str] = []
                sub_len = 0
                for sl in sub_lines:
                    if sub_len + len(sl) + 1 > self.chunk_size and sub_buf:
                        ch = flush_buffer(['\n'.join(sub_buf)], current_section, breadcrumb)
                        if ch:
                            chunks.append(ch)
                        # Overlap: últimas líneas de overlap caracteres
                        overlap_lines: List[str] = []
                        acc = 0
                        for prev in reversed(sub_buf):
                            acc += len(prev) + 1
                            if acc <= self.overlap:
                                overlap_lines.insert(0, prev)
                            else:
                                break
                        sub_buf = overlap_lines
                        sub_len = sum(len(x) + 1 for x in sub_buf)
                    sub_buf.append(sl)
                    sub_len += len(sl) + 1

                if sub_buf:
                    ch = flush_buffer(['\n'.join(sub_buf)], current_section, breadcrumb)
                    if ch:
                        chunks.append(ch)
                continue

            # ── ¿Cabe en el buffer actual? ────────────────────────────────────
            separator_len = 2 if buffer_blocks else 0
            if buffer_len + separator_len + block_len > self.chunk_size and buffer_blocks:
                # Volcar buffer
                ch = flush_buffer(buffer_blocks, current_section, breadcrumb)
                if ch:
                    chunks.append(ch)

                # Overlap: conservar el último bloque si cabe
                last = buffer_blocks[-1]
                if len(last) <= self.overlap:
                    buffer_blocks = [last]
                    buffer_len = len(last)
                else:
                    # Conservar los últimos `overlap` caracteres del último bloque
                    snippet = last[-self.overlap:]
                    # Avanzar al primer espacio para no cortar palabra
                    space_idx = snippet.find(' ')
                    snippet = snippet[space_idx + 1:] if space_idx != -1 else snippet
                    buffer_blocks = [snippet]
                    buffer_len = len(snippet)

            buffer_blocks.append(block_text)
            buffer_len += block_len + separator_len

        # Volcar lo que quedó en el buffer
        breadcrumb = self._build_breadcrumb(hierarchy) if hierarchy else "DOCUMENTO"
        if buffer_blocks:
            ch = flush_buffer(buffer_blocks, current_section, breadcrumb)
            if ch:
                chunks.append(ch)

        # ── Post-proceso: agregar metadatos de posición ───────────────────────
        total = len(chunks)
        for idx, ch in enumerate(chunks):
            ch["chunk_index"] = idx
            ch["chunk_total"] = total
            pct = round((idx / max(total - 1, 1)) * 100)
            ch["position_pct"] = pct
            # Inyectar metadatos al final del texto del chunk
            ch["text"] += f"\n\n[Fragmento {idx + 1} de {total} · Posición: {pct}%]"

        print(f"[CHUNK] {total} chunks generados para documento {document_id}")
        return chunks