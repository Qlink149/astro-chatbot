from fastapi import APIRouter, HTTPException, Query
from typing import Literal

from kisna_chatbot.database.db_utils import (
    get_dashboard_stats,
    get_rating_stats,
    get_user_growth,
)
from kisna_chatbot.utils.logger_config import logger

router = APIRouter(prefix="/dashboard", tags=["System - Dashboard"])

Period = Literal["year", "month", "week"]


@router.get("/stats")
def dashboard_stats(client_id: str = Query("samara", description="Tenant client id")):
    """Return high-level dashboard statistics."""
    try:
        stats = get_dashboard_stats(client_id=client_id)
        if client_id == "samara":
            from kisna_chatbot.database.collections import users

            stats["total_readings"] = users.count_documents(
                {"client_id": "samara", "free_reading_used": True}
            )
            agg = list(
                users.aggregate(
                    [
                        {"$match": {"client_id": "samara"}},
                        {
                            "$group": {
                                "_id": None,
                                "total": {
                                    "$sum": {
                                        "$ifNull": ["$followup_questions_asked", 0]
                                    }
                                },
                            }
                        },
                    ]
                )
            )
            stats["total_followup_questions"] = agg[0]["total"] if agg else 0
            from kisna_chatbot.utils.funnel_events import get_funnel_counts

            stats["funnel"] = get_funnel_counts(client_id)
            # Prefer free-deep count when present; fall back to free_reading_used
            stats["total_free_deep_answers"] = stats["funnel"].get(
                "free_deep_answer_sent", 0
            )
            stats["total_beat1_sent"] = stats["funnel"].get("beat1_sent", 0)
            stats["total_topics_chosen"] = stats["funnel"].get("topic_chosen", 0)
        return stats
    except Exception:
        logger.exception("Failed to fetch dashboard stats")
        raise HTTPException(status_code=500, detail="Failed to fetch dashboard stats")


@router.get("/ratings")
def rating_stats(client_id: str = Query("samara", description="Tenant client id")):
    """Return experience rating breakdown and average score."""
    try:
        return get_rating_stats(client_id=client_id)
    except Exception:
        logger.exception("Failed to fetch rating stats")
        raise HTTPException(status_code=500, detail="Failed to fetch rating stats")


@router.get("/users/growth")
def users_growth(
    period: Period = Query("month", description="Grouping granularity: year | month | week"),
    client_id: str = Query("samara", description="Tenant client id"),
):
    """Return new user counts grouped by period."""
    try:
        data = get_user_growth(period=period, client_id=client_id)
        return {"period": period, "data": data}
    except Exception:
        logger.exception("Failed to fetch user growth", extra={"period": period})
        raise HTTPException(status_code=500, detail="Failed to fetch user growth")
