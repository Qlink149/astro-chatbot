import time

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
            offered = int(stats["funnel"].get("beat_2b_date_offered", 0) or 0)
            confirmed = int(stats["funnel"].get("beat_2b_date_confirmed", 0) or 0)
            stats["date_confirmation_rate"] = confirmed / max(1, offered)
            stats["total_gate_shown"] = stats["funnel"].get("gate_shown", 0)
            stats["total_payment_succeeded"] = stats["funnel"].get(
                "payment_succeeded", 0
            )
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


@router.get("/model-mix")
def model_mix_cost(
    days: int = Query(7, ge=1, le=90),
    client_id: str = Query("samara"),
):
    """Model-mix breakdown and rough cost-per-conversation from ai_usage_logs."""
    try:
        from kisna_chatbot.database.collections import ai_usage_logs, users

        since = int(time.time()) - days * 86400
        pipeline = [
            {"$match": {"client_id": client_id, "created_at": {"$gte": since}}},
            {
                "$group": {
                    "_id": "$model",
                    "requests": {"$sum": 1},
                    "prompt_tokens": {"$sum": "$prompt_tokens"},
                    "completion_tokens": {"$sum": "$completion_tokens"},
                    "estimated_cost_usd": {"$sum": "$estimated_cost_usd"},
                }
            },
            {"$sort": {"estimated_cost_usd": -1}},
        ]
        rows = list(ai_usage_logs.aggregate(pipeline))
        total_cost = sum(r.get("estimated_cost_usd") or 0 for r in rows)
        total_requests = sum(r.get("requests") or 0 for r in rows)

        active_users = users.count_documents({
            "client_id": client_id,
            "chat_history": {"$exists": True, "$ne": []},
        })
        cost_per_conversation = (
            round(total_cost / max(1, active_users), 4) if total_cost else 0
        )

        return {
            "client_id": client_id,
            "days": days,
            "total_cost_usd": round(total_cost, 6),
            "total_requests": total_requests,
            "cost_per_conversation_usd": cost_per_conversation,
            "active_users_with_chat": active_users,
            "by_model": [
                {
                    "model": r["_id"] or "unknown",
                    "requests": r["requests"],
                    "prompt_tokens": r["prompt_tokens"],
                    "completion_tokens": r["completion_tokens"],
                    "estimated_cost_usd": round(r.get("estimated_cost_usd") or 0, 6),
                    "pct_of_cost": round(
                        ((r.get("estimated_cost_usd") or 0) / max(total_cost, 0.0001)) * 100, 1
                    ),
                }
                for r in rows
            ],
        }
    except Exception:
        logger.exception("Failed to fetch model mix")
        raise HTTPException(status_code=500, detail="Failed to fetch model mix")
