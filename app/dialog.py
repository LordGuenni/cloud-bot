from __future__ import annotations

import re
from typing import Callable

from .models import ChatResponse, SessionState
from .validation import (
    validate_birthdate,
    validate_city,
    validate_country,
    validate_email,
    validate_first_name,
    validate_house_number,
    validate_last_name,
    validate_phone,
    validate_postal_country_consistency,
    validate_postal_code,
    validate_street,
)

FIELD_ORDER = [
    "first_name",
    "last_name",
    "birthdate",
    "street",
    "house_number",
    "postal_code",
    "city",
    "country",
    "email",
    "phone",
]

ADDRESS_FIELDS = ("street", "house_number", "postal_code", "city", "country")

FIELD_PROMPTS = {
    "first_name": "Wie lauten dein Vor- und Nachname?",
    "last_name": "Wie lautet dein Nachname?",
    "birthdate": "Bitte nenne dein Geburtsdatum (TT.MM.JJJJ).",
    "email": "Fast geschafft. Unter welcher E-Mail-Adresse und Telefonnummer bist du erreichbar?",
    "phone": "Wie lautet deine Telefonnummer?",
    "street": "Bitte nenne deine vollständige Adresse (Straße Hausnummer, PLZ Ort, Land).",
    "house_number": "Wie lautet deine Hausnummer?",
    "postal_code": "Wie lautet deine Postleitzahl?",
    "city": "In welchem Ort wohnst du?",
    "country": "In welchem Land wohnst du?",
}

ADDRESS_FOLLOWUP_PROMPTS = {
    "street": "Ich konnte die Straße nicht erkennen. Wie lautet die Straße?",
    "house_number": "Ich konnte die Hausnummer nicht erkennen. Wie lautet die Hausnummer?",
    "postal_code": "Ich konnte die PLZ nicht erkennen. Wie lautet die Postleitzahl?",
    "city": "Ich konnte den Ort nicht erkennen. In welchem Ort wohnst du?",
    "country": "Ich konnte das Land nicht erkennen. In welchem Land wohnst du?",
}

FIELD_LABELS = {
    "first_name": "Vorname",
    "last_name": "Nachname",
    "birthdate": "Geburtsdatum",
    "email": "E-Mail",
    "phone": "Telefon",
    "street": "Straße",
    "house_number": "Hausnummer",
    "postal_code": "PLZ",
    "city": "Ort",
    "country": "Land",
}

VALIDATORS: dict[str, Callable[[str], str]] = {
    "first_name": validate_first_name,
    "last_name": validate_last_name,
    "birthdate": validate_birthdate,
    "email": validate_email,
    "phone": validate_phone,
    "street": validate_street,
    "house_number": validate_house_number,
    "postal_code": validate_postal_code,
    "city": validate_city,
    "country": validate_country,
}

FIELD_ALIASES = {
    "vorname": "first_name",
    "firstname": "first_name",
    "first name": "first_name",
    "nachname": "last_name",
    "lastname": "last_name",
    "last name": "last_name",
    "geburtsdatum": "birthdate",
    "birthdate": "birthdate",
    "e-mail": "email",
    "email": "email",
    "telefon": "phone",
    "phone": "phone",
    "straße": "street",
    "strasse": "street",
    "street": "street",
    "hausnummer": "house_number",
    "house number": "house_number",
    "plz": "postal_code",
    "postal": "postal_code",
    "postal code": "postal_code",
    "ort": "city",
    "stadt": "city",
    "city": "city",
    "land": "country",
    "country": "country",
}


EMAIL_CANDIDATE_REGEX = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_CANDIDATE_REGEX = re.compile(r"\+?[0-9][0-9 ()/-]{5,}[0-9]")
DATE_CANDIDATE_REGEX = re.compile(r"\b(?:\d{1,2}[./]\d{1,2}[./]\d{2,4}|\d{4}-\d{2}-\d{2})\b")


