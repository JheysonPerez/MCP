"""
Servicio de Re-ranking para mejorar la calidad de retrieval.
Usa cross-encoder para re-ordenar chunks por relevancia query-específica.
"""
from typing import List, Dict
import requests
import os


class RerankService:
    """
    Servicio de re-ranking para mejorar resultados de búsqueda vectorial.
    
    Implementa:
    - Cross-encoder para scoring query-documento
    - Re-ordenamiento de top-k resultados
    - Fallback a scores originales si el servicio falla
    """
    
    def __init__(self, base_url: str = None, model: str = "llama3.2"):
        """
        Inicializa el servicio de re-ranking.
        
        Args:
            base_url: URL de Ollama (default: localhost:11434)
            model: Modelo a usar para re-ranking (default: llama3.2)
        """
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.model = model
        
    def rerank(self, query: str, chunks: List[Dict], top_k: int = 5) -> List[Dict]:
        """
        Re-ordena chunks por relevancia usando scoring semántico.
        
        Args:
            query: La consulta del usuario
            chunks: Lista de chunks con 'text' y metadata
            top_k: Cuántos chunks retornar después de re-ranking
            
        Returns:
            Lista re-ordenada de chunks más relevantes
        """
        if not chunks or len(chunks) <= 2:
            return chunks[:top_k]
        
        # Scoring por relevance usando Ollama
        scored_chunks = []
        
        for chunk in chunks:
            score = self._score_relevance(query, chunk.get('text', ''))
            scored_chunks.append({
                **chunk,
                'rerank_score': score,
                # Combinar score original con rerank
                'final_score': (chunk.get('score', 0.5) * 0.3) + (score * 0.7)
            })
        
        # Ordenar por final_score descendente
        scored_chunks.sort(key=lambda x: x['final_score'], reverse=True)
        
        return scored_chunks[:top_k]
    
    def _score_relevance(self, query: str, text: str) -> float:
        """
        Calcula score de relevancia entre query y texto.
        
        Usa una escala 0-1 basada en:
        - Presencia de términos de la query en el texto
        - Longitud de overlap semántico
        - Similitud de entidades (nombres, números)
        """
        try:
            # Normalizar
            query_lower = query.lower()
            text_lower = text.lower()
            
            # Diccionario de sinónimos para documentos institucionales peruanos
            SYNONYMS = {
                'dni': ['n° de documento', 'numero de documento', 'documento de identidad', 'n de documento'],
                'nombre': ['nombres', 'apellidos', 'titular'],
                'fecha nacimiento': ['fecha de nacimiento'],
                'vencimiento': ['fecha de caducidad', 'caducidad', 'vigencia'],
                'emision': ['fecha de emision', 'emitido'],
                'domicilio': ['direccion', 'domicilio'],
                'nacionalidad': ['pais', 'nacionalidad'],
            }

            # Expandir query con sinónimos antes del scoring
            expanded_query = query_lower
            for term, syns in SYNONYMS.items():
                if term in query_lower:
                    expanded_query += ' ' + ' '.join(syns)

            # Expandir texto con sinónimos inversos  
            expanded_text = text_lower
            for term, syns in SYNONYMS.items():
                for syn in syns:
                    if syn in text_lower:
                        expanded_text += ' ' + term

            # Usar expanded_query y expanded_text para el cálculo
            query_terms = set(expanded_query.split())
            text_terms = set(expanded_text.split())
            term_overlap = len(query_terms & text_terms) / max(len(query_terms), 1)
            
            # 2. Substring match (peso: 30%)
            # Buscar frases completas de la query
            substring_score = 0.0
            if query_lower in text_lower:
                substring_score = 1.0
            else:
                # Buscar palabras individuales importantes
                important_words = [w for w in query_terms if len(w) > 3]
                matches = sum(1 for w in important_words if w in text_lower)
                substring_score = matches / max(len(important_words), 1)
            
            # 3. Entity match (nombres propios, números) (peso: 30%)
            import re
            # Extraer números (DNI, fechas, etc.)
            query_numbers = set(re.findall(r'\d{4,}', query))
            text_numbers = set(re.findall(r'\d{4,}', text))
            number_match = len(query_numbers & text_numbers) / max(len(query_numbers), 1)
            
            # Extraer palabras en mayúsculas (nombres propios)
            query_names = set(re.findall(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+', query))
            text_names = set(re.findall(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+', text))
            name_match = len(query_names & text_names) / max(len(query_names), 1)
            
            entity_score = (number_match + name_match) / 2
            
            # Score final ponderado
            final_score = (term_overlap * 0.4) + (substring_score * 0.3) + (entity_score * 0.3)
            
            return min(final_score, 1.0)
            
        except Exception as e:
            print(f"[RERANK] Error en scoring: {e}")
            return 0.5  # Score neutral si falla
    
    def rerank_with_llm(self, query: str, chunks: List[Dict], top_k: int = 5) -> List[Dict]:
        """
        Versión avanzada usando LLM para re-ranking.
        Más lento pero más preciso.
        """
        if not chunks or len(chunks) <= 2:
            return chunks[:top_k]
        
        try:
            # Preparar prompt para LLM
            chunks_text = "\n\n".join([
                f"[{i}] {c.get('text', '')[:200]}..." 
                for i, c in enumerate(chunks[:10])
            ])
            
            prompt = f"""Eres un evaluador de relevancia. Para la pregunta "{query}", ordena estos documentos de más a menos relevante (1-10).

Documentos:
{chunks_text}

Responde SOLO con los índices ordenados, ejemplo: "3,0,1,2,4" """

            # Llamar a Ollama
            url = f"{self.base_url}/api/generate"
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.1}
            }
            
            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()
            
            # Parsear respuesta (índices separados por coma)
            ranking_str = result.get("response", "").strip()
            indices = [int(x.strip()) for x in ranking_str.split(",") if x.strip().isdigit()]
            
            # Re-ordenar chunks según ranking del LLM
            reranked = []
            for idx in indices[:top_k]:
                if 0 <= idx < len(chunks):
                    chunk = chunks[idx].copy()
                    chunk['rerank_score'] = 1.0 - (indices.index(idx) * 0.1)
                    reranked.append(chunk)
            
            # Agregar chunks no mencionados al final
            mentioned = set(indices)
            for i, chunk in enumerate(chunks):
                if i not in mentioned:
                    chunk_copy = chunk.copy()
                    chunk_copy['rerank_score'] = 0.3
                    reranked.append(chunk_copy)
            
            return reranked[:top_k]
            
        except Exception as e:
            print(f"[RERANK] Error en LLM reranking: {e}")
            # Fallback a método simple
            return self.rerank(query, chunks, top_k)


def create_rerank_service() -> RerankService:
    """Factory function para crear instancia del servicio."""
    return RerankService()
