import os

from dotenv import load_dotenv
from qdrant_client import QdrantClient


load_dotenv()

qdrant_url = os.getenv("QDRANT_URL")
qdrant_api_key = os.getenv("QDRANT_API_KEY")

if not qdrant_url:
    raise ValueError("Missing QDRANT_URL")

if not qdrant_api_key:
    raise ValueError("Missing QDRANT_API_KEY")

client = QdrantClient(
    url=qdrant_url,
    api_key=qdrant_api_key,
    timeout=30,
)

collections = client.get_collections()

print("Connected successfully.")
print(collections)