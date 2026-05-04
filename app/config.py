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


def parse_vault_name(vault_uri: str) -> str:
    host = urlparse(vault_uri).netloc
    if not host:
        raise ValueError(f"Ungültige Vault-URI: {vault_uri}")
    return host.split(".")[0]


def load_app_config(path: str | None = None) -> AppConfig:
    config_path = path or os.environ.get("BOT_CONFIG_PATH", "config.json")
    with open(config_path, "r", encoding="utf-8") as file:
        payload = json.load(file)
    key_vault_uri = payload.get("key_vault_uri")
    if not key_vault_uri:
        raise ValueError("key_vault_uri fehlt in config.json")
    secret_names = payload.get("key_vault_secret_names", {})
    if not isinstance(secret_names, dict):
        raise ValueError("key_vault_secret_names muss ein Objekt sein")
    return AppConfig(key_vault_uri=key_vault_uri, key_vault_secret_names=secret_names)


class KeyVaultSecretProvider:
    def __init__(self, key_vault_uri: str) -> None:
        credential = DefaultAzureCredential(exclude_interactive_browser_credential=False)
        self.client = SecretClient(vault_url=key_vault_uri, credential=credential)

    @lru_cache(maxsize=64)
    def get_secret(self, secret_name: str) -> str:
        if not secret_name:
            raise ValueError("Secret-Name fehlt")
        value = self.client.get_secret(secret_name).value
        if not value:
            raise ValueError(f"Secret '{secret_name}' ist leer")
        return value.strip().strip('"').strip("'")

