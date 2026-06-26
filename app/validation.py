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
    if len(cleaned) < 2 or any(c.isdigit() for c in cleaned):
        raise ValueError("Der Vorname ist ungültig (bitte keine Zahlen).")
    if not PERSON_TEXT_REGEX.match(cleaned):
        raise ValueError("Der Vorname enthält ungültige Sonderzeichen.")
    return cleaned


def validate_last_name(value: str) -> str:
    cleaned = _normalize_text(value)
    if len(cleaned) < 2 or any(c.isdigit() for c in cleaned):
        raise ValueError("Der Nachname ist ungültig (bitte keine Zahlen).")
    if not PERSON_TEXT_REGEX.match(cleaned):
        raise ValueError("Der Nachname enthält ungültige Sonderzeichen.")
    return cleaned


GERMAN_MONTHS = {
    "januar": 1, "februar": 2, "märz": 3, "april": 4, "mai": 5, "juni": 6,
    "juli": 7, "august": 8, "september": 9, "oktober": 10, "november": 11, "dezember": 12,
    "jan": 1, "feb": 2, "mär": 3, "apr": 4, "mai": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "okt": 10, "nov": 11, "dez": 12
}

def validate_birthdate(value: str) -> str:
    # Remove trailing dots, commas or spaces
    cleaned = value.strip().rstrip("., ").lower()
    print(f"DEBUG [Validation]: Validating birthdate raw: '{value}' -> cleaned: '{cleaned}'")
    
    parsed_date = None

    # 1. Handle "28. Juni 2004" or "28 Juni 2004"
    month_pattern = r"(?P<day>\d{1,2})[. ]\s*(?P<month>[a-zäöü]+)\s*[. ]\s*(?P<year>\d{4})"
    match = re.search(month_pattern, cleaned)
    if match:
        month_name = match.group("month")
        if month_name in GERMAN_MONTHS:
            try:
                parsed_date = datetime(
                    year=int(match.group("year")),
                    month=GERMAN_MONTHS[month_name],
                    day=int(match.group("day"))
                )
            except ValueError:
                pass

    # 2. Handle standard numeric formats if natural language failed
    if not parsed_date:
        # Try to normalize "D.M.YYYY" to "DD.MM.YYYY"
        norm_match = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", cleaned)
        if norm_match:
            cleaned = f"{int(norm_match.group(1)):02d}.{int(norm_match.group(2)):02d}.{norm_match.group(3)}"

        for fmt in DATE_FORMATS:
            try:
                parsed_date = datetime.strptime(cleaned, fmt)
                break
            except ValueError:
                continue

    if not parsed_date:
        raise ValueError("Bitte gib das Geburtsdatum z. B. als TT.MM.JJJJ oder '28. Juni 2004' an.")

    if parsed_date > datetime.now():
        raise ValueError("Das Geburtsdatum darf nicht in der Zukunft liegen.")
    
    age = (datetime.now().date() - parsed_date.date()).days // 365
    if age < 14:
        raise ValueError("Das Geburtsdatum ist unplausibel (Mindestalter 14 Jahre).")
    if age > 120:
        raise ValueError("Das Geburtsdatum ist unplausibel (älter als 120 Jahre).")
        
    return parsed_date.strftime("%Y-%m-%d")


def validate_email(value: str) -> str:
    cleaned = _normalize_text(value).lower().strip().rstrip(".,;!? ")
    
    # Handle voice-to-text artifacts
    cleaned = cleaned.replace(" punkt ", ".").replace(" dot ", ".")
    cleaned = cleaned.replace(" at ", "@").replace(" klammeraffe ", "@")
    cleaned = cleaned.replace(" minus ", "-").replace(" bindestrich ", "-").replace(" dash ", "-")
    cleaned = cleaned.replace(" ", "") # Emails never have spaces
    
    # Common mistakes in spoken TLDs
    if cleaned.endswith("atde"): cleaned = cleaned[:-4] + "@de"
    if cleaned.endswith(".de."): cleaned = cleaned[:-1]
    
    if not EMAIL_REGEX.match(cleaned):
        raise ValueError("Die E-Mail hat kein gültiges Format (z.B. name@beispiel.de).")
    return cleaned