def _next_field(current_field: str) -> str | None:
    idx = FIELD_ORDER.index(current_field)
    if idx + 1 >= len(FIELD_ORDER):
        return None
    return FIELD_ORDER[idx + 1]


def _next_missing_field(values: dict[str, str], current_field: str) -> str | None:
    start_index = FIELD_ORDER.index(current_field) + 1
    for field in FIELD_ORDER[start_index:]:
        if not values.get(field):
            return field
    return None


def _next_missing_address_field(values: dict[str, str]) -> str | None:
    for field in ADDRESS_FIELDS:
        if not values.get(field):
            return field
    return None


def _build_summary(values: dict[str, str]) -> str:
    lines = [f"- {FIELD_LABELS[field]}: {values.get(field, '-')}" for field in FIELD_ORDER]
    return "Bitte bestätige die erfassten Daten:\n" + "\n".join(lines)


def _build_known_address_text(values: dict[str, str]) -> str:
    known = [f"{FIELD_LABELS[field]}: {values[field]}" for field in ADDRESS_FIELDS if values.get(field)]
    return ", ".join(known)


def _build_address_followup(values: dict[str, str], missing_field: str) -> str:
    known_address = _build_known_address_text(values)
    if not known_address:
        return ADDRESS_FOLLOWUP_PROMPTS[missing_field]
    return f"Ich habe bereits erkannt: {known_address}. {ADDRESS_FOLLOWUP_PROMPTS[missing_field]}"


def _validate_cross_field_plausibility(values: dict[str, str]) -> tuple[str, str] | None:
    postal = values.get("postal_code")
    country = values.get("country")
    if postal and country:
        try:
            validate_postal_country_consistency(postal, country)
        except ValueError as exc:
            return "postal_code", str(exc)
    return None


def _is_ambiguous_for_field(field: str, text: str) -> bool:
    lowered = text.lower()
    if " oder " in f" {lowered} ":
        return True
    if field == "email":
        return len(EMAIL_CANDIDATE_REGEX.findall(text)) > 1
    if field == "phone":
        return len(PHONE_CANDIDATE_REGEX.findall(text)) > 1
    if field == "birthdate":
        return len(DATE_CANDIDATE_REGEX.findall(text)) > 1
    return False


def _normalize_correction_target(text: str) -> str | None:
    cleaned = text.strip().lower()
    if cleaned in FIELD_ALIASES:
        return FIELD_ALIASES[cleaned]
    for alias, canonical in FIELD_ALIASES.items():
        if alias in cleaned:
            return canonical
    return None


def _build_account_payload(session: SessionState) -> dict[str, str]:
    address_line = f"{session.values['street']} {session.values['house_number']}"
    return {
        "first_name": session.values["first_name"],
        "last_name": session.values["last_name"],
        "birthdate": session.values["birthdate"],
        "email": session.values["email"],
        "phone": session.values["phone"],
        "address_line": address_line,
        "postal_code": session.values["postal_code"],
        "city": session.values["city"],
        "country": session.values["country"],
    }


def _extract_name_values(text: str, extracted_values: dict[str, str]) -> dict[str, str]:
    name_values: dict[str, str] = {}

    extracted_first = extracted_values.get("first_name")
    if extracted_first:
        try:
            name_values["first_name"] = validate_first_name(extracted_first)
        except ValueError:
            pass

    extracted_last = extracted_values.get("last_name")
    if extracted_last:
        try:
            name_values["last_name"] = validate_last_name(extracted_last)
        except ValueError:
            pass

    if "first_name" not in name_values or "last_name" not in name_values:
        parts = [part for part in re.split(r"\s+", text.strip()) if part]
        if len(parts) >= 2:
            if "first_name" not in name_values:
                try:
                    name_values["first_name"] = validate_first_name(parts[0])
                except ValueError:
                    pass
            if "last_name" not in name_values:
                try:
                    name_values["last_name"] = validate_last_name(" ".join(parts[1:]))
                except ValueError:
                    pass

    return name_values


