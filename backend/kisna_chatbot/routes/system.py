from fastapi import APIRouter, Depends

from kisna_chatbot.routes.dependencies.system_dependencies import (
    verify_token,
    verify_token_or_api_key,
)
from kisna_chatbot.routes.system_sub_routes import ai as ai_router
from kisna_chatbot.routes.system_sub_routes import auth as auth_router
from kisna_chatbot.routes.system_sub_routes import chat_history as chat_history_router
from kisna_chatbot.routes.system_sub_routes import conversation as conversation_module
from kisna_chatbot.routes.system_sub_routes import dashboard as dashboard_router
from kisna_chatbot.routes.system_sub_routes import message_trace as message_trace_router
from kisna_chatbot.routes.system_sub_routes import payments as payments_router
from kisna_chatbot.routes.system_sub_routes import samara_jobs as samara_jobs_router
from kisna_chatbot.routes.system_sub_routes import users as users_router
from kisna_chatbot.utils.logger_config import logger

router = APIRouter(prefix="/system", tags=["System"])

router.include_router(auth_router.router)

router.include_router(users_router.router)

router.include_router(conversation_module.stream_router)

router.include_router(
    conversation_module.router,
    dependencies=[Depends(verify_token_or_api_key)],
)

router.include_router(
    message_trace_router.router, dependencies=[Depends(verify_token)]
)

router.include_router(dashboard_router.router, dependencies=[Depends(verify_token)])

router.include_router(ai_router.router, dependencies=[Depends(verify_token)])

router.include_router(
    chat_history_router.router,
    dependencies=[Depends(verify_token_or_api_key)],
)

router.include_router(
    payments_router.router,
    dependencies=[Depends(verify_token_or_api_key)],
)

router.include_router(samara_jobs_router.router)


@router.get("/ping", dependencies=[Depends(verify_token)])
def ping():
    """Health check — confirms the server is running."""
    logger.info("Ping endpoint called")
    return {"message": "Samara Chatbot Server is running"}
