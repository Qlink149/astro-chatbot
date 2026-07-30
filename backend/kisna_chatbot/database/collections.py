from kisna_chatbot.database.database import db

# All collections include client_id field for multi-tenancy

users = db["users"]
ratings = db["ratings"]
ai_usage_logs = db["ai_usage_logs"]
processed_inbound_messages = db["processed_inbound_messages"]
chat_messages = db["chat_messages"]
message_traces = db["message_traces"]
payments = db["payments"]
samara_funnel = db["samara_funnel"]

COLLECTIONS = (
    users,
    ratings,
    ai_usage_logs,
    processed_inbound_messages,
    chat_messages,
    message_traces,
    payments,
    samara_funnel,
)
