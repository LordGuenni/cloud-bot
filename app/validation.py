from __future__ import annotations

import re
from datetime import datetime

DATE_FORMATS = ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y")
EMAIL_REGEX = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
PHONE_REGEX = re.compile(r"^\+?[0-9 ()/-]{7,25}$")
POSTAL_REGEX = re.compile(r"^\d{4,10}$")
HOUSE_NUMBER_REGEX = re.compile(r"^[0-9A-Za-z\-\/]{1,10}$")
PERSON_TEXT_REGEX = re.compile(r"^[A-Za-zÄÖÜäöüß .'-]{2,80}$")
LOCATION_TEXT_REGEX = re.compile(r"^[A-Za-zÄÖÜäöüß .'-]{2,80}$")
GERMANY_ALIASES = {"de", "deutschland", "germany", "deutsch"}
AUSTRIA_ALIASES = {"at", "österreich", "austria", "oesterreich"}
SWITZERLAND_ALIASES = {"ch", "schweiz", "switzerland"}


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def validate_first_name(value: str) -> str:
    cleaned = _normalize_text(value)
    if not PERSON_TEXT_REGEX.match(cleaned):
        raise ValueError("Der Vorname sieht ungültig aus.")
    return cleaned


def validate_last_name(value: str) -> str:
    cleaned = _normalize_text(value)
    if not PERSON_TEXT_REGEX.match(cleaned):
        raise ValueError("Der Nachname sieht ungültig aus.")
    return cleaned


def validate_birthdate(value: str) -> str:
    cleaned = _normalize_text(value)
    for fmt in DATE_FORMATS:
        try:
            parsed = datetime.strptime(cleaned, fmt)
            if parsed > datetime.now():
                raise ValueError("Das Geburtsdatum darf nicht in der Zukunft liegen.")
            age = (datetime.now().date() - parsed.date()).days // 365
            if age < 14:
                raise ValueError("Das Geburtsdatum ist unplausibel (Mindestalter 14 Jahre).")
            if age > 120:
                raise ValueError("Das Geburtsdatum ist unplausibel (älter als 120 Jahre).")
            return parsed.strftime("%Y-%m-%d")
        except ValueError as exc:
            if "Zukunft" in str(exc) or "unplausibel" in str(exc):
                raise
            continue
    raise ValueError("Bitte gib das Geburtsdatum z. B. als TT.MM.JJJJ an.")


def validate_email(value: str) -> str:
    cleaned = _normalize_text(value).lower()
    if not EMAIL_REGEX.match(cleaned):
        raise ValueError("Die E-Mail hat kein gültiges Format.")
    return cleaned


def validate_phone(value: str) -> str:
    cleaned = _normalize_text(value)
    if not PHONE_REGEX.match(cleaned):
        raise ValueError("Die Telefonnummer hat kein gültiges Format.")
    digits = re.sub(r"\D", "", cleaned)
    if len(digits) < 7 or len(digits) > 15:
        raise ValueError("Die Telefonnummer hat kein gültiges Format.")
    return cleaned


def validate_street(value: str) -> str:
    cleaned = _normalize_text(value)
    if len(cleaned) < 2:
        raise ValueError("Bitte nenne eine Straße mit mindestens 2 Zeichen.")
    return cleaned


def validate_house_number(value: str) -> str:
    cleaned = _normalize_text(value)
    if not HOUSE_NUMBER_REGEX.match(cleaned):
        raise ValueError("Die Hausnummer ist ungültig.")
    return cleaned


def validate_postal_code(value: str) -> str:
    cleaned = _normalize_text(value)
    if not POSTAL_REGEX.match(cleaned):
        raise ValueError("Die PLZ muss aus 4 bis 10 Ziffern bestehen.")
    return cleaned


def validate_city(value: str) -> str:
    cleaned = _normalize_text(value)
    if not LOCATION_TEXT_REGEX.match(cleaned):
        raise ValueError("Bitte gib einen gültigen Ort an.")
    return cleaned


def validate_country(value: str) -> str:
    cleaned = _normalize_text(value)
    if len(cleaned) == 2 and cleaned.isalpha():
        return cleaned.upper()
    if len(cleaned) < 4 or not LOCATION_TEXT_REGEX.match(cleaned):
        raise ValueError("Bitte gib ein gültiges Land an.")
    return cleaned


def _normalized_country_key(country: str) -> str:
    normalized = _normalize_text(country).lower()
    return normalized.replace("ö", "oe").replace("ä", "ae").replace("ü", "ue").replace("ß", "ss")


def validate_postal_country_consistency(postal_code: str, country: str) -> None:
    postal = validate_postal_code(postal_code)
    country_key = _normalized_country_key(country)
    if country_key in GERMANY_ALIASES and len(postal) != 5:
        raise ValueError("Für Deutschland muss die PLZ genau 5-stellig sein.")
    if country_key in AUSTRIA_ALIASES and len(postal) != 4:
        raise ValueError("Für Österreich muss die PLZ genau 4-stellig sein.")
    if country_key in SWITZERLAND_ALIASES and len(postal) != 4:
        raise ValueError("Für die Schweiz muss die PLZ genau 4-stellig sein.")


def parse_full_address(value: str) -> dict[str, str]:
    cleaned = _normalize_text(value)
    extracted: dict[str, str] = {}
    segments = [_normalize_text(segment) for segment in cleaned.split(",") if segment.strip()]

    street_house_match = None
    street_source = ""
    street_candidates = segments + [cleaned]
    for candidate in street_candidates:
        match = re.search(
            r"(?P<street>[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß .'-]+?)\s+"
            r"(?P<house>[0-9]{1,5}[A-Za-z]?(?:[-/][0-9A-Za-z]{1,4})?)(?:\s|$)",
            candidate,
        )
        if not match:
            continue
        street_house_match = match
        street_source = candidate
        try:
            extracted["street"] = validate_street(match.group("street"))
            extracted["house_number"] = validate_house_number(match.group("house"))
            break
        except ValueError:
            continue

    postal_city_match = None
    for segment in (segments[1:] if len(segments) > 1 else [cleaned]):
        match = re.search(
            r"\b(?P<postal>\d{4,10})\s+(?P<city>[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß .'-]+)$",
            segment,
        )
        if match:
            postal_city_match = match
            break

    if postal_city_match:
        extracted["postal_code"] = validate_postal_code(postal_city_match.group("postal"))
        extracted["city"] = validate_city(postal_city_match.group("city"))

    if "city" not in extracted and len(segments) > 1:
        city_candidates = segments[:-1]
        for candidate in city_candidates:
            if not candidate or re.search(r"\d", candidate):
                continue
            try:
                extracted["city"] = validate_city(candidate)
                break
            except ValueError:
                continue

    if len(segments) > 1:
        country_candidate = segments[-1]
        if not re.search(r"\d", country_candidate):
            try:
                extracted["country"] = validate_country(country_candidate)
            except ValueError:
                pass
    if "country" not in extracted and street_house_match and street_source:
        country_candidate = _normalize_text(street_source[street_house_match.end() :])
        if country_candidate and not re.search(r"\d", country_candidate):
            try:
                extracted["country"] = validate_country(country_candidate)
            except ValueError:
                pass

    if "street" not in extracted and len(segments) == 1:
        single_part = segments[0]
        if re.search(
            r"\b(straße|strasse|str\.|weg|platz|allee|gasse|ufer|ring|damm|chaussee)\b",
            single_part,
            re.IGNORECASE,
        ):
            try:
                extracted["street"] = validate_street(single_part)
            except ValueError:
                pass

    return extracted
