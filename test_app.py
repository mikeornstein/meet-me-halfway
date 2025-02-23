import pytest
from unittest.mock import patch
import streamlit_app as app  # Import your app module

# Set dummy API keys for testing
app.ORS_API_KEY = "test_key"
app.GOOGLE_API_KEY = "test_key"

def test_geocode_valid_address():
    with patch('requests.get') as mock_get:
        mock_get.return_value.json.return_value = {
            "features": [{"geometry": {"coordinates": [13.4050, 52.5200]}}]
        }
        result = app.geocode("Berlin, Germany")
        assert result == [13.4050, 52.5200]

def test_geocode_invalid_address():
    with patch('requests.get') as mock_get:
        mock_get.return_value.json.return_value = {"features": []}
        result = app.geocode("Invalid Address")
        assert result is None