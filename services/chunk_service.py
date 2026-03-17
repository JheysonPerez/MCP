from typing import List, Dict

class ChunkService:
    def __init__(self, chunk_size: int = 500, overlap: int = 50):
        """
        Inicializa la estrategia de fragmentación.
        chunk_size: Cantidad de caracteres por chunk.
        overlap: Solapamiento entre chunks para no perder contexto continuo.
        """
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_text(self, text: str, document_id: str) -> List[Dict]:
        """
        Divide el texto extraído en fragmentos más pequeños y estructurados.
        
        Devuelve una lista de chunks, donde cada uno es un diccionario con:
        - document_id
        - chunk_index
        - text
        """
        chunks = []
        # Normalizar espacios para limpieza de saltos de línea irregulares
        text = " ".join(text.split())
        text_length = len(text)
        
        start = 0
        chunk_index = 0

        while start < text_length:
            # Límite proyectado
            end = min(start + self.chunk_size, text_length)
            
            # Retroceder al último espacio en este rango si estamos cortando en medio de texto,
            # para no partir palabras a la mitad.
            if end < text_length and text[end] != ' ' and ' ' in text[start:end]:
                end = text.rfind(' ', start, end)
                
            chunk_slice = text[start:end].strip()
            
            if chunk_slice: # Solo agregar si tiene texto real
                chunks.append({
                    "document_id": document_id,
                    "chunk_index": chunk_index,
                    "text": chunk_slice
                })
                chunk_index += 1
                
            # Si llegamos al final del string original, detenemos el loop.
            if end == text_length:
                break
            
            # Recalcular siguiente inicio usando el overlap. Intentar que empiece al inicio de una palabra.
            next_start = max(end - self.overlap, start + 1)
            
            # Si cortamos en medio de una palabra izquierda, avanzar al siguiente bloque espaciado.
            if next_start < text_length and text[next_start - 1] != ' ':
                next_space_idx = text.find(' ', next_start)
                if next_space_idx != -1 and next_space_idx < end:
                    next_start = next_space_idx + 1
                    
            start = next_start
            
        return chunks
