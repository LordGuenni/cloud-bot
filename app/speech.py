from __future__ import annotations

import time
import urllib.request
from dataclasses import dataclass

from .config import KeyVaultSecretProvider


@dataclass
class SpeechTokenPayload:
    token: str
    region: str


class SpeechTokenService:
    def __init__(
        self,
        secret_provider: KeyVaultSecretProvider,
        speech_key_secret_name: str,
        speech_region_secret_name: str,
    ) -> None:
        self.secret_provider = secret_provider
        self.speech_key_secret_name = speech_key_secret_name
        self.speech_region_secret_name = speech_region_secret_name
        self._cached_token: str | None = None
        self._cached_region: str | None = None
        self._expires_at: float = 0.0

    def get_token(self) -> SpeechTokenPayload:
        now = time.time()
        if self._cached_token and self._cached_region and now < self._expires_at:
            return SpeechTokenPayload(token=self._cached_token, region=self._cached_region)

        key = self.secret_provider.get_secret(self.speech_key_secret_name)
        region = self.secret_provider.get_secret(self.speech_region_secret_name)
        token_endpoint = f"https://{region}.api.cognitive.microsoft.com/sts/v1.0/issueToken"

        request = urllib.request.Request(
            token_endpoint,
            method="POST",
            headers={"Ocp-Apim-Subscription-Key": key, "Content-Length": "0"},
            data=b"",
        )

        with urllib.request.urlopen(request, timeout=10) as response:
            token = response.read().decode("utf-8")

        self._cached_token = token
        self._cached_region = region
        self._expires_at = now + 9 * 60
        return SpeechTokenPayload(token=token, region=region)

