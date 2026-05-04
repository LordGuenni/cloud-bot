from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import KeyVaultSecretProvider, load_app_config
from .dialog import handle_message, initial_message
from .models import ChatRequest, ChatResponse, StartSessionResponse
from .ner import AzureNerExtractor
from .speech import SpeechTokenService
from .storage import CosmosAccountStore, SessionStore

app = FastAPI(title="Registration Voice/Chat Bot")

session_store = SessionStore()
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

app.mount("/static", StaticFiles(directory="web"), name="static")


@app.get("/")
def root() -> FileResponse:
    return FileResponse("web/index.html")


@app.post("/api/chat/start", response_model=StartSessionResponse)
def start_session() -> StartSessionResponse:
    session = session_store.create()
    return StartSessionResponse(
        session_id=session.session_id,
        reply=initial_message(),
        expected_field=session.current_field,
    )


@app.post("/api/chat/message", response_model=ChatResponse)
def chat_message(request: ChatRequest) -> ChatResponse:
    session = session_store.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session nicht gefunden.")
    try:
        return handle_message(
            session,
            request.message,
            save_account=account_store.save,
            extract_entities=ner_extractor.extract,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Azure Language NER konnte nicht ausgeführt werden: {exc}",
        ) from exc


@app.get("/api/admin/accounts")
def list_accounts() -> list[dict[str, object]]:
    return account_store.list_accounts()


@app.get("/api/speech/token")
def issue_speech_token() -> dict[str, str]:
    payload = speech_service.get_token()
    return {"token": payload.token, "region": payload.region}