def validate_phone(value: str) -> str:
    cleaned = _normalize_text(value)
    # Remove all non-digit characters except leading +
    digits_only = re.sub(r"(?<!^)\+|[^\d+]", "", cleaned)
    
    if len(digits_only) < 7 or len(digits_only) > 17:
        raise ValueError("Die Telefonnummer ist zu kurz oder zu lang.")
        
    # Heuristic: If it starts with 0 and no +, assume DE (+49)
    if digits_only.startswith("0") and not digits_only.startswith("00"):
        digits_only = "+49" + digits_only[1:]
    elif digits_only.startswith("00"):
        digits_only = "+" + digits_only[2:]
        
    return digits_only


def validate_street(value: str) -> str:
    cleaned = _normalize_text(value)
    if len(cleaned) < 3 or not any(char.isalpha() for char in cleaned):
        raise ValueError("Bitte nenne eine gültige Straße.")
    return cleaned


def validate_house_number(value: str) -> str:
    cleaned = _normalize_text(value)
    if not HOUSE_NUMBER_REGEX.match(cleaned):
        raise ValueError("Die Hausnummer ist ungültig.")
    return cleaned


def validate_postal_code(value: str) -> str:
    cleaned = value.strip().replace(" ", "")
    if not POSTAL_REGEX.match(cleaned):
        raise ValueError("Die PLZ muss aus 4 bis 10 Ziffern bestehen.")
    return cleaned


def validate_city(value: str) -> str:
    cleaned = _normalize_text(value)
    if len(cleaned) < 2 or any(char.isdigit() for char in cleaned):
        raise ValueError("Bitte gib einen gültigen Ort ohne Zahlen an.")
    return cleaned


def validate_country(value: str) -> str:
    cleaned = _normalize_text(value)
    if len(cleaned) == 2 and cleaned.isalpha():
        return cleaned.upper()
    if len(cleaned) < 4:
        raise ValueError("Bitte gib ein gültiges Land an.")
    return cleaned


def _normalized_country_key(country: str) -> str:
    normalized = _normalize_text(country).lower()
    return normalized.replace("ö", "oe").replace("ä", "ae").replace("ü", "ue").replace("ß", "ss")


def validate_postal_country_consistency(postal_code: str | None, country: str | None) -> None:
    if not postal_code or not country:
        return
        
    postal = postal_code.replace(" ", "")
    country_key = _normalized_country_key(country)
    
    if country_key in GERMANY_ALIASES:
        if len(postal) != 5:
            raise ValueError(f"In Deutschland muss die PLZ 5-stellig sein (du hast '{postal}').")
    elif country_key in AUSTRIA_ALIASES or country_key in SWITZERLAND_ALIASES:
        if len(postal) != 4:
            raise ValueError(f"In {country.capitalize()} muss die PLZ 4-stellig sein (du hast '{postal}').")


