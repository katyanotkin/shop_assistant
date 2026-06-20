import json

import google.genai as genai
from google.genai import types

GEMINI_MODEL = "gemini-2.5-flash-lite"
GEMINI_LOCATION = "us-central1"

_PROMPT = """\
You are configuring a shopping search assistant. Given a free-form description of what \
the user wants to buy, generate a structured search configuration JSON.

Description: {description}
Search name (snake_case identifier): {search_name}

Return ONLY a JSON object with this exact structure (no markdown fences):
{{
  "search_name": "{search_name}",
  "active": true,
  "criteria": {{
    "category": ["..."],
    "gender": "women|men|unisex",
    "material": [],
    "lining": [],
    "length": [],
    "exclude": [],
    "sizes": [],
    "max_price": null,
    "extra_notes": ""
  }},
  "preferred_shops": []
}}

Rules:
- category: main product type(s) — always required, infer from description
- gender: infer from description; default "unisex" if unclear
- Use empty arrays [] for fields not mentioned in the description
- max_price: number or null
- extra_notes: any nuance not captured by other fields; empty string if none
- preferred_shops: empty unless user names specific shops
- Only populate values the user actually mentioned or strongly implied
"""


def generate_search_config(description: str, search_name: str, project: str) -> dict:
    client = genai.Client(vertexai=True, project=project, location=GEMINI_LOCATION)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=_PROMPT.format(description=description, search_name=search_name),
        config=types.GenerateContentConfig(temperature=0),
    )
    raw = response.text.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)
