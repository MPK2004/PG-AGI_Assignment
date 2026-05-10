import re
import os
import json
from sentence_transformers import SentenceTransformer

def chunk_markdown_with_metadata(text):
    """
    Splits Markdown text on header boundaries and extracts the section header.
    Returns a list of dictionaries: {"text": ..., "section_header": ...}
    """
    lines = text.split('\n')
    chunks = []
    current_chunk = []
    current_header = "Initial Section"
    
    header_pattern = re.compile(r'^(#+)\s+(.*)')
    
    for line in lines:
        match = header_pattern.match(line)
        if match:
            if current_chunk:
                chunks.append({
                    "text": '\n'.join(current_chunk).strip(),
                    "section_header": current_header
                })
            
            current_header = match.group(2).strip()
            current_chunk = [line]
        else:
            current_chunk.append(line)
            
    if current_chunk:
        chunks.append({
            "text": '\n'.join(current_chunk).strip(),
            "section_header": current_header
        })
        
    return [c for c in chunks if c["text"].strip()]

def main():
    input_file = "data/processed/test_output.md"
    
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found. Please run ingestion.py first.")
        return

    print(f"Reading {input_file}...")
    with open(input_file, "r", encoding="utf-8") as f:
        content = f.read()
    
    source_book = "Unknown"
    if "Andriy Burkov" in content or "Hundred-Page" in content:
        source_book = "Burkov"
    elif "Mitchell" in content:
        source_book = "Mitchell"
    
    print(f"Identified Source Book: {source_book}")

    print("Splitting Markdown into structural chunks with metadata...")
    chunks_with_metadata = chunk_markdown_with_metadata(content)
    
    model_name = 'all-MiniLM-L6-v2'
    print(f"Initializing Embedding Model: {model_name}...")
    model = SentenceTransformer(model_name)
    
    print(f"Generating embeddings for {len(chunks_with_metadata)} chunks...")
    
    texts = [c["text"] for c in chunks_with_metadata]
    embeddings = model.encode(texts)
    
    payloads = []
    for i, chunk in enumerate(chunks_with_metadata):
        payloads.append({
            "id": i,
            "text": chunk["text"],
            "vector": embeddings[i].tolist(),
            "metadata": {
                "source_book": source_book,
                "section_header": chunk["section_header"]
            }
        })
    
    output_json = "data/processed/processed_chunks.json"
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(payloads, f, indent=4)
    
    print("\n" + "="*40)
    print(f"Processing Complete")
    print(f"Total chunks generated: {len(payloads)}")
    print(f"Vector dimension size: {embeddings.shape[1]}")
    print(f"Saved to {output_json}")
    print("="*40 + "\n")

if __name__ == "__main__":
    main()
