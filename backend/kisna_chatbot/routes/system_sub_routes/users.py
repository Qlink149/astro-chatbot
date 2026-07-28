from fastapi import APIRouter, Depends, HTTPException, Query

from kisna_chatbot.database.collections import chat_messages, message_traces, users
from kisna_chatbot.database.db_utils import get_all_users, get_user_by_phone, search_users
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
                    "reading_delivered_at": None,
                    "followup_questions_asked": 0,
                    "credits": 0,
                    "user_language": None,
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

