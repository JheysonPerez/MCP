"""
Servicio de búsqueda híbrida: combina vectorial semántica + keyword BM25
"""
from typing import List, Dict, Tuple
import math
import re
from collections import Counter


class HybridSearchService:
    """
    Implementa búsqueda híbrida para mejorar recall y precisión.
    
    Combina:
    - Vector search: captura significado semántico
    - BM25: captura coincidencias exactas de términos
    - Fusión RRF (Reciprocal Rank Fusion)
    """
    
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        """
        Args:
            k1: Parámetro de saturación BM25 (default: 1.5)
            b: Parámetro de normalización por longitud (default: 0.75)
        """
        self.k1 = k1
        self.b = b
        # IDF cache
        self.idf_cache = {}
        # Longitud promedio de documentos
        self.avgdl = None
        
    def calculate_bm25_scores(
        self, 
        query: str, 
        documents: List[Dict]
    ) -> List[Tuple[int, float]]:
        """
        Calcula scores BM25 para cada documento.
        
        Args:
            query: Texto de consulta
            documents: Lista de chunks con 'text'
            
        Returns:
            Lista de (índice, score_bm25) ordenada por score
        """
        if not documents:
            return []
        
        # Tokenizar query
        query_terms = self._tokenize(query)
        
        # Calcular estadísticas del corpus
        doc_lengths = [len(self._tokenize(d.get('text', ''))) for d in documents]
        self.avgdl = sum(doc_lengths) / len(doc_lengths) if doc_lengths else 1
        
        # Calcular IDF para cada término
        N = len(documents)
        idfs = {}
        for term in set(query_terms):
            df = sum(1 for d in documents if term in self._tokenize(d.get('text', '')))
            # IDF con smoothing
            idf = math.log((N - df + 0.5) / (df + 0.5) + 1.0)
            idfs[term] = idf
        
        # Calcular score BM25 para cada documento
        scores = []
        for idx, doc in enumerate(documents):
            doc_text = doc.get('text', '')
            doc_terms = self._tokenize(doc_text)
            doc_len = len(doc_terms)
            
            score = 0.0
            term_freqs = Counter(doc_terms)
            
            for term in query_terms:
                if term in term_freqs:
                    f = term_freqs[term]  # frecuencia del término
                    idf = idfs.get(term, 0)
                    
                    # Fórmula BM25
                    numerator = f * (self.k1 + 1)
                    denominator = f + self.k1 * (1 - self.b + self.b * (doc_len / self.avgdl))
                    score += idf * (numerator / denominator)
            
            scores.append((idx, score))
        
        # Ordenar por score descendente
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores
    
    def reciprocal_rank_fusion(
        self,
        vector_results: List[Dict],
        keyword_results: List[Tuple[int, float]],
        k: int = 60,
        query_type: str = "general"
    ) -> List[Dict]:
        """
        Fusiona resultados vectoriales y keyword usando RRF con pesos dinámicos.
        
        RRF: score = Σ(w_i / (k + rank))
        
        Args:
            vector_results: Resultados de búsqueda vectorial
            keyword_results: Resultados BM25
            k: Constante de suavizado
            query_type: Tipo de query ("general" o "numeric")
        """
        # Determinar pesos según tipo de query
        if query_type == "numeric":
            w_vector = 0.3  # Menor peso a vectorial para números exactos
            w_keyword = 0.7   # Mayor peso a BM25
            print(f"[HYBRID] Query numérica detectada: pesos BM25={w_keyword}, Vector={w_vector}")
        else:
            w_vector = 0.5
            w_keyword = 0.5
        
        ranks = {}
        
        # Asignar ranks de búsqueda vectorial con peso
        for rank, doc in enumerate(vector_results):
            doc_id = doc.get('document_id', '')
            chunk_idx = doc.get('chunk_index', 0)
            key = f"{doc_id}_{chunk_idx}"
            
            if key not in ranks:
                ranks[key] = {'doc': doc, 'rrf_score': 0}
            # Aplicar peso vectorial
            ranks[key]['rrf_score'] += w_vector * (1.0 / (k + rank))
        
        # Asignar ranks de búsqueda keyword con peso
        for rank, (idx, _) in enumerate(keyword_results):
            if idx < len(vector_results):
                doc = vector_results[idx]
                doc_id = doc.get('document_id', '')
                chunk_idx = doc.get('chunk_index', 0)
                key = f"{doc_id}_{chunk_idx}"
                
                if key not in ranks:
                    ranks[key] = {'doc': doc, 'rrf_score': 0}
                # Aplicar peso keyword (BM25)
                ranks[key]['rrf_score'] += w_keyword * (1.0 / (k + rank))
        
        # Ordenar por RRF score
        sorted_results = sorted(ranks.values(), key=lambda x: x['rrf_score'], reverse=True)
        
        # Retornar documentos con score fusionado
        final_results = []
        for item in sorted_results:
            doc = item['doc'].copy()
            doc['hybrid_score'] = item['rrf_score']
            final_results.append(doc)
        
        return final_results
    
    def hybrid_search(
        self,
        query: str,
        vector_results: List[Dict],
        top_k: int = 6,
        query_type: str = "general"
    ) -> List[Dict]:
        """
        Ejecuta búsqueda híbrida con pesos dinámicos según tipo de query.
        
        Args:
            query: Consulta del usuario
            vector_results: Resultados pre-obtenidos de búsqueda vectorial
            top_k: Cuántos resultados retornar
            query_type: Tipo de query ("general" o "numeric")
            
        Returns:
            Resultados fusionados y ordenados
        """
        if not vector_results:
            return []
        
        # Calcular scores BM25 sobre los mismos documentos
        bm25_scores = self.calculate_bm25_scores(query, vector_results)
        
        # Fusionar con RRF usando pesos dinámicos
        fused_results = self.reciprocal_rank_fusion(
            vector_results, 
            bm25_scores, 
            query_type=query_type
        )
        
        return fused_results[:top_k]
    
    def _tokenize(self, text: str) -> List[str]:
        """
        Tokeniza texto para BM25.
        Normaliza y elimina stop words básicas, pero conserva números.
        """
        # Convertir a minúsculas
        text = text.lower()
        # Extraer palabras alfanuméricas (incluyendo números puros)
        tokens = re.findall(r'\b[a-z0-9]+\b', text)
        
        # Stop words básicas en español e inglés
        stop_words = {
            'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas', 'y', 'o', 'pero',
            'de', 'del', 'al', 'a', 'en', 'con', 'por', 'para', 'sobre', 'entre',
            'the', 'a', 'an', 'and', 'or', 'but', 'of', 'to', 'in', 'with', 'for',
            'que', 'es', 'son', 'fue', 'fueron', 'este', 'esta', 'estos', 'estas',
            'su', 'sus', 'se', 'ha', 'han', 'no', 'sí', 'si', 'como', 'más', 'mas'
        }
        
        # Filtrar stop words pero conservar tokens numéricos (longitud > 2 o puramente numéricos)
        result = []
        for t in tokens:
            if t.isdigit():
                # Siempre incluir números puros (DNI, códigos, etc.)
                result.append(t)
            elif t not in stop_words and len(t) > 2:
                result.append(t)
        
        return result


# Factory function
def create_hybrid_search_service() -> HybridSearchService:
    """Crea instancia del servicio de búsqueda híbrida."""
    return HybridSearchService()
