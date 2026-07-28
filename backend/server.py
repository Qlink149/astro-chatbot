"""Supervisor entrypoint — mounts the kisna-chatbot multi-client app under /api."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from kisna_chatbot.main import app as chatbot_app


@asynccontextmanager
async def lifespan(_app: FastAPI):
    async with chatbot_app.router.lifespan_context(chatbot_app):
        yield


app = FastAPI(
    title="Samara by Clara — Gateway",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.mount("/api", chatbot_app)


@app.get("/")
def root():
    return {"service": "samara-by-clara", "status": "ok"}
