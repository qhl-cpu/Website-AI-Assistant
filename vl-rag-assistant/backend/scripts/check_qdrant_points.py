import os

from dotenv import load_dotenv
from qdrant_client import QdrantClient


load_dotenv()

client = QdrantClient(
    url=os.environ["QDRANT_URL"],
    api_key=os.environ["QDRANT_API_KEY"],
)

collection_name = os.getenv(
    "QDRANT_COLLECTION_NAME",
    "vancouver_laser_content",
)

points, next_page_offset = client.scroll(
    collection_name=collection_name,
    limit=3,
    with_payload=True,
    with_vectors=False,
)

print(f"Returned {len(points)} points.")
print()

for point in points:
    payload = point.payload or {}

    print(f"Point ID: {point.id}")
    print(f"Chunk ID: {payload.get('chunk_id')}")
    print(f"Title: {payload.get('title')}")
    print(f"Section: {payload.get('section_type')}")
    print(f"Status: {payload.get('status')}")
    print(f"URL: {payload.get('url')}")
    print(f"Text: {payload.get('text')}")
    print("-" * 60)

print(f"Next offset: {next_page_offset}")