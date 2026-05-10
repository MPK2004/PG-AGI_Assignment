# PG-AGI RAG Pipeline

A professional RAG (Retrieval-Augmented Generation) pipeline implementation for processing machine learning textbooks.

## Project Structure

```text
PG-AGI_Assignment/
├── data/
│   ├── raw/                # Original PDF files (e.g., mitchell.pdf, burkov.pdf)
│   └── processed/          # Generated Markdown and JSON embeddings
├── src/                    # Core source code
│   ├── ingestion.py        # PDF extraction and Markdown conversion (Docling)
│   ├── embedding.py        # Structural chunking and vector generation
│   └── database.py         # Qdrant collection management and upsert
├── tests/                  # Verification scripts
│   ├── test_qdrant_cloud.py # Connectivity test for Qdrant Cloud
│   └── test_retrieval.py   # Vector search and retrieval validation
├── .gitignore              # Git ignore rules
├── requirements.txt        # Project dependencies
└── README.md               # Project documentation
```

## Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Environment**:
   Ensure you have access to Qdrant Cloud and your credentials are configured in the scripts (or ideally via environment variables).

## Usage Pipeline

### 1. Ingestion
Extract text from a specific page range of a PDF and convert it to Markdown.
```bash
python src/ingestion.py data/raw/mitchell.pdf 10 25
```

### 2. Embedding
Chunk the Markdown file and generate vector embeddings using `all-MiniLM-L6-v2`.
```bash
python src/embedding.py
```

### 3. Database Upsert
Upload the generated chunks and embeddings to Qdrant.
```bash
python src/database.py
```

### 4. Retrieval Test
Verify that the retrieval pipeline is working correctly.
```bash
python tests/test_retrieval.py
```
