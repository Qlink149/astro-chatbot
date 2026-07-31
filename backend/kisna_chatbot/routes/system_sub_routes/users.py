from fastapi import APIRouter, Depends, HTTPException, Query

from kisna_chatbot.database.collections import (
    ai_usage_logs,
    chat_messages,
    message_traces,
    payments,
    processed_inbound_messages,
    ratings,
    users,
)
from kisna_chatbot.database.db_utils import get_all_users, get_user_by_phone, search_users
from kisna_chatbot.payments.credit_ledger import get_credit_balance, grant_credits
from kisna_chatbot.routes.dependencies.system_dependencies import verify_token
from kisna_chatbot.utils.logger_config import logger

router = APIRouter(
    prefix="/user",
    tags=["System - Users"],
    dependencies=[Depends(verify_token)],
)


@router.get("")
def list_users(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    agent_requested: bool | None = Query(
        None, description="Filter to only users who requested a live agent"
    ),
    client_id: str = Query("samara", description="Tenant client id"),
):
    """List all users — sorted by most recently updated, with pagination. Pass agent_requested=true to filter to live-agent requests only."""
    try:
        return get_all_users(
            page=page,
            limit=limit,
            client_id=client_id,
            agent_requested=agent_requested,
        )
    except Exception:
        logger.exception("Failed to list users")
        raise HTTPException(status_code=500, detail="Failed to fetch users")


@router.get("/search")
def search(
    q: str = Query(..., min_length=1, description="Search term — matches phone number or username"),
    limit: int = Query(20, ge=1, le=100),
    client_id: str = Query("samara", description="Tenant client id"),
):
    """Search users by phone number or username (partial, case-insensitive)."""
    try:
        results = search_users(q=q, limit=limit, client_id=client_id)
        return {"results": results, "count": len(results)}
    except Exception:
        logger.exception("Failed to search users", extra={"q": q})
        raise HTTPException(status_code=500, detail="Failed to search users")


