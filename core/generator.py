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
    "gender": null,
    "material": null,
    "lining": null,
    "length": null,
    "exclude": null,
    "sizes": null,
    "max_price": null,
    "extra_notes": null
  }},
  "preferred_shops": []
}}

Rules:
- category: ALWAYS required — list the main product type(s) inferred from the description
- gender: include ONLY for clothing/fashion items where gender is relevant;
  omit (null) for home goods, accessories, tools, etc.
- material, lining, length, exclude, sizes: include ONLY if mentioned or strongly
  implied by the description; leave null otherwise
- max_price: number if mentioned, otherwise null
- extra_notes: short string for nuance not captured by other fields; null if nothing to add
- preferred_shops: list if user names specific shops, otherwise empty array
- DO NOT invent or assume values — only include what the description actually says
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
