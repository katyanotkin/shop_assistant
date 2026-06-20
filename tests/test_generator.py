import json
from unittest.mock import MagicMock, patch

import pytest

from core.generator import generate_search_config


def _mock_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.text = text
    return resp


def test_generate_returns_parsed_config():
    config = {
        "search_name": "wool_coat",
        "active": True,
        "criteria": {
            "category": ["coat"],
            "gender": "women",
            "material": ["wool"],
            "lining": [],
            "length": [],
            "exclude": [],
            "sizes": [],
            "max_price": None,
            "extra_notes": "",
        },
        "preferred_shops": [],
    }
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _mock_response(json.dumps(config))

    with patch("core.generator.genai.Client", return_value=mock_client):
        result = generate_search_config("women's wool coat", "wool_coat", "test-project")

    assert result["search_name"] == "wool_coat"
    assert result["criteria"]["category"] == ["coat"]
    assert result["criteria"]["gender"] == "women"


def test_generate_strips_markdown_fences():
    criteria = {
        "category": ["coat"],
        "gender": "women",
        "material": [],
        "lining": [],
        "length": [],
        "exclude": [],
        "sizes": [],
        "max_price": None,
        "extra_notes": "",
    }
    config = {"search_name": "wool_coat", "active": True, "criteria": criteria, "preferred_shops": []}
    raw = f"```json\n{json.dumps(config)}\n```"
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _mock_response(raw)

    with patch("core.generator.genai.Client", return_value=mock_client):
        result = generate_search_config("women's wool coat", "wool_coat", "test-project")

    assert result["search_name"] == "wool_coat"


def test_generate_raises_on_invalid_json():
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _mock_response("not json at all")

    with patch("core.generator.genai.Client", return_value=mock_client):
        with pytest.raises(Exception):
            generate_search_config("women's wool coat", "wool_coat", "test-project")


def test_generate_passes_description_and_name():
    criteria = {
        "category": ["jacket"],
        "gender": "unisex",
        "material": [],
        "lining": [],
        "length": [],
        "exclude": [],
        "sizes": [],
        "max_price": None,
        "extra_notes": "",
    }
    config = {"search_name": "rain_jacket", "active": True, "criteria": criteria, "preferred_shops": []}
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _mock_response(json.dumps(config))

    with patch("core.generator.genai.Client", return_value=mock_client):
        generate_search_config("waterproof rain jacket unisex", "rain_jacket", "my-project")

    call_kwargs = mock_client.models.generate_content.call_args
    prompt = call_kwargs[1]["contents"] if "contents" in call_kwargs[1] else call_kwargs[0][1]
    assert "rain_jacket" in prompt
    assert "waterproof rain jacket unisex" in prompt
