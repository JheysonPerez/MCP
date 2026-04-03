from typing import List, Dict
import re

class ChunkService:
    def __init__(self, chunk_size: int = 800, overlap: int = 100):
        """
        Inicializa la estrategia de fragmentación.
        chunk_size: Cantidad de caracteres por chunk (aumentado de 500 a 800).
        overlap: Solapamiento entre chunks (aumentado de 50 a 100).
        """
        self.chunk_size = chunk_size
        self.overlap = overlap
        # Patrones para detectar encabezados/secciones
        self.header_patterns = [
            r'^[A-Z][A-Z\s]{3,}$',  # TODO MAYUSCULAS
            r'^\d+[\.\)]\s+[A-Z]',  # 1. Título o 1) Título
            r'^(SECCI[ÓO]N|CAP[ÍI]TULO|ART[ÍI]CULO|PARTE)\s+\d+',  # SECCIÓN 1
            r'^[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,5}:',  # Título: subtítulo
        ]

    def detect_sections(self, text: str) -> List[Dict]:
        """
        Detecta secciones/encabezados en el texto para agregar contexto.
        Retorna lista de dicts con: start, end, title, content
        """
        lines = text.split('\n')
        sections = []
        current_title = "DOCUMENTO"
        current_content = []
        
        for i, line in enumerate(lines):
            is_header = False
            clean_line = line.strip()
            
            # Verificar patrones de encabezado
            for pattern in self.header_patterns:
                if re.match(pattern, clean_line, re.IGNORECASE):
                    # Guardar sección anterior
                    if current_content:
                        sections.append({
                            'title': current_title,
                            'content': '\n'.join(current_content),
                            'start_idx': len('\n'.join([s['content'] for s in sections]))
                        })
                    current_title = clean_line
                    current_content = []
                    is_header = True
                    break
            
            if not is_header and clean_line:
                current_content.append(clean_line)
        
        # Agregar última sección
        if current_content:
            sections.append({
                'title': current_title,
                'content': '\n'.join(current_content)
            })
        
        # Si no se detectaron secciones, crear una sola
        if not sections:
            sections = [{'title': 'DOCUMENTO', 'content': text}]
        
        return sections

    def _is_form_document(self, text: str) -> bool:
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        if not lines: return False
        
        form_count = 0
        for l in lines:
            # Patrón 1: "Clave : Valor" o "Clave: Valor"
            if re.match(r'^[^:]{2,40}:\s*\S+', l):
                form_count += 1
            # Patrón 2: "Clave :" (valor en línea siguiente)
            elif re.match(r'^[^:]{2,40}:\s*$', l):
                form_count += 1
            # Patrón 3: línea corta que parece un valor de campo (< 40 chars, no es párrafo)
            elif len(l) < 40 and not l.endswith('.') and not l.startswith('•'):
                form_count += 1
        
        ratio = form_count / len(lines)
        print(f"[CHUNK] Ratio formulario: {ratio:.2f} ({form_count}/{len(lines)} líneas)")
        return ratio > 0.30  # threshold: 30% de líneas parecen campos de formulario

    def _chunk_form(self, text: str, document_id: str) -> List[Dict]:
        """
        Para documentos tipo formulario: agrupa campos en chunks de 3-4 líneas con overlap de 1.
        Esto preserva mejor el contexto semántico de campos como DNI, fechas, etc.
        """
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        chunks = []
        group_size = 4  # campos por chunk
        overlap = 1

        for i in range(0, len(lines), group_size - overlap):
            group = lines[i:i + group_size]
            if group:
                chunk_text = '\n'.join(group)
                chunks.append({
                    "document_id": document_id,
                    "chunk_index": len(chunks),
                    "text": f"## DATOS DEL DOCUMENTO\n{chunk_text}",
                    "section": "DATOS DEL DOCUMENTO"
                })
        return chunks

    def chunk_text(self, text: str, document_id: str) -> List[Dict]:
        """
        Divide el texto en chunks con contexto de sección.
        Cada chunk incluye el título de su sección padre.
        Detecta automáticamente documentos tipo formulario para usar estrategia específica.
        """
        # Detectar si es documento tipo formulario (estructura Clave: Valor)
        if self._is_form_document(text):
            print(f"[CHUNK] Documento tipo formulario detectado, usando chunk por campos")
            return self._chunk_form(text, document_id)
        
        chunks = []
        sections = self.detect_sections(text)
        chunk_index = 0
        
        for section in sections:
            section_title = section['title']
            section_content = section['content']
            text_length = len(section_content)
            start = 0
            
            while start < text_length:
                end = min(start + self.chunk_size, text_length)
                
                # Retroceder al último espacio para no partir palabras
                if end < text_length and section_content[end] != ' ' and ' ' in section_content[start:end]:
                    end = section_content.rfind(' ', start, end)
                
                chunk_slice = section_content[start:end].strip()
                
                if chunk_slice:
                    # Agregar contexto de sección al chunk
                    context_chunk = f"## {section_title}\n{chunk_slice}"
                    chunks.append({
                        "document_id": document_id,
                        "chunk_index": chunk_index,
                        "text": context_chunk,
                        "section": section_title
                    })
                    chunk_index += 1
                
                if end == text_length:
                    break
                
                # Overlap con manejo de palabras
                next_start = max(end - self.overlap, start + 1)
                if next_start < text_length and section_content[next_start - 1] != ' ':
                    next_space_idx = section_content.find(' ', next_start)
                    if next_space_idx != -1 and next_space_idx < end:
                        next_start = next_space_idx + 1
                
                start = next_start
        
        return chunks
