#!/usr/bin/env python3
"""
Script de procesamiento batch para extraer metadatos de documentos existentes.

Uso:
    python scripts/batch_extract_metadata.py

Procesa todos los documentos que:
- Están indexados (is_indexed = TRUE)
- No tienen metadatos extraídos (doc_type IS NULL)
- O fallaron previamente (metadata_extraction_failed = TRUE)

Muestra progreso en tiempo real y resumen final.
"""

import sys
from pathlib import Path

# Añadir raíz del proyecto al path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.connection import DatabaseConnection
from services.metadata_extraction_service import MetadataExtractionService
from services.persistence_service import PersistenceService


def main():
    print("=" * 70)
    print("EXTRACCIÓN BATCH DE METADATOS - EPIIS MCP-DOCS")
    print("=" * 70)
    print()

    # Inicializar servicios
    db = DatabaseConnection()
    persistence = PersistenceService(db)
    metadata_service = MetadataExtractionService()

    # Obtener documentos sin metadatos
    docs = persistence.get_documents_without_metadata()

    if not docs:
        print("✓ No hay documentos pendientes de extracción de metadatos.")
        print("  Todos los documentos indexados ya tienen metadatos extraídos.")
        return

    print(f"Encontrados {len(docs)} documentos para procesar:")
    print()

    # Contadores
    processed = 0
    failed = 0
    type_counts = {}

    # Procesar cada documento
    for idx, doc in enumerate(docs, 1):
        doc_id = doc["id"]
        filename = doc["filename"]
        processed_path = doc.get("processed_path")

        print(f"[{idx}/{len(docs)}] Procesando: {filename[:60]}...", end=" ")

        # Validar path
        if not processed_path:
            print("⚠ SIN RUTA")
            failed += 1
            continue

        path = Path(processed_path)
        if not path.exists():
            # Intentar path alternativo
            base_dir = Path(__file__).resolve().parent.parent
            alt_path = base_dir / "data" / "processed" / path.name
            if alt_path.exists():
                path = alt_path
            else:
                print(f"⚠ NO ENCONTRADO")
                failed += 1
                continue

        try:
            # Leer texto
            with open(path, 'r', encoding='utf-8') as f:
                text = f.read()

            if not text.strip():
                print("⚠ VACÍO")
                failed += 1
                continue

            # Extraer metadatos
            metadata = metadata_service.extract_metadata(text, filename)

            # Guardar en DB
            persistence.update_document_metadata(doc_id, metadata)

            if metadata.get("metadata_extraction_failed"):
                print(f"❌ FALLÓ")
                failed += 1
            else:
                doc_type = metadata.get("doc_type", "otro")
                year = metadata.get("doc_year", "?")
                conf = metadata.get("classification_confidence", 0)
                print(f"✓ {doc_type} ({year}) conf={conf:.2f}")

                processed += 1
                type_counts[doc_type] = type_counts.get(doc_type, 0) + 1

        except Exception as e:
            print(f"❌ ERROR: {str(e)[:40]}")
            failed += 1

    # Resumen final
    print()
    print("=" * 70)
    print("RESUMEN FINAL")
    print("=" * 70)
    print(f"Total procesados exitosamente: {processed}")
    print(f"Fallidos: {failed}")
    print(f"Total: {processed + failed}")
    print()

    if type_counts:
        print("Distribución por tipo de documento:")
        for doc_type, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            bar = "█" * (count * 50 // max(type_counts.values()))
            print(f"  {doc_type:20s} {count:4d} {bar}")
        print()

    if failed > 0:
        print("Nota: Los documentos fallidos tendrán metadata_extraction_failed=TRUE")
        print("      y podrán ser reintentados ejecutando este script nuevamente.")

    print("=" * 70)


if __name__ == "__main__":
    main()
