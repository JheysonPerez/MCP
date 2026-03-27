import os
import shutil
import mimetypes
from pathlib import Path

# Dependencias para extraer texto
from pypdf import PdfReader
import docx

try:
    import pytesseract
    from pdf2image import convert_from_path
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

class DocumentService:
    def __init__(self, upload_dir="data/uploads", processed_dir="data/processed", persistence_service=None):
        self.upload_dir = Path(upload_dir)
        self.processed_dir = Path(processed_dir)
        self.persistence = persistence_service
        
        # Asegurar que los directorios existen
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    def save_file(self, file_path: str | Path, filename: str = None) -> Path:
        """
        Copia un archivo externo hacia el directorio de uploads local.
        """
        source_path = Path(file_path)
        if not source_path.exists():
            raise FileNotFoundError(f"El archivo fuente no existe: {source_path}")
            
        if filename is None:
            filename = source_path.name
            
        dest_path = self.upload_dir / filename
        shutil.copy2(source_path, dest_path)
        
        return dest_path

    def detect_file_type(self, file_path: str | Path) -> str:
        """
        Detecta la extensión/tipo del archivo para decidir cómo extraer el texto.
        Devuelve la extensión en minúsculas (ej: '.pdf', '.docx', '.txt').
        """
        path = Path(file_path)
        ext = path.suffix.lower()
        if not ext:
            # Intento de fallback adivinando el mimetype si no hay extensión
            mime_type, _ = mimetypes.guess_type(path)
            if mime_type == 'application/pdf':
                return '.pdf'
            elif mime_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
                return '.docx'
            elif mime_type == 'text/plain':
                return '.txt'
            elif mime_type in ('image/jpeg', 'image/jpg'):
                return '.jpg'
            elif mime_type == 'image/png':
                return '.png'
        return ext

    def extract_text(self, file_path: str | Path) -> str:
        """
        Extrae el texto del archivo apoyándose en su extensión/tipo.
        """
        ext = self.detect_file_type(file_path)
        path_str = str(file_path)

        if ext == '.txt':
            return self._extract_from_txt(path_str)
        elif ext == '.pdf':
            return self._extract_from_pdf(path_str)
        elif ext == '.docx':
            return self._extract_from_docx(path_str)
        elif ext in ('.jpg', '.jpeg', '.png'):
            return self._extract_from_image(path_str)
        else:
            raise ValueError(f"Formato de archivo no soportado: {ext}")

    def _extract_from_txt(self, file_path: str) -> str:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    def _extract_from_pdf(self, file_path: str) -> str:
        """
        Extracción en dos fases:
        Fase 1: pypdf para PDFs con texto embebido (rápido)
        Fase 2: OCR con Tesseract si el texto extraído es insuficiente
        """
        text_content = []
        reader = PdfReader(file_path)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_content.append(page_text)
        
        extracted = "\n".join(text_content).strip()
        
        # Si hay texto suficiente, retornar directo
        if len(extracted) > 100:
            return extracted
        
        # Fase 2: activar OCR
        if not OCR_AVAILABLE:
            print(f"[WARN] PDF sin texto y OCR no disponible: {file_path}")
            return extracted
        
        print(f"[OCR] PDF sin texto embebido, activando Tesseract: {file_path}")
        try:
            pages = convert_from_path(file_path, dpi=300)
            ocr_text = []
            for i, page_img in enumerate(pages):
                text = pytesseract.image_to_string(
                    page_img,
                    lang="spa+eng",
                    config="--psm 1"
                )
                if text.strip():
                    ocr_text.append(text)
                print(f"[OCR] Página {i+1}/{len(pages)} procesada")
            
            result = "\n".join(ocr_text).strip()
            if result:
                print(f"[OCR] Extracción exitosa: {len(result)} caracteres")
            else:
                print(f"[OCR] Sin texto detectado después de OCR")
            return result
            
        except Exception as e:
            print(f"[OCR] Error en Tesseract: {e}")
            return extracted

    def _extract_from_docx(self, file_path: str) -> str:
        doc = docx.Document(file_path)
        return "\n".join([para.text for para in doc.paragraphs])

    def _extract_from_image(self, file_path: str) -> str:
        """
        Extrae texto de una imagen JPG o PNG usando Tesseract OCR.
        """
        if not OCR_AVAILABLE:
            raise ValueError(
                "OCR no disponible. Instala pytesseract y Pillow."
            )
        try:
            from PIL import Image
            print(f"[OCR] Procesando imagen: {file_path}")
            img = Image.open(file_path)
            text = pytesseract.image_to_string(
                img,
                lang="spa+eng",
                config="--psm 1"
            )
            result = text.strip()
            if result:
                print(f"[OCR] Imagen procesada: {len(result)} caracteres")
            else:
                print(f"[OCR] Sin texto detectado en imagen")
            return result
        except Exception as e:
            raise ValueError(f"Error procesando imagen con OCR: {e}")

    def process_and_save(self, file_path: str | Path) -> tuple[Path, Path, int]:
        """
        Realiza el flujo completo:
        1. Guarda en uploads
        2. Registra en DB como 'pending'
        3. Extrae texto y guarda en processed
        4. Actualiza DB como 'completed' o 'failed'
        Retorna (ruta_subida, ruta_procesada, doc_id)
        """
        import uuid
        
        # 1. Guardar archivo original
        upload_path = self.save_file(file_path)
        original_name = upload_path.name
        
        doc_id = None
        processed_path = None
        
        try:
            # 2. Pre-registro en DB (estado: pending por defecto en register_document)
            if self.persistence:
                user_id = self.persistence.create_or_get_user("sistema", "sistema@local.epiis")
                doc_id = self.persistence.register_document(
                    filename=original_name,
                    original_path=str(upload_path),
                    processed_path="", # Se llenará en el siguiente paso
                    user_id=user_id
                )
            
            # 3. Extraer texto
            extracted_text = self.extract_text(upload_path)
            
            # 4. Generar nombre y ruta procesada
            safe_uuid = uuid.uuid4().hex[:8]
            if original_name.lower().endswith('.txt'):
                processed_name = f"{safe_uuid}_{original_name}"
            else:
                processed_name = f"{safe_uuid}_{original_name}.txt"
                
            processed_path = self.processed_dir / processed_name
            
            # 5. Guardar texto procesado
            processed_path = self.processed_dir / processed_name
            absolute_processed_path = str(processed_path.resolve())
            
            with open(processed_path, "w", encoding="utf-8") as f:
                f.write(extracted_text)
            
            # 6. Actualizar éxito en DB con la RUTA REAL ABSOLUTA
            if self.persistence and doc_id:
                self.persistence.update_document_status(
                    doc_id, 
                    processing_status='completed',
                    processed_path=absolute_processed_path
                )
                
            return upload_path, Path(absolute_processed_path), doc_id

        except Exception as e:
            error_msg = f"Error procesando {original_name}: {str(e)}"
            print(f"[ERROR] {error_msg}")
            
            # 7. Registrar fallo en DB
            if self.persistence and doc_id:
                self.persistence.update_document_status(
                    doc_id, 
                    processing_status='failed',
                    error_log=error_msg
                )
            raise
