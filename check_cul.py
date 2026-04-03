import os, re

# Encontrar archivo del doc 25
processed_dir = "data/processed"
files = os.listdir(processed_dir)
print("Archivos:", files)

# Abrir el más reciente
latest = sorted([f for f in files if 'Certificado' in f or 'certificado' in f.lower()])
print("CUL file:", latest)

if latest:
    with open(f"{processed_dir}/{latest[-1]}", "r") as f:
        text = f.read()
    
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    print(f"\nTotal líneas: {len(lines)}")
    
    form_lines = sum(1 for l in lines if re.match(r'^[^:]+:\s+\S+', l))
    print(f"Líneas formulario: {form_lines}")
    print(f"Ratio: {form_lines/len(lines):.2f}")
    
    print("\n--- PRIMERAS 20 LÍNEAS ---")
    for i, l in enumerate(lines[:20]):
        print(f"{i:2}: '{l}'")
