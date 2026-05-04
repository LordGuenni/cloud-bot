#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


@dataclass
class CredentialBundle:
    endpoint: str
    key: str


def run_az(args: list[str], expect_json: bool = True) -> Any:
    command = ["az", *args]
    if expect_json:
        command.extend(["-o", "json"])

    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())

    if not expect_json:
        return completed.stdout.strip()

    return json.loads(completed.stdout or "null")


def parse_vault_name(vault_uri: str) -> str:
    host = urlparse(vault_uri).netloc
    if not host:
        raise ValueError(f"Ungültige Vault-URI: {vault_uri}")
    return host.split(".")[0]


def load_config(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def read_secret(vault_name: str, secret_name: str) -> str:
    response = run_az(
        [
            "keyvault",
            "secret",
            "show",
            "--vault-name",
            vault_name,
            "--name",
            secret_name,
            "--query",
            "value",
        ],
        expect_json=False,
    )
    return response.strip()


def get_language_credentials(config: dict[str, Any]) -> CredentialBundle:
    secret_names = config.get("key_vault_secret_names", {})
    endpoint_secret = secret_names.get("language_endpoint")
    key_secret = secret_names.get("language_key")
    vault_uri = config.get("key_vault_uri")

    if not vault_uri:
        raise ValueError("key_vault_uri fehlt in config.json")
    if not endpoint_secret or not key_secret:
        raise ValueError("Secret-Namen für language_endpoint/language_key fehlen in config.json")

    vault_name = parse_vault_name(vault_uri)
    endpoint = read_secret(vault_name, endpoint_secret).strip().strip('"').strip("'")
    key = read_secret(vault_name, key_secret).strip().strip('"').strip("'")

    if not endpoint or not key:
        raise ValueError("language_endpoint oder language_key ist leer")

    return CredentialBundle(endpoint=endpoint, key=key)


def normalize_and_append(target: list[str], value: str) -> None:
    cleaned = value.strip()
    if cleaned and cleaned not in target:
        target.append(cleaned)


def extract_username_from_text(text: str) -> list[str]:
    patterns = [
        r"(?:username|user\s*name|benutzername)\s*(?:ist|is|:|=)?\s*([A-Za-z0-9._-]{3,32})",
        r"(?:mein|my)\s+(?:username|benutzername)\s*(?:ist|is|:|=)?\s*([A-Za-z0-9._-]{3,32})",
    ]
    results: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            normalize_and_append(results, match.group(1))
    return results


def classify_entities(text: str, endpoint: str, key: str) -> dict[str, Any]:
    try:
        from azure.ai.textanalytics import TextAnalyticsClient
        from azure.core.credentials import AzureKeyCredential
    except ImportError as exc:
        raise RuntimeError(
            "Fehlende Abhängigkeit: installiere mit 'pip install azure-ai-textanalytics'"
        ) from exc

    client = TextAnalyticsClient(endpoint=endpoint, credential=AzureKeyCredential(key))
    docs = [text]

    general_result = client.recognize_entities(docs)[0]
    pii_result = client.recognize_pii_entities(docs)[0]

    if general_result.is_error:
        raise RuntimeError(f"Entity Recognition Fehler: {general_result.error}")
    if pii_result.is_error:
        raise RuntimeError(f"PII Recognition Fehler: {pii_result.error}")

    output = {
        "input_text": text,
        "username": extract_username_from_text(text),
        "first_name": [],
        "last_name": [],
        "full_name": [],
        "email": [],
        "phone": [],
        "address": [],
        "city": [],
        "postal_code": [],
        "country": [],
        "birthdate": [],
        "raw_entities": [],
        "raw_pii_entities": [],
    }

    for entity in general_result.entities:
        record = {
            "text": entity.text,
            "category": entity.category,
            "subcategory": entity.subcategory,
            "confidence_score": round(entity.confidence_score, 3),
        }
        output["raw_entities"].append(record)

        if entity.category == "Person":
            normalize_and_append(output["full_name"], entity.text)
        elif entity.category == "Location":
            if entity.subcategory == "City":
                normalize_and_append(output["city"], entity.text)
            elif entity.subcategory == "CountryRegion":
                normalize_and_append(output["country"], entity.text)
        elif entity.category == "Address":
            normalize_and_append(output["address"], entity.text)
        elif entity.category == "DateTime":
            normalize_and_append(output["birthdate"], entity.text)

    for pii in pii_result.entities:
        pii_record = {
            "text": pii.text,
            "category": pii.category,
            "subcategory": pii.subcategory,
            "confidence_score": round(pii.confidence_score, 3),
        }
        output["raw_pii_entities"].append(pii_record)

        if pii.category == "Email":
            normalize_and_append(output["email"], pii.text)
        elif pii.category == "PhoneNumber":
            normalize_and_append(output["phone"], pii.text)
        elif pii.category == "Address":
            normalize_and_append(output["address"], pii.text)
        elif pii.category in {"Date", "DateTime"}:
            normalize_and_append(output["birthdate"], pii.text)

    usernames_lower = {value.lower() for value in output["username"]}
    output["full_name"] = [
        value
        for value in output["full_name"]
        if value.lower() not in usernames_lower
    ]

    # Lightweight name split heuristic for typical "Vorname Nachname"
    for name in output["full_name"]:
        parts = [part for part in re.split(r"\s+", name.strip()) if part]
        if len(parts) >= 2:
            normalize_and_append(output["first_name"], parts[0])
            normalize_and_append(output["last_name"], " ".join(parts[1:]))

    # Postal code fallback using regex
    for match in re.finditer(r"\b\d{5}\b", text):
        normalize_and_append(output["postal_code"], match.group(0))

    return output


def get_input_text(args: argparse.Namespace) -> str:
    if args.text:
        return args.text
    if args.text_file:
        with open(args.text_file, "r", encoding="utf-8") as file:
            return file.read().strip()
    raise ValueError("Bitte --text oder --text-file angeben.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Testet Azure Language NER/PII mit einem Freitext und klassifiziert Registrierungsfelder."
    )
    parser.add_argument("--config", default="config.json", help="Pfad zur Konfigurationsdatei")
    parser.add_argument("--text", default="", help="Direkter Eingabetext")
    parser.add_argument("--text-file", default="", help="Pfad zu einer Textdatei")
    parser.add_argument("--raw", action="store_true", help="Raw-Entities mit ausgeben")
    args = parser.parse_args()

    try:
        input_text = get_input_text(args)
        config = load_config(args.config)
        creds = get_language_credentials(config)
        result = classify_entities(input_text, creds.endpoint, creds.key)

        if not args.raw:
            result.pop("raw_entities", None)
            result.pop("raw_pii_entities", None)

        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
