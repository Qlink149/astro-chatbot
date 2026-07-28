from pydantic import BaseModel, Field


class ClientConfig(BaseModel):
    """Per-client settings for the WhatsApp chatbot."""

    client_id: str = Field(
        ...,
        description="Stable slug used in webhooks and routing (e.g. samara).",
    )
    brand_name: str = Field(
        ...,
        description="Display name shown in prompts and user-facing copy.",
    )
    brand_voice: str = Field(
        ...,
        description="Tone descriptor injected into agent system prompts.",
    )
    intent_categories: list[str] = Field(
        ...,
        description="Intent labels used by routing / agents for this client.",
    )
