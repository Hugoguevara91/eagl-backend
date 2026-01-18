import os
import time
from dataclasses import dataclass

import httpx


class GeocodingError(RuntimeError):
    pass


@dataclass
class GeocodeResult:
    lat: float | None
    lng: float | None
    status: str


def is_address_complete(address: str | None) -> bool:
    if not address:
        return False
    cleaned = address.strip()
    if len(cleaned) < 10:
        return False
    has_state = bool(__import__("re").search(r"\b[A-Z]{2}\b", cleaned))
    has_zip = bool(__import__("re").search(r"\b\d{5}-?\d{3}\b", cleaned))
    return has_state or has_zip


def _normalize_address(address: str) -> str:
    value = address.strip()
    if not value:
        return value
    replacements = {
        "R. ": "Rua ",
        "R.": "Rua ",
        "Av. ": "Avenida ",
        "Av.": "Avenida ",
    }
    for raw, fixed in replacements.items():
        value = value.replace(raw, fixed)
    if "Brasil" not in value and "BR" not in value:
        value = f"{value}, Brasil"
    return value


def geocode_address(address: str, timeout: float = 6.0) -> GeocodeResult:
    api_key = os.getenv("GOOGLE_MAPS_GEOCODING_KEY")
    if not api_key:
        raise GeocodingError("GOOGLE_MAPS_GEOCODING_KEY nao configurada")

    normalized = _normalize_address(address)
    params = {
        "address": normalized,
        "key": api_key,
        "region": "br",
        "components": "country:BR",
    }
    url = "https://maps.googleapis.com/maps/api/geocode/json"

    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.get(url, params=params)
            if response.status_code >= 400:
                raise GeocodingError(f"HTTP {response.status_code}")
            payload = response.json()
            status = payload.get("status") or "ERROR"
            if status == "OK":
                results = payload.get("results") or []
                if not results:
                    return GeocodeResult(lat=None, lng=None, status="ZERO_RESULTS")
                location = results[0].get("geometry", {}).get("location") or {}
                return GeocodeResult(
                    lat=location.get("lat"),
                    lng=location.get("lng"),
                    status="OK",
                )
            if status in {"ZERO_RESULTS", "NOT_FOUND"}:
                return GeocodeResult(lat=None, lng=None, status=status)
            if status in {"OVER_QUERY_LIMIT", "REQUEST_DENIED", "INVALID_REQUEST"}:
                raise GeocodingError(status)
            return GeocodeResult(lat=None, lng=None, status=status)
        except httpx.RequestError as exc:
            last_exc = exc
            if attempt == 0:
                time.sleep(0.3)
                continue
            break

    raise GeocodingError(str(last_exc) if last_exc else "Falha ao geocodificar")
