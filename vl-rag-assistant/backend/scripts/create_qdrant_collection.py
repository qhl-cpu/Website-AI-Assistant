import os

from dotenv import load_dotenv
from qdrant_client import QdrantClient, models


load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
COLLECTION_NAME = os.getenv(
    "QDRANT_COLLECTION_NAME",
    "vancouver_laser_content",
)

# Replace this with the size printed from your embedded JSONL file.
VECTOR_SIZE = 1536


def main() -> None:
    if not QDRANT_URL:
        raise ValueError("Missing QDRANT_URL")

    if not QDRANT_API_KEY:
        raise ValueError("Missing QDRANT_API_KEY")

    client = QdrantClient(
        url=QDRANT_URL,
        api_key=QDRANT_API_KEY,
        timeout=60,
    )

    if client.collection_exists(COLLECTION_NAME):
        print(f"Collection already exists: {COLLECTION_NAME}")
        return

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=models.VectorParams(
            size=VECTOR_SIZE,
            distance=models.Distance.COSINE,
        ),
    )

    print(f"Created collection: {COLLECTION_NAME}")


if __name__ == "__main__":
    main()