#!/usr/bin/env python3
"""
Script para probar la detección de formularios en el documento CUL existente.
Este script simula lo que hace chunk_service._is_form_document() sin necesidad de reindexar.
"""

import os
import re

processed_dir = "data/processed"
files = os.listdir(processed_dir)

# Encontrar archivo CUL
cul_files = [f for f in files if 'certificado' in f.lower() and 'laboral' in f.lower()]
if not cul_files:
    print("No se encontró archivo CUL")
    exit(1)

latest = sorted(cul_files)[-1]
print(f"Analizando: {latest}")

with open(f"{processed_dir}/{latest}", "r") as f:
    text = f.read()

lines = [l.strip() for l in text.split('\n') if l.strip()]
print(f"\nTotal líneas: {len(lines)}")

# Simular el nuevo _is_form_document
form_count = 0
detected_patterns = []

for i, l in enumerate(lines):
    pattern = None
    # Patrón 1: "Clave : Valor"
    if re.match(r'^[^:]{2,40}:\s*\S+', l):
        form_count += 1
        pattern = "P1 (clave:valor)"
    # Patrón 2: "Clave :"
    elif re.match(r'^[^:]{2,40}:\s*$', l):
        form_count += 1
        pattern = "P2 (clave:)"
    # Patrón 3: línea corta
    elif len(l) < 40 and not l.endswith('.') and not l.startswith('•'):
        form_count += 1
        pattern = "P3 (valor corto)"
    
    if pattern:
        detected_patterns.append((i, l[:50], pattern))

ratio = form_count / len(lines)
print(f"Líneas detectadas: {form_count}")
print(f"Ratio: {ratio:.2f}")
print(f"Threshold: 0.30")
print(f"Resultado: {'FORMULARIO ✓' if ratio > 0.30 else 'NO FORMULARIO ✗'}")

print("\n--- PRIMERAS 20 LÍNEAS CON DETECCIÓN ---")
for i, line, pattern in detected_patterns[:20]:
    print(f"{i:2}: [{pattern}] {line}")
