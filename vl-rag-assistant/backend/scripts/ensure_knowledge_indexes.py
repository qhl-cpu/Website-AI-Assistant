"""Check or initialize the payload indexes used by chat and knowledge management."""

import argparse
import sys

from app.core.config import QDRANT_COLLECTION_NAME
from app.knowledge.index import payload_index_gaps
from app.services.vector_store import get_qdrant_client


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Create missing indexes in the configured collection.")
    args = parser.parse_args()

    client = get_qdrant_client()
    info = client.get_collection(QDRANT_COLLECTION_NAME)
    missing, mismatched = payload_index_gaps(info)

    if mismatched:
        for field, expected in mismatched.items():
            actual = info.payload_schema[field].data_type.value
            print(f"Incompatible index: {field} is {actual}, expected {expected.value}.", file=sys.stderr)
        return 2

    if missing and not args.apply:
        for field, expected in missing.items():
            print(f"Missing index: {field} ({expected.value})")
        print("Run again with --apply to create the missing indexes.")
        return 1

    for field, expected in missing.items():
        client.create_payload_index(
            collection_name=QDRANT_COLLECTION_NAME,
            field_name=field,
            field_schema=expected,
            wait=True,
        )
        print(f"Created index: {field} ({expected.value})")

    if missing:
        missing, mismatched = payload_index_gaps(client.get_collection(QDRANT_COLLECTION_NAME))
        if missing or mismatched:
            print("Some indexes could not be verified. Check the collection before deployment.", file=sys.stderr)
            return 2
    print("All knowledge payload indexes are present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
