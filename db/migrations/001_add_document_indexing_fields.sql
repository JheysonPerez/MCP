-- MIGRACIÓN 001: Campos de Indexación Documental
-- Propósito: Añadir trazabilidad de procesamiento y búsqueda semántica de forma segura.

-- 1. Añadir nuevas columnas de forma incremental
ALTER TABLE documents 
    ADD COLUMN IF NOT EXISTS processing_status VARCHAR(50) DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS is_indexed BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS chunk_count INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS last_indexed_at TIMESTAMP WITH TIME ZONE,
    ADD COLUMN IF NOT EXISTS error_log TEXT;

-- 2. Garantizar la restricción de integridad con nombre explícito
-- Eliminamos primero por si existiera con nombre automático o previo
ALTER TABLE documents DROP CONSTRAINT IF EXISTS check_processing_status;
ALTER TABLE documents 
    ADD CONSTRAINT check_processing_status 
    CHECK (processing_status IN ('pending', 'completed', 'failed'));

-- 3. Optimización de rendimiento (Índices)
CREATE INDEX IF NOT EXISTS idx_documents_indexed ON documents(is_indexed);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(processing_status);
