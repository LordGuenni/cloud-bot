from __future__ import annotations

import asyncio
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from botbuilder.core import (
    BotFrameworkAdapter,
    BotFrameworkAdapterSettings,
    MemoryStorage,
    UserState,
    ConversationState,
)
from botbuilder.schema import Activity

from .bot import RegistrationBot
from .config import KeyVaultSecretProvider, load_app_config
from .dialog import RegistrationDialog
from .ner import AzureNerExtractor
from .speech import SpeechTokenService
from .storage import CosmosAccountStore

app = FastAPI(title="Registration Voice/Chat Bot (Bot Framework SDK)")

app_config = load_app_config()
secret_provider = KeyVaultSecretProvider(app_config.key_vault_uri)
secret_names = app_config.key_vault_secret_names

required_secret_keys = [
    "speech_key",
    "speech_region",
    "cosmos_endpoint",
    "cosmos_key",
    "cosmos_database",
    "cosmos_container",
    "language_endpoint",
    "language_key",
]
missing_secret_keys = [key for key in required_secret_keys if key not in secret_names]
if missing_secret_keys:
    missing = ", ".join(missing_secret_keys)
    raise RuntimeError(f"Fehlende Secret-Mappings in config.json: {missing}")

# Optional Bot App Credentials
app_id = secret_provider.get_secret(secret_names.get("microsoft_app_id", "")) or ""
app_password = secret_provider.get_secret(secret_names.get("microsoft_app_password", "")) or ""

adapter_settings = BotFrameworkAdapterSettings(app_id, app_password)
adapter = BotFrameworkAdapter(adapter_settings)

# Storage & State
storage = MemoryStorage()
user_state = UserState(storage)
conversation_state = ConversationState(storage)

cosmos_endpoint = secret_provider.get_secret(secret_names["cosmos_endpoint"])
cosmos_key = secret_provider.get_secret(secret_names["cosmos_key"])
cosmos_database = secret_provider.get_secret(secret_names["cosmos_database"])
cosmos_container = secret_provider.get_secret(secret_names["cosmos_container"])
language_endpoint = secret_provider.get_secret(secret_names["language_endpoint"])
language_key = secret_provider.get_secret(secret_names["language_key"])

account_store = CosmosAccountStore(
    endpoint=cosmos_endpoint,
    key=cosmos_key,
    database_name=cosmos_database,
    container_name=cosmos_container,
)
speech_service = SpeechTokenService(
    secret_provider=secret_provider,
    speech_key_secret_name=secret_names["speech_key"],
    speech_region_secret_name=secret_names["speech_region"],
)
ner_extractor = AzureNerExtractor(endpoint=language_endpoint, key=language_key)

registration_dialog = RegistrationDialog(
    user_state=user_state,
    save_account=account_store.save,
    extract_entities=ner_extractor.extract,
)
bot = RegistrationBot(conversation_state, user_state, registration_dialog)

app.mount("/static", StaticFiles(directory="web"), name="static")


@app.get("/")
def root() -> FileResponse:
    return FileResponse("web/index.html")


@app.post("/api/messages")
async def messages(request: Request) -> Response:
    if "application/json" in request.headers.get("content-type", ""):
        body = await request.json()
    else:
        return Response(status_code=415)

    activity = Activity().deserialize(body)
    auth_header = request.headers.get("Authorization", "")

    try:
        response = await adapter.process_activity(activity, auth_header, bot.on_turn)
        if response:
            return JSONResponse(status_code=response.status, content=response.body)
        return Response(status_code=201)
    except Exception as exc:
        raise exc


# Bridge Endpoints for Web UI Prototype
@app.post("/api/chat/start")
async def start_session() -> dict[str, str]:
    return {
        "session_id": "web-session",
        "reply": "Willkommen! Ich lege mit dir einen neuen Account an. Wie lauten dein Vor- und Nachname?",
        "expected_field": "first_name"
    }


@app.post("/api/chat/message")
async def chat_message(request: Request) -> dict[str, Any]:
    body = await request.json()
    message = body.get("message", "")
    
    # Simple dummy bridge (Bot Framework should be used via /api/messages)
    return {
        "session_id": "web-session",
        "reply": "Nachricht empfangen. (Bitte nutze den /api/messages Endpunkt für die volle Bot Framework Erfahrung)",
        "completed": False
    }


@app.get("/api/admin/accounts")
def list_accounts() -> list[dict[str, object]]:
    return account_store.list_accounts()


@app.get("/api/speech/token")
def issue_speech_token() -> dict[str, str]:
    payload = speech_service.get_token()
    return {"token": payload.token, "region": payload.region}
