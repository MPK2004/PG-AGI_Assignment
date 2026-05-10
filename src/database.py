import json
import os
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct

load_dotenv()

CLUSTER_URL = os.getenv("QDRANT_URL")
API_KEY = os.getenv("QDRANT_API_KEY")
COLLECTION_NAME = "ml_knowledge_base"

def upsert_data():
    print(f"Connecting to Qdrant at {CLUSTER_URL}...")
    client = QdrantClient(url=CLUSTER_URL, api_key=API_KEY)

    json_path = "data/processed/processed_chunks.json"
    if not os.path.exists(json_path):
        print(f"Error: {json_path} not found. Please run embedding.py first.")
        return

    print(f"Loading chunks from {json_path}...")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"Creating collection '{COLLECTION_NAME}'...")
    client.recreate_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=384, distance=Distance.COSINE),
    )

    print(f"Preparing {len(data)} points for upsert...")
    points = []
    for item in data:
        payload = {"text": item["text"]}
        if "metadata" in item:
            payload.update(item["metadata"])
            
        points.append(PointStruct(
            id=item["id"],
            vector=item["vector"],
            payload=payload
        ))

    batch_size = 100
    for i in range(0, len(points), batch_size):
        batch = points[i : i + batch_size]
        print(f"Upserting batch {i//batch_size + 1} ({len(batch)} points)...")
        client.upsert(
            collection_name=COLLECTION_NAME,
            points=batch
        )

    print(f"Successfully upserted {len(data)} points to '{COLLECTION_NAME}'.")

if __name__ == "__main__":
    upsert_data()