def _can_directly_validate_address_field(field: str, text: str) -> bool:
    cleaned = text.strip()
    if not cleaned:
        return False
    if field == "street":
        return bool(
            re.search(
                r"\b(straße|strasse|str\.|weg|platz|allee|gasse|ufer|ring|damm|chaussee)\b",
                cleaned,
                re.IGNORECASE,
            )
        )
    return True


def initial_message() -> str:
    return (
        "Willkommen! Ich lege mit dir einen neuen Account an. "
        "Ich erfasse persönliche Daten, Kontakt und Adresse. "
        "Passwörter werden nicht abgefragt. "
        + FIELD_PROMPTS["first_name"]
    )


def handle_message(
    session: SessionState,
    user_message: str,
    save_account: Callable[[dict[str, str]], None],
    extract_entities: Callable[[str], dict[str, str]] | None = None,
) -> ChatResponse:
    text = user_message.strip()
    lowered = text.lower()

    if lowered in {"neustart", "restart"}:
        session.current_field = "first_name"
        session.values = {}
        session.awaiting_confirmation = False
        session.awaiting_correction_field = False
        return ChatResponse(
            session_id=session.session_id,
            reply="Alles klar, wir starten neu. " + FIELD_PROMPTS["first_name"],
            expected_field=session.current_field,
        )

    if session.awaiting_confirmation:
        if lowered in {"ja", "yes", "korrekt", "stimmt"}:
            account = _build_account_payload(session)
            save_account(account)
            session.awaiting_confirmation = False
            return ChatResponse(
                session_id=session.session_id,
                reply="Perfekt, dein Account wurde gespeichert.",
                expected_field=None,
                completed=True,
                account=account,
            )
        if lowered in {"nein", "no"}:
            session.awaiting_correction_field = True
            session.awaiting_confirmation = False
            return ChatResponse(
                session_id=session.session_id,
                reply="Kein Problem. Welches Feld soll ich korrigieren? (z. B. E-Mail, Telefonnummer, PLZ)",
                expected_field="correction_field",
            )
        return ChatResponse(
            session_id=session.session_id,
            reply="Bitte antworte mit 'Ja' oder 'Nein'.",
            expected_field="confirmation",
        )

    if session.awaiting_correction_field:
        target = _normalize_correction_target(text)
        if not target:
            return ChatResponse(
                session_id=session.session_id,
                reply="Das Feld habe ich nicht erkannt. Nenne bitte z. B. Vorname, E-Mail, Telefon oder PLZ.",
                expected_field="correction_field",
            )
        session.current_field = target
        session.awaiting_correction_field = False
        session.awaiting_confirmation = False
        return ChatResponse(
            session_id=session.session_id,
            reply=f"Okay, wir korrigieren {FIELD_LABELS[target]}. {FIELD_PROMPTS[target]}",
            expected_field=target,
        )

    extracted_values: dict[str, str] = {}
    if extract_entities:
        extracted_values = extract_entities(text)

    if session.current_field == "first_name":
        if _is_ambiguous_for_field("first_name", text):
            return ChatResponse(
                session_id=session.session_id,
                reply="Ich habe mehrere mögliche Namen erkannt. Bitte nenne genau einen Vor- und Nachnamen.",
                expected_field="first_name",
            )

        name_values = _extract_name_values(text, extracted_values)
        if not name_values:
            return ChatResponse(
                session_id=session.session_id,
                reply=f"Ich konnte Vor- und Nachname nicht sicher erkennen. {FIELD_PROMPTS['first_name']}",
                expected_field="first_name",
            )

        session.values.update(name_values)
        if not session.values.get("last_name"):
            session.current_field = "last_name"
            return ChatResponse(
                session_id=session.session_id,
                reply=FIELD_PROMPTS["last_name"],
                expected_field="last_name",
            )
        session.current_field = "birthdate"
        return ChatResponse(
            session_id=session.session_id,
            reply=FIELD_PROMPTS["birthdate"],
            expected_field="birthdate",
        )

    if session.current_field in ADDRESS_FIELDS:
        if _is_ambiguous_for_field(session.current_field, text):
            return ChatResponse(
                session_id=session.session_id,
                reply=f"Ich habe mehrere mögliche Angaben für {FIELD_LABELS[session.current_field]} erkannt. Bitte nenne genau einen Wert.",
                expected_field=session.current_field,
            )

        address_values: dict[str, str] = {}
        for field in ADDRESS_FIELDS:
            if extracted_values.get(field):
                try:
                    address_values[field] = VALIDATORS[field](extracted_values[field])
                except ValueError:
                    pass

        if session.current_field not in address_values and _can_directly_validate_address_field(
            session.current_field, text
        ):
            try:
                address_values[session.current_field] = VALIDATORS[session.current_field](text)
            except ValueError:
                pass

        if not address_values:
            if session.current_field == "street":
                return ChatResponse(
                    session_id=session.session_id,
                    reply=(
                        "Ich konnte keine Adresskomponente erkennen. "
                        "Nenne gerne eine einzelne Komponente oder gib alles im Format "
                        "'Straße Hausnummer, PLZ Ort, Land' an."
                    ),
                    expected_field="street",
                )
            return ChatResponse(
                session_id=session.session_id,
                reply=_build_address_followup(session.values, session.current_field),
                expected_field=session.current_field,
            )

        session.values.update(address_values)
        plausibility_error = _validate_cross_field_plausibility(session.values)
        if plausibility_error:
            field, message = plausibility_error
            session.current_field = field
            return ChatResponse(
                session_id=session.session_id,
                reply=f"{message} {FIELD_PROMPTS[field]}",
                expected_field=field,
            )

        missing_address = _next_missing_address_field(session.values)
        if missing_address:
            session.current_field = missing_address
            return ChatResponse(
                session_id=session.session_id,
                reply=_build_address_followup(session.values, missing_address),
                expected_field=missing_address,
            )
        next_field = _next_missing_field(session.values, "country")
        if next_field:
            session.current_field = next_field
            return ChatResponse(
                session_id=session.session_id,
                reply=FIELD_PROMPTS[next_field],
                expected_field=next_field,
            )
        session.awaiting_confirmation = True
        return ChatResponse(
            session_id=session.session_id,
            reply=_build_summary(session.values) + "\nSind die Daten korrekt? (Ja/Nein)",
            expected_field="confirmation",
        )

    for field, value in extracted_values.items():
        if field not in VALIDATORS:
            continue
        if field in session.values and field != session.current_field:
            continue
        try:
            session.values[field] = VALIDATORS[field](value)
        except ValueError:
            continue

    if _is_ambiguous_for_field(session.current_field, text):
        return ChatResponse(
            session_id=session.session_id,
            reply=f"Ich habe mehrere mögliche Angaben für {FIELD_LABELS[session.current_field]} erkannt. Bitte nenne genau einen Wert.",
            expected_field=session.current_field,
        )

    validator = VALIDATORS[session.current_field]
    value_to_validate = extracted_values.get(session.current_field, text)
    try:
        validated = validator(value_to_validate)
    except ValueError as exc:
        if value_to_validate != text:
            try:
                validated = validator(text)
            except ValueError:
                return ChatResponse(
                    session_id=session.session_id,
                    reply=f"{exc} {FIELD_PROMPTS[session.current_field]}",
                    expected_field=session.current_field,
                )
        else:
            return ChatResponse(
                session_id=session.session_id,
                reply=f"{exc} {FIELD_PROMPTS[session.current_field]}",
                expected_field=session.current_field,
            )

    session.values[session.current_field] = validated
    next_field = _next_missing_field(session.values, session.current_field)
    if next_field:
        session.current_field = next_field
        return ChatResponse(
            session_id=session.session_id,
            reply=FIELD_PROMPTS[next_field],
            expected_field=next_field,
        )

    session.awaiting_confirmation = True
    return ChatResponse(
        session_id=session.session_id,
        reply=_build_summary(session.values) + "\nSind die Daten korrekt? (Ja/Nein)",
        expected_field="confirmation",
    )
