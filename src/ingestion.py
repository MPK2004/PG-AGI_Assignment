import sys
import os
from docling.document_converter import DocumentConverter

def main():
    """
    Ingests a specific page range of a PDF and converts it to Markdown.
    Usage: python ingestion.py [pdf_path] [start_page] [end_page]
    """
    default_pdf = "data/raw/mitchell.pdf"
    default_start = 10
    default_end = 25
    
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else default_pdf
    start_page = int(sys.argv[2]) if len(sys.argv) > 2 else default_start
    end_page = int(sys.argv[3]) if len(sys.argv) > 3 else default_end
    
    if not os.path.exists(pdf_path):
        print(f"Error: PDF file not found at {pdf_path}")
        print("Please ensure the PDF is in the data/ directory.")
        sys.exit(1)

    print(f"Initializing Ingestion for: {os.path.basename(pdf_path)}")
    print(f"Page Range: {start_page} - {end_page}")
    
    try:
        converter = DocumentConverter()
        
        print("Converting PDF to Markdown... (this may take a moment)")
        
        result = converter.convert(pdf_path, page_range=(start_page, end_page))
        
        md_content = result.document.export_to_markdown()
        
        output_file = "data/processed/test_output.md"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(md_content)
            
        print(f"Successfully exported to {output_file}")
        print(f"Stats: {len(md_content)} characters extracted.")
        
    except Exception as e:
        print(f"Error during ingestion: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
