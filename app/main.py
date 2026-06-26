from __future__ import annotations

import asyncio
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response, Header
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
from .storage import CosmosAccountStore, FileStorage
from .models import UserProfile

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

# Bridge Adapter for Local Web UI (unauthenticated)
bridge_adapter = BotFrameworkAdapter(BotFrameworkAdapterSettings("", ""))

# Storage & State
storage = FileStorage()
user_state = UserState(storage)
conversation_state = ConversationState(storage)
user_profile_accessor = user_state.create_property("UserProfile")

cosmos_endpoint = secret_provider.get_secret(secret_names["cosmos_endpoint"])
if not cosmos_endpoint:
    raise RuntimeError(f"Konnte 'cosmos_endpoint' nicht aus Key Vault ({app_config.key_vault_uri}) laden.")

cosmos_key = secret_provider.get_secret(secret_names["cosmos_key"])
cosmos_database = secret_provider.get_secret(secret_names["cosmos_database"])
cosmos_container = secret_provider.get_secret(secret_names["cosmos_container"])

language_endpoint = secret_provider.get_secret(secret_names["language_endpoint"])
language_key = secret_provider.get_secret(secret_names["language_key"])
if not language_key:
    raise RuntimeError(f"Konnte 'language_key' nicht aus Key Vault ({app_config.key_vault_uri}) laden.")

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


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    return FileResponse("web/favicon.svg")


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


@app.post("/api/chat/start")
async def start_session() -> dict[str, str]:
    import uuid
    session_id = str(uuid.uuid4())
    
    return {
        "session_id": session_id,
        "reply": "Willkommen! Ich lege mit dir einen neuen Account an. Wie lauten dein Vor- und Nachname?",
        "expected_field": "first_name"
    }


@app.post("/api/chat/message")
async def chat_message(request: Request) -> dict[str, Any]:
    body = await request.json()
    user_text = body.get("message", "")
    session_id = body.get("session_id", "web-session")
    client_profile = body.get("user_profile")
    responses = []
    user_profile_data = {}

    # Middleware-like function to capture bot responses
    async def capture_responses(context, next_turn):
        original_send_activities = context.send_activities
        async def hooked_send_activities(activities):
            for activity in activities:
                if activity.type == "message":
                    responses.append(activity.text)
            return await original_send_activities(activities)
        context.send_activities = hooked_send_activities
        await next_turn()

    from botbuilder.schema import ActivityTypes, ChannelAccount
    activity = Activity(
        type=ActivityTypes.message,
        text=user_text,
        from_property=ChannelAccount(id=f"user-{session_id}", name="User"),
        recipient=ChannelAccount(id="bot", name="Bot"),
        conversation=ChannelAccount(id=f"conv-{session_id}"),
        service_url="http://localhost",
        channel_id="emulator"
    )

    try:
        async def turn_wrapper(context):
            # Intercept responses and prevent the adapter from trying to POST them back to a non-existent network endpoint
            async def hooked_send_activities(activities):
                from botbuilder.schema import ResourceResponse
                resource_responses = []
                for act in activities:
                    if act.type == "message":
                        responses.append(act.text)
                    resource_responses.append(ResourceResponse(id=act.id or "web-res"))
                return resource_responses
            
            context.send_activities = hooked_send_activities
            
            # Sync client-side user profile if server-side state is empty
            profile = await user_profile_accessor.get(context, UserProfile)
            if client_profile and isinstance(client_profile, dict):
                for k, v in client_profile.items():
                    if v and hasattr(profile, k) and not getattr(profile, k):
                        setattr(profile, k, v)
            
            await bot.on_turn(context)
            
            # Populate updated profile data to return to the client
            profile = await user_profile_accessor.get(context, UserProfile)
            if profile:
                user_profile_data.update({
                    "first_name": profile.first_name,
                    "last_name": profile.last_name,
                    "birthdate": profile.birthdate,
                    "street": profile.street,
                    "house_number": profile.house_number,
                    "postal_code": profile.postal_code,
                    "city": profile.city,
                    "country": profile.country,
                    "email": profile.email,
                    "phone": profile.phone
                })

        # Use bridge_adapter (no auth) instead of the main adapter
        await bridge_adapter.process_activity(activity, "", turn_wrapper)
        reply_text = " ".join(responses) if responses else "Ich habe dich leider nicht verstanden."
        
        return {
            "session_id": session_id,
            "reply": reply_text,
            "completed": "gespeichert" in reply_text.lower(),
            "profile": user_profile_data
        }
    except Exception as exc:
        full_error = f"{str(exc)} | Endpunkt: {language_endpoint}"
        return {
            "session_id": session_id,
            "reply": f"SYSTEM-DIAGNOSE: {full_error}",
            "completed": False
        }


