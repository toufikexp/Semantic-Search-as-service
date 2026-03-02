"""Re-process documents stuck in 'pending' or 'failed' status.

Usage (run inside the embedding-worker container):

    docker compose exec embedding-worker python scripts/reprocess_pending.py <collection_id>

    # To also retry documents that previously failed:
    docker compose exec embedding-worker python scripts/reprocess_pending.py <collection_id> --include-failed
"""

import argparse
import sys

from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.collection import Collection
from app.models.document import Document
from app.workers.tasks import _process_single_document


def main():
    parser = argparse.ArgumentParser(description="Re-process pending/failed documents")
    parser.add_argument("collection_id", help="UUID of the collection to reprocess")
    parser.add_argument(
        "--include-failed",
        action="store_true",
        help="Also retry documents with status='failed'",
    )
    args = parser.parse_args()

    engine = create_engine(settings.DATABASE_URL_SYNC, pool_size=5)

    with Session(engine) as db:
        collection = db.execute(
            select(Collection).where(Collection.id == args.collection_id)
        ).scalar_one_or_none()

        if collection is None:
            print(f"Collection {args.collection_id} not found")
            sys.exit(1)

        # Reset failed docs to pending if requested
        statuses = ["pending"]
        if args.include_failed:
            reset = db.execute(
                update(Document)
                .where(
                    Document.collection_id == args.collection_id,
                    Document.status == "failed",
                )
                .values(status="pending")
            )
            db.commit()
            print(f"Reset {reset.rowcount} failed documents to pending")

        documents = (
            db.execute(
                select(Document).where(
                    Document.collection_id == args.collection_id,
                    Document.status == "pending",
                )
            )
            .scalars()
            .all()
        )

        if not documents:
            print("No pending documents found — nothing to do.")
            sys.exit(0)

        print(f"Found {len(documents)} pending documents. Processing...")

        ok, failed = 0, 0
        for i, doc in enumerate(documents, 1):
            try:
                _process_single_document(db, doc, collection)
                db.commit()
                ok += 1
                print(f"  [{i}/{len(documents)}] {doc.external_id} — indexed")
            except Exception as e:
                db.rollback()
                failed += 1
                print(f"  [{i}/{len(documents)}] {doc.external_id} — FAILED: {e}")

        # Update collection doc count
        total_indexed = len(
            db.execute(
                select(Document).where(
                    Document.collection_id == args.collection_id,
                    Document.status == "indexed",
                )
            )
            .scalars()
            .all()
        )
        collection.doc_count = total_indexed
        db.commit()

        print(f"\nDone: {ok} indexed, {failed} failed, {total_indexed} total in collection")


if __name__ == "__main__":
    main()