@router.get("/{phone_number}")
def get_user(
    phone_number: str,
    client_id: str = Query("samara", description="Tenant client id"),
):
    """Get complete user document by phone number."""
    try:
        user = get_user_by_phone(phone_number, client_id=client_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to get user", extra={"phone_number": phone_number})
        raise HTTPException(status_code=500, detail="Failed to fetch user")


@router.post("/{phone_number}/reset")
def reset_user(
    phone_number: str,
    client_id: str = Query("samara", description="Tenant client id"),
):
    """Wipe a user's chat + reading state so they restart from the greeting.

    Testing-only convenience. Clears chat_history, chat_messages archive,
    message_traces, chart, birth details, and every 'reading progress' flag on
    the user profile — the profile row itself is kept (phone stays known).
    """
    try:
        query = {"phone_number": phone_number, "client_id": client_id}
        user = users.find_one(query)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        result = users.update_one(
            query,
            {
                "$set": {
                    "chat_history": [],
                    "chart_json": None,
                    "birth_details": None,
                    "free_reading_used": False,
                    "free_deep_answer_used": False,
                    "reading_delivered_at": None,
                    "followup_questions_asked": 0,
                    "credits": 0,
                    "user_language": None,
                    "conversation_beat": None,
                    "beat_last_inbound_id": None,
                    "chosen_topic": None,
                    "open_loop_summary": None,
                    "confirmed_events": [],
                    "rejected_windows": [],
                    "beat2_windows_offered": 0,
                    "beat2_offered_starts": [],
                    "beat2_pending_window": None,
                },
            },
        )

        chat_deleted = chat_messages.delete_many(query).deleted_count
        trace_deleted = message_traces.delete_many(query).deleted_count

        logger.info(
            "Samara user reset",
            extra={
                "phone_number": phone_number,
                "client_id": client_id,
                "profile_updated": result.modified_count,
                "chat_messages_deleted": chat_deleted,
                "message_traces_deleted": trace_deleted,
            },
        )
        return {
            "status": "ok",
            "phone_number": phone_number,
            "client_id": client_id,
            "chat_messages_deleted": chat_deleted,
            "message_traces_deleted": trace_deleted,
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to reset user", extra={"phone_number": phone_number})
        raise HTTPException(status_code=500, detail="Failed to reset user")



@router.post("/{phone_number}/delete-chat")
def delete_user_chat(
    phone_number: str,
    client_id: str = Query("samara", description="Tenant client id"),
):
    """Delete a user's chat history but KEEP their chart / profile / language.

    Use this when you want to clear the conversation transcript for a user
    but let them continue from where they were (chart already computed, free
    reading already delivered, language already picked). If you want a full
    reset (chart + birth details + language + credits wiped), use /reset.
    """
    try:
        query = {"phone_number": phone_number, "client_id": client_id}
        user = users.find_one(query)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        result = users.update_one(query, {"$set": {"chat_history": []}})
        chat_deleted = chat_messages.delete_many(query).deleted_count
        trace_deleted = message_traces.delete_many(query).deleted_count

        logger.info(
            "Samara user chat deleted",
            extra={
                "phone_number": phone_number,
                "client_id": client_id,
                "profile_updated": result.modified_count,
                "chat_messages_deleted": chat_deleted,
                "message_traces_deleted": trace_deleted,
            },
        )
        return {
            "status": "ok",
            "phone_number": phone_number,
            "client_id": client_id,
            "chat_messages_deleted": chat_deleted,
            "message_traces_deleted": trace_deleted,
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "Failed to delete user chat", extra={"phone_number": phone_number}
        )
        raise HTTPException(status_code=500, detail="Failed to delete user chat")


@router.post("/{phone_number}/grant-credits")
def grant_user_credits(
    phone_number: str,
    amount: int = Query(10, ge=1, le=100, description="Credits to grant"),
    client_id: str = Query("samara", description="Tenant client id"),
):
    """Admin bypass: grant credits so the user can continue without Razorpay.

    Also clears session paywall suppress flags so the next deep question works.
    """
    try:
        query = {"phone_number": phone_number, "client_id": client_id}
        user = users.find_one(query)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        updated = grant_credits(
            phone_number=phone_number,
            client_id=client_id,
            amount=int(amount),
            source="admin_bypass",
            payment_id=None,
        )
        if not updated:
            raise HTTPException(status_code=500, detail="Failed to grant credits")

        users.update_one(
            query,
            {
                "$set": {
                    "paywall_pitch_suppressed": False,
                    "paywall_deferred": False,
                    "gate_suppressed_session": False,
                }
            },
        )
        refreshed = users.find_one(query) or updated
        balance = get_credit_balance(refreshed)

        logger.info(
            "Admin credit bypass granted",
            extra={
                "phone_number": phone_number,
                "client_id": client_id,
                "amount": amount,
                "balance": balance,
            },
        )
        return {
            "status": "ok",
            "phone_number": phone_number,
            "client_id": client_id,
            "granted": int(amount),
            "credits": balance,
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "Failed to grant credits", extra={"phone_number": phone_number}
        )
        raise HTTPException(status_code=500, detail="Failed to grant credits")


@router.post("/{phone_number}/delete")
def delete_user_fully(
    phone_number: str,
    client_id: str = Query("samara", description="Tenant client id"),
):
    """Hard-delete this user and related rows — fresh WhatsApp start next time."""
    try:
        query = {"phone_number": phone_number, "client_id": client_id}
        user = users.find_one(query)
        if not user:
            # Still wipe related collections in case of orphans
            pass

        deleted = {
            "users": users.delete_many(query).deleted_count,
            "chat_messages": chat_messages.delete_many(query).deleted_count,
            "message_traces": message_traces.delete_many(query).deleted_count,
            "ai_usage_logs": ai_usage_logs.delete_many(query).deleted_count,
            "processed_inbound_messages": processed_inbound_messages.delete_many(
                query
            ).deleted_count,
            "payments": payments.delete_many(query).deleted_count,
            "ratings": ratings.delete_many(query).deleted_count,
        }

        if deleted["users"] == 0 and user is None:
            raise HTTPException(status_code=404, detail="User not found")

        logger.info(
            "Samara user hard-deleted",
            extra={
                "phone_number": phone_number,
                "client_id": client_id,
                **{f"deleted_{k}": v for k, v in deleted.items()},
            },
        )
        return {
            "status": "ok",
            "phone_number": phone_number,
            "client_id": client_id,
            "deleted": deleted,
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "Failed to delete user", extra={"phone_number": phone_number}
        )
        raise HTTPException(status_code=500, detail="Failed to delete user")

