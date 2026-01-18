import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services import geocode


class ReverseGeocodeTests(unittest.TestCase):
    def test_reverse_geocode_missing_key(self):
        os.environ.pop("GOOGLE_MAPS_API_KEY", None)
        result = geocode.reverse_geocode(-23.55, -46.63)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("status"), "ERROR")
        self.assertEqual(result.get("error"), "MISSING_KEY")

    @patch("app.services.geocode.requests.get")
    def test_reverse_geocode_ok(self, mock_get):
        os.environ["GOOGLE_MAPS_API_KEY"] = "test"
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "status": "OK",
            "results": [
                {
                    "formatted_address": "Rua A, 123 - Centro",
                    "address_components": [
                        {"long_name": "Rua A", "types": ["route"]},
                        {"long_name": "123", "types": ["street_number"]},
                        {"long_name": "Centro", "types": ["sublocality"]},
                        {"long_name": "Sao Paulo", "types": ["locality"]},
                        {"long_name": "SP", "types": ["administrative_area_level_1"]},
                        {"long_name": "01000-000", "types": ["postal_code"]},
                        {"long_name": "Brasil", "types": ["country"]},
                    ],
                }
            ],
            "plus_code": {"compound_code": "XP7P+QH Sao Paulo"},
        }
        result = geocode.reverse_geocode(-23.55, -46.63)
        self.assertEqual(result.get("status"), "OK")
        address = result.get("address") or {}
        self.assertEqual(address.get("street"), "Rua A")
        self.assertEqual(address.get("number"), "123")
        self.assertEqual(address.get("city"), "Sao Paulo")
        self.assertEqual(address.get("plus_code"), "XP7P+QH Sao Paulo")


class DoctorEndpointTests(unittest.TestCase):
    @patch("app.api.v1.doctor.reverse_geocode")
    def test_doctor_maps_ok(self, mock_reverse):
        mock_reverse.return_value = {"status": "OK", "address": {"formatted": "X"}}
        client = TestClient(app)
        res = client.get("/api/doctor/maps")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json().get("status"), "OK")

