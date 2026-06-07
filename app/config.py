from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlparse

from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient


@dataclass(frozen=True)
class AppConfig:
    key_vault_uri: str
    key_vault_secret_names: dict[str, str]


def load_app_config(path: str | None = None) -> AppConfig:
    config_path = path or os.environ.get("BOT_CONFIG_PATH", "config.json")
    
    # Default mappings if file is missing
    default_secret_names = {
        "speech_key": "speech-key",
        "speech_region": "speech-region",
        "cosmos_endpoint": "cosmos-endpoint",
        "cosmos_key": "cosmos-key",
        "cosmos_database": "cosmos-database",
        "cosmos_container": "cosmos-container",
        "language_endpoint": "language-endpoint",
        "language_key": "language-key",
        "microsoft_app_id": "microsoft-app-id",
        "microsoft_app_password": "microsoft-app-password"
    }

    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as file:
            payload = json.load(file)
        return AppConfig(
            key_vault_uri=payload.get("key_vault_uri", os.environ.get("KEY_VAULT_URI", "")),
            key_vault_secret_names=payload.get("key_vault_secret_names", default_secret_names)
        )
    
    # Fallback to Environment Variables (for Azure)
    kv_uri = os.environ.get("KEY_VAULT_URI")
    if not kv_uri:
        raise ValueError("Weder config.json noch Umgebungsvariable KEY_VAULT_URI gefunden.")
    
    return AppConfig(key_vault_uri=kv_uri, key_vault_secret_names=default_secret_names)


class KeyVaultSecretProvider:
    def __init__(self, key_vault_uri: str) -> None:
        if not key_vault_uri:
            raise ValueError("Key Vault URI ist leer.")
        credential = DefaultAzureCredential(exclude_interactive_browser_credential=False)
        self.client = SecretClient(vault_url=key_vault_uri, credential=credential)

    @lru_cache(maxsize=64)
    def get_secret(self, secret_name: str) -> str:
        if not secret_name:
            return ""
        try:
            value = self.client.get_secret(secret_name).value
            return value.strip().strip('"').strip("'") if value else ""
        except Exception:
            # Fallback to env var if secret not in vault or vault access fails
            return os.environ.get(secret_name.upper().replace("-", "_"), "")