import json
import jwt
from jwt.algorithms import RSAAlgorithm
import httpx

# Load tenant_id from environment variable or fallback to config.json, otherwise "common"
import os
tenant_id = os.environ.get("TENANT_ID", "")
if not tenant_id:
    try:
        config_path = os.environ.get("BOT_CONFIG_PATH", "config.json")
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
                val = config_data.get("tenant_id", "")
                if val:
                    tenant_id = val
    except Exception:
        pass
if not tenant_id:
    tenant_id = "common"

class EntraIdTokenValidator:
    def __init__(self, tenant_id: str, client_id: str):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.jwks_url = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
        self.keys = []

    async def _fetch_keys(self):
        if not self.keys:
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(self.jwks_url, timeout=5.0)
                    self.keys = resp.json().get("keys", [])
            except Exception as e:
                print(f"Error fetching JWKS keys: {e}")
                self.keys = []

    async def validate_token(self, token: str) -> bool:
        if not self.client_id:
            # Bypass validation in local development without Client ID
            print("WARNING: Microsoft App ID is empty. Bypassing Entra ID token validation.")
            return True
            
        try:
            await self._fetch_keys()
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get("kid")
            
            key_data = next((k for k in self.keys if k["kid"] == kid), None)
            if not key_data:
                print("Error: kid not found in JWKS.")
                return False
                
            public_key = RSAAlgorithm.from_jwk(key_data)
            
            # Verify token signature, audience, and issuer
            # Note: MSAL.js idTokens use v2.0 endpoint by default
            jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                audience=self.client_id,
                issuer=f"https://login.microsoftonline.com/{self.tenant_id}/v2.0"
            )
            return True
        except Exception as exc:
            print(f"Token validation failed: {exc}")
            return False

# Instantiate validator
token_validator = EntraIdTokenValidator(tenant_id=tenant_id, client_id=app_id)


@app.get("/api/admin/config")
def get_admin_config() -> dict[str, str]:
    return {
        "client_id": app_id,
        "tenant_id": tenant_id
    }


@app.get("/api/admin/accounts")
async def list_accounts(authorization: str | None = Header(default=None)) -> list[dict[str, object]]:
    if not token_validator.client_id:
        # If no client ID is configured, bypass authentication for local testing
        return account_store.list_accounts()
        
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
        
    token = authorization.split(" ")[1]
    is_valid = await token_validator.validate_token(token)
    if not is_valid:
        raise HTTPException(status_code=401, detail="Entra ID Token-Validierung fehlgeschlagen")
        
    return account_store.list_accounts()


@app.post("/api/admin/accounts/update")
async def update_account(request: Request, authorization: str | None = Header(default=None)) -> dict[str, str]:
    if token_validator.client_id:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
        token = authorization.split(" ")[1]
        is_valid = await token_validator.validate_token(token)
        if not is_valid:
            raise HTTPException(status_code=401, detail="Entra ID Token-Validierung fehlgeschlagen")
            
    body = await request.json()
    if "id" not in body:
        raise HTTPException(status_code=400, detail="Account ID fehlt")
        
    try:
        account_store.update(body)
        return {"status": "success", "message": "Account erfolgreich aktualisiert"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/admin/accounts/delete")
async def delete_account(request: Request, authorization: str | None = Header(default=None)) -> dict[str, str]:
    if token_validator.client_id:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
        token = authorization.split(" ")[1]
        is_valid = await token_validator.validate_token(token)
        if not is_valid:
            raise HTTPException(status_code=401, detail="Entra ID Token-Validierung fehlgeschlagen")
            
    body = await request.json()
    account_id = body.get("id")
    email = body.get("email")
    
    if not account_id or not email:
        raise HTTPException(status_code=400, detail="Account ID und E-Mail (Partition Key) sind erforderlich")
        
    try:
        account_store.delete(account_id, email)
        return {"status": "success", "message": "Account erfolgreich gelöscht"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/speech/token")
def issue_speech_token() -> dict[str, str]:
    payload = speech_service.get_token()
    return {"token": payload.token, "region": payload.region}
