from __future__ import annotations

import re
import logging
from dataclasses import dataclass

from azure.ai.textanalytics import TextAnalyticsClient
from azure.core.credentials import AzureKeyCredential
from azure.identity import ManagedIdentityCredential, DefaultAzureCredential

from .validation import parse_full_address

logger = logging.getLogger(__name__)

class AzureNerExtractor:
    MIN_GENERAL_CONFIDENCE = 0.6
    MIN_PII_CONFIDENCE = 0.6

    def __init__(self, endpoint: str, key: str | None = None) -> None:
        self.endpoint = endpoint
        if key and len(key) > 5:
            logger.info(f"AzureNerExtractor: Initializing with API Key (length: {len(key)})")
            self.credential = AzureKeyCredential(key)
        else:
            logger.info("AzureNerExtractor: No API Key provided or too short. Using DefaultAzureCredential.")
            self.credential = DefaultAzureCredential()
            
        self.client = TextAnalyticsClient(
            endpoint=endpoint,
            credential=self.credential,
        )

    def extract(self, text: str) -> dict[str, str]:
        if not self.client:
            raise RuntimeError("Azure AI Language Client ist nicht initialisiert.")
            
        try:
            logger.debug(f"AzureNerExtractor: Requesting entities for text: '{text[:50]}...'")
            docs = [text]
            response = self.client.recognize_entities(docs)
            if not response or len(response) == 0:
                logger.warning("AzureNerExtractor: Empty response from recognize_entities.")
                return {}
            general = response[0]
            
            pii_response = self.client.recognize_pii_entities(docs)
            pii = pii_response[0] if pii_response else None
            logger.info("AzureNerExtractor: Successfully received entities from Azure.")
        except Exception as exc:
            error_msg = str(exc)
            logger.error(f"AzureNerExtractor: SDK Error: {error_msg}")
            if "Authorization" in error_msg:
                error_msg += f" | Auth-Method: {'Key' if isinstance(self.credential, AzureKeyCredential) else 'Identity'}"
            raise RuntimeError(f"Azure SDK Fehler: {error_msg}") from exc

        if general.is_error:
            raise RuntimeError(f"Azure NER error: {general.error}")
        if pii.is_error:
            raise RuntimeError(f"Azure PII error: {pii.error}")

        values: dict[str, str] = {}
        full_name = ""
        address_hint = ""

        for entity in general.entities:
            if entity.confidence_score < self.MIN_GENERAL_CONFIDENCE:
                continue
            if entity.category == "Person" and not full_name:
                full_name = entity.text.strip()
            elif entity.category == "Location" and entity.subcategory == "City" and "city" not in values:
                values["city"] = entity.text.strip()
            elif (
                entity.category == "Location"
                and entity.subcategory == "CountryRegion"
                and "country" not in values
            ):
                values["country"] = entity.text.strip()
            elif entity.category == "Address" and not address_hint:
                address_hint = entity.text.strip()
            elif entity.category == "DateTime" and "birthdate" not in values:
                values["birthdate"] = entity.text.strip()

        for entity in pii.entities:
            if entity.confidence_score < self.MIN_PII_CONFIDENCE:
                continue
            if entity.category == "Email" and "email" not in values:
                values["email"] = entity.text.strip()
            elif entity.category == "PhoneNumber" and "phone" not in values:
                values["phone"] = entity.text.strip()
            elif entity.category == "Address" and not address_hint:
                address_hint = entity.text.strip()
            elif entity.category in {"Date", "DateTime"} and "birthdate" not in values:
                values["birthdate"] = entity.text.strip()

        if full_name:
            parts = [part for part in re.split(r"\s+", full_name) if part]
            if len(parts) >= 2:
                values.setdefault("first_name", parts[0])
                values.setdefault("last_name", " ".join(parts[1:]))

        if any(key in values for key in ("city", "country")) or address_hint:
            for match in re.finditer(r"\b\d{4,10}\b", text):
                values.setdefault("postal_code", match.group(0))

        address_source = address_hint or text
        values.update({k: v for k, v in parse_full_address(address_source).items() if v})
        if address_hint and address_hint != text:
            values.update({k: v for k, v in parse_full_address(text).items() if v})

        return values
