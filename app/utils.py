"""
Utilidades para el procesamiento de texto y markdown en la aplicación Flask.
"""

import markdown
import bleach
import re

# Tags HTML permitidos en las respuestas RAG
ALLOWED_TAGS = [
    'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'ul', 'ol', 'li',
    'strong', 'em', 'b', 'i',
    'code', 'pre', 'blockquote',
    'a', 'br', 'hr', 'span', 'div'
]

# Atributos permitidos por tag
ALLOWED_ATTRIBUTES = {
    'a': ['href', 'rel', 'target'],
    'code': ['class'],
    'pre': ['class'],
    'span': ['class'],
    'div': ['class'],
}

# Protocolos permitidos para URLs
ALLOWED_PROTOCOLS = ['http', 'https', 'mailto']


def _preprocess_markdown(text: str) -> str:
    """
    Pre-procesa texto markdown para normalizar formato.
    
    Problema: El LLM genera headers como "texto. #### Header" donde los ####
    no están al inicio de línea, entonces el parser markdown no los reconoce.
    
    Solución: Encontrar todos los headers markdown (## a ######) e insertar
    saltos de línea antes de cada uno que no esté al inicio de línea.
    """
    if not text:
        return text
    
    # Encontrar todas las posiciones de headers markdown (##, ###, ####, etc.)
    # seguidos de espacio y texto
    header_pattern = re.compile(r'#{2,6}\s+\w')
    
    result = []
    last_end = 0
    
    for match in header_pattern.finditer(text):
        start = match.start()
        
        # Verificar si el header está al inicio de línea o después de \n
        if start > 0:
            char_before = text[start - 1]
            # Si el caracter anterior no es \n, necesitamos insertar saltos
            if char_before != '\n':
                # Agregar texto acumulado
                result.append(text[last_end:start])
                # Insertar saltos de línea antes del header
                result.append('\n\n')
                last_end = start
    
    # Agregar el resto del texto
    result.append(text[last_end:])
    
    # Unir todo
    text = ''.join(result)
    
    # Limpiar múltiples saltos de línea consecutivos (más de 2)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text


def render_markdown_safe(text: str) -> str:
    """
    Convierte texto markdown a HTML seguro para renderizar.
    
    Args:
        text: Texto en formato markdown
        
    Returns:
        HTML sanitizado listo para usar con |safe en templates
    """
    if not text:
        return ""
    
    # Pre-procesar para normalizar headers inline
    text = _preprocess_markdown(text)
    
    # Convertir markdown a HTML
    md = markdown.Markdown(
        extensions=[
            'fenced_code',  # Soporte para ```code blocks```
            'nl2br',        # Convertir newlines a <br>
            'tables',       # Tablas markdown
        ]
    )
    html = md.convert(text)
    md.reset()  # Limpiar estado para siguiente uso
    
    # Sanitizar HTML para prevenir XSS
    safe_html = bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True  # Eliminar tags no permitidos en lugar de escaparlos
    )
    
    # Agregar rel="nofollow noopener" a todos los links por seguridad
    safe_html = safe_html.replace('<a href=', '<a rel="nofollow noopener" target="_blank" href=')
    
    return safe_html


def process_rag_response(response_text: str) -> dict:
    """
    Procesa una respuesta completa del RAG para mostrar en la UI.
    
    Args:
        response_text: Texto de respuesta del LLM (puede contener markdown)
        
    Returns:
        dict con:
            - html: HTML sanitizado para mostrar
            - original: Texto original sin procesar
    """
    return {
        'html': render_markdown_safe(response_text),
        'original': response_text
    }
