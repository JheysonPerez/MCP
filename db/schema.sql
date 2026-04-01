-- Creación de la estructura base de la base de datos PostgreSQL.
-- Este archivo se puede ejecutar manualmente o a través del script de setup en Python.

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255),
    role VARCHAR(20) DEFAULT 'user' CHECK (role IN ('admin', 'user')),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    original_path VARCHAR(500),
    processed_path VARCHAR(500),
    uploaded_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    -- Campos de ciclo de vida RAG
    processing_status VARCHAR(50) DEFAULT 'pending',
    is_indexed BOOLEAN DEFAULT FALSE,
    chunk_count INTEGER DEFAULT 0,
    last_indexed_at TIMESTAMP WITH TIME ZONE,
    error_log TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT check_processing_status 
        CHECK (processing_status IN ('pending', 'completed', 'failed'))
);

-- Índices para optimizar el arranque y la gestión del repositorio
CREATE INDEX IF NOT EXISTS idx_documents_indexed ON documents(is_indexed);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(processing_status);

CREATE TABLE IF NOT EXISTS queries (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    query_text TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS responses (
    id SERIAL PRIMARY KEY,
    query_id INTEGER REFERENCES queries(id) ON DELETE CASCADE,
    response_text TEXT NOT NULL,
    generated_by_model VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS generated_documents (
    id SERIAL PRIMARY KEY,
    response_id INTEGER REFERENCES responses(id) ON DELETE CASCADE,
    document_content TEXT NOT NULL,
    format VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Tabla para generación documental por IA
CREATE TABLE IF NOT EXISTS generated_documents_v2 (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    title VARCHAR(500) NOT NULL,
    prompt TEXT NOT NULL,
    content TEXT NOT NULL,
    format VARCHAR(20) DEFAULT 'markdown',
    generation_mode VARCHAR(50) DEFAULT 'prompt_libre',
    source_doc_ids INTEGER[],
    model_used VARCHAR(100),
    word_count INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT check_format 
        CHECK (format IN ('txt', 'markdown', 'pdf', 'docx')),
    CONSTRAINT check_mode
        CHECK (generation_mode IN ('prompt_libre', 'basado_repositorio', 'basado_documento'))
);

CREATE INDEX IF NOT EXISTS idx_gendocs_user ON generated_documents_v2(user_id);
CREATE INDEX IF NOT EXISTS idx_gendocs_mode ON generated_documents_v2(generation_mode);