def parse_full_address(value: str) -> dict[str, str]:
    raw_text = value.strip()
    
    # 0. Split by commas to handle fragments, stripping trailing punctuation from segments
    segments = [s.strip().rstrip(".,;!? ") for s in raw_text.split(",") if s.strip()]
    segments = [s for s in segments if s]
    extracted: dict[str, str] = {}
    remaining_segments = []  # List of tuples: (segment_text, original_index)
    
    plz_idx = -1

    # 1. Look for PLZ in any segment (matches 4 to 9 digits with optional whitespace)
    for idx, seg in enumerate(segments):
        plz_match = re.search(r"\b\d(?:\s*\d){3,8}\b", seg)
        if plz_match:
            plz_val = re.sub(r"\s+", "", plz_match.group(0))
            
            # Smart heuristic for 6-8 digit PLZs (voice-transcribed house number + PLZ)
            # e.g., "8, 14776" transcribed as "814 776". If PLZ has 6-8 digits,
            # split the first digit(s) as the house number and the last 5 digits as the German PLZ.
            if len(plz_val) >= 6 and len(plz_val) <= 8:
                extracted["house_number"] = plz_val[:-5]
                plz_val = plz_val[-5:]
                
            extracted["postal_code"] = plz_val
            plz_idx = idx
            
            # Extract leftovers from this segment (before/after PLZ)
            start_idx = plz_match.start()
            end_idx = plz_match.end()
            before_plz = seg[:start_idx].strip(",;!? ")
            after_plz = seg[end_idx:].strip(",;!? ")
            
            if before_plz:
                remaining_segments.append((before_plz, idx))
            if after_plz:
                remaining_segments.append((after_plz, idx))
        else:
            remaining_segments.append((seg, idx))

    # 2. Look for Country in remaining segments
    all_aliases = GERMANY_ALIASES | AUSTRIA_ALIASES | SWITZERLAND_ALIASES
    final_segments = []
    for seg, idx in remaining_segments:
        found_country = False
        for alias in all_aliases:
            if re.search(rf"\b{alias}\b", seg, re.IGNORECASE):
                extracted["country"] = alias.capitalize() if len(alias) > 2 else alias.upper()
                found_country = True
                break
        if not found_country:
            final_segments.append((seg, idx))

    # 3. Look for Street/House Number (explicit pair)
    still_remaining = []
    street_keywords = r"(straße|strasse|str\.|weg|platz|allee|gasse|ufer|ring|damm|chaussee)"
    
    for i, (seg, idx) in enumerate(final_segments):
        # Case A: "Street Name 50"
        sh_match = re.search(rf"(?P<street>[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß .'-]+?)\s+(?P<house>[0-9]{{1,5}}[A-Za-z]?(?:[-/][0-9A-Za-z]{{1,4}})?)$", seg)
        if sh_match:
            extracted["street"] = sh_match.group("street").strip()
            extracted["house_number"] = sh_match.group("house").strip()
            continue
            
        # Case B: Just "Street Name" (with keyword)
        if re.search(street_keywords, seg, re.IGNORECASE):
            extracted["street"] = seg
            if i + 1 < len(final_segments) and re.match(r"^[0-9]{1,5}[A-Za-z]?$", final_segments[i+1][0]):
                extracted["house_number"] = final_segments[i+1][0]
            continue
            
        # Case C: Just a standalone number (House Number)
        if re.match(r"^[0-9]{1,5}[A-Za-z]?$", seg) and not extracted.get("house_number"):
            extracted["house_number"] = seg
            continue

        still_remaining.append((seg, idx))

    # Spatial Heuristic: If we extracted a house number (e.g. from PLZ split) but no street name,
    # find a leftover segment positioned before or at the PLZ segment and treat it as the street.
    if "house_number" in extracted and "street" not in extracted:
        street_cand = next((seg for seg, idx in still_remaining if idx <= plz_idx), None)
        if street_cand:
            extracted["street"] = street_cand
            still_remaining = [(seg, idx) for seg, idx in still_remaining if seg != street_cand]

    # 4. Use leftovers as City (careful not to pick up streets)
    if "city" not in extracted and still_remaining:
        # Pick the candidate that doesn't look like a street
        city_candidates = [seg for seg, idx in still_remaining if not re.search(street_keywords, seg, re.IGNORECASE)]
        if city_candidates:
            # Prefer leftovers positioned after the PLZ (idx > plz_idx) if available
            post_plz_candidates = [seg for seg, idx in still_remaining if idx > plz_idx and not re.search(street_keywords, seg, re.IGNORECASE)]
            city_cand = post_plz_candidates[0] if post_plz_candidates else max(city_candidates, key=len)
            if len(city_cand) > 2:
                extracted["city"] = city_cand

    return extracted
