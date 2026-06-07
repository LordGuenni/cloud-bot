from __future__ import annotations

import re
import logging
import httpx
from dataclasses import dataclass
from azure.identity import DefaultAzureCredential

from .validation import parse_full_address

logger = logging.getLogger(__name__)

class AzureNerExtractor:
    def __init__(self, endpoint: str, key: str | None = None) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.key = key
        self.credential = DefaultAzureCredential()

    def extract(self, text: str) -> dict[str, str]:
        # URL for Entity Recognition (matches the successful az rest call)
        url = f"{self.endpoint}/language/:analyze-text?api-version=2023-04-01"
        
        headers = {"Content-Type": "application/json"}
        if self.key:
            headers["Ocp-Apim-Subscription-Key"] = self.key
        else:
            # Use Managed Identity token if no key is provided
            token_obj = self.credential.get_token("https://cognitiveservices.azure.com/.default")
            headers["Authorization"] = f"Bearer {token_obj.token}"

        payload = {
            "kind": "EntityRecognition",
            "analysisInput": {
                "documents": [{"id": "1", "text": text, "language": "de"}]
            }
        }

        try:
            with httpx.Client() as client:
                response = client.post(url, headers=headers, json=payload, timeout=10.0)
                response.raise_for_status()
                data = response.json()
                
            # Fallback for PII
            pii_payload = dict(payload)
            pii_payload["kind"] = "PiiEntityRecognition"
            with httpx.Client() as client:
                pii_resp = client.post(url, headers=headers, json=pii_payload, timeout=10.0)
                pii_resp.raise_for_status()
                pii_data = pii_resp.json()
        except Exception as exc:
            logger.error(f"Azure REST API Fehler: {exc}")
            # This is the NEW error format that MUST show up if the code is running
            raise RuntimeError(f"REST_API_ERROR: {exc}")

        values: dict[str, str] = {}
        full_name = ""
        address_hint = ""

        # Process Entity Recognition
        doc = data.get("results", {}).get("documents", [{}])[0]
        for entity in doc.get("entities", []):
            cat = entity.get("category")
            sub = entity.get("subcategory")
            val = entity.get("text")
            
            if cat == "Person" and not full_name:
                full_name = val
            elif cat == "Location" and sub == "City":
                values["city"] = val
            elif cat == "Location" and sub == "CountryRegion":
                values["country"] = val
            elif cat == "Address":
                address_hint = val
            elif cat == "DateTime" and "birthdate" not in values:
                values["birthdate"] = val

        # Process PII Recognition
        pii_doc = pii_data.get("results", {}).get("documents", [{}])[0]
        for entity in pii_doc.get("entities", []):
            cat = entity.get("category")
            val = entity.get("text")
            if cat == "Email":
                values["email"] = val
            elif cat == "PhoneNumber":
                values["phone"] = val

        if full_name:
            parts = [part for part in re.split(r"\s+", full_name) if part]
            if len(parts) >= 2:
                values.setdefault("first_name", parts[0])
                values.setdefault("last_name", " ".join(parts[1:]))

        address_source = address_hint or text
        values.update({k: v for k, v in parse_full_address(address_source).items() if v})
        
        return values
