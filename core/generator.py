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

Return ONLY a JSON object (no markdown fences). Omit any field that has no value — \
do NOT include null values or empty arrays:
{{
  "search_name": "{search_name}",
  "active": true,
  "criteria": {{
    "category": ["..."],
    <only the fields relevant to this product type>
  }},
  "preferred_shops": []
}}

Rules:
- "category": ALWAYS required — list the main product type(s) inferred from the description.
- Choose field names appropriate for the product type. Do NOT force everything into \
  clothing fields. Examples by category:
    Clothing/fashion  → gender, material, lining, length, sizes, exclude
    Furniture/storage → dimensions (e.g. "max 60×35×180 cm"), color_exclude, \
features (list of required attributes e.g. ["shelves", "with doors"]), capacity
    Electronics       → brand, connectivity, battery_life, screen_size
    Any other item    → invent descriptive snake_case field names that capture \
the key criteria
- "max_price": number if a price limit is mentioned; omit otherwise.
- "extra_notes": one short string for nuance not captured by structured fields; omit if not needed.
- "preferred_shops": list of shop URLs if the user names specific shops; omit or use [] otherwise.
- All field names must be snake_case.
- Only include fields with concrete values — omit anything not mentioned or clearly implied.
- DO NOT invent or assume values the description does not support.
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
