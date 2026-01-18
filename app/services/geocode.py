import logging
import os
from typing import Optional

import requests


logger = logging.getLogger("eagl.maps")


def _component(components: list[dict], key: str) -> Optional[str]:
    for comp in components:
        if key in comp.get("types", []):
            return comp.get("long_name")
    return None


def reverse_geocode(lat: float, lng: float) -> Optional[dict]:
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        logger.warning("GOOGLE_MAPS_API_KEY not configured")
        return {"status": "ERROR", "error": "MISSING_KEY"}
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"latlng": f"{lat},{lng}", "key": api_key}
    try:
        resp = requests.get(url, params=params, timeout=10)
    except Exception as exc:
        logger.warning("reverse geocode request failed: %s", exc)
        return {"status": "ERROR", "error": "REQUEST_FAILED"}
    if resp.status_code != 200:
        logger.warning("reverse geocode status_code=%s", resp.status_code)
        return {"status": "ERROR", "error": "BAD_STATUS"}
    data = resp.json()
    status = data.get("status")
    if status != "OK" or not data.get("results"):
        logger.info("reverse geocode status=%s", status)
        return {"status": "ERROR", "error": status or "NO_RESULTS"}
    result = data["results"][0]
    components = result.get("address_components", [])
    plus_code = data.get("plus_code", {}).get("compound_code") or data.get("plus_code", {}).get("global_code")
    address = {
        "formatted": result.get("formatted_address"),
        "street": _component(components, "route"),
        "number": _component(components, "street_number"),
        "district": _component(components, "sublocality")
        or _component(components, "sublocality_level_1")
        or _component(components, "neighborhood"),
        "city": _component(components, "locality")
        or _component(components, "administrative_area_level_2"),
        "state": _component(components, "administrative_area_level_1"),
        "zip": _component(components, "postal_code"),
        "country": _component(components, "country"),
        "plus_code": plus_code,
    }
    return {"status": "OK", "address": address}
