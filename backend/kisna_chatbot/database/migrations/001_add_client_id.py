"""
Migration 001: Add client_id field and multi-tenant indexes.

Backfills client_id on documents missing the field and creates
a compound index on (client_id, phone_number) for each collection.
"""

from pymongo.collection import Collection
from pymongo.errors import OperationFailure

from kisna_chatbot.database.collections import (
    ratings,
    users,
)
from kisna_chatbot.utils.env_load import mongo_uri
from kisna_chatbot.utils.logger_config import logger

DEFAULT_CLIENT_ID = "samara"
INDEX_NAME = "client_id_phone_number"

MISSING_CLIENT_ID_FILTER = {
    "$or": [
        {"client_id": {"$exists": False}},
        {"client_id": None},
    ]
}


def backfill_client_id(collection: Collection, name: str) -> int:
    result = collection.update_many(
        MISSING_CLIENT_ID_FILTER,
        {"$set": {"client_id": DEFAULT_CLIENT_ID}},
    )
    modified = result.modified_count
    logger.info(
        "Backfilled client_id",
        extra={"collection": name, "modified": modified},
    )
    return modified


def ensure_index(collection: Collection, name: str) -> None:
    try:
        collection.create_index(
            [("client_id", 1), ("phone_number", 1)],
            name=INDEX_NAME,
        )
        logger.info("Ensured index", extra={"collection": name, "index": INDEX_NAME})
    except OperationFailure as exc:
        logger.warning(
            "Index create skipped/failed",
            extra={"collection": name, "error": str(exc)},
        )


def run() -> None:
    logger.info("Running migration 001_add_client_id", extra={"mongo_uri_set": bool(mongo_uri)})
    for collection, name in (
        (users, "users"),
        (ratings, "ratings"),
    ):
        backfill_client_id(collection, name)
        ensure_index(collection, name)
    logger.info("Migration 001 complete")


if __name__ == "__main__":
    run()
