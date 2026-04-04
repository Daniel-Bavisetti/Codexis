import json
import os

def parse_requirements(filepath: str | None = None, raw_text: str | None = None) -> dict:
    categorized = {"FIT": [], "PARTIAL": [], "GAP": []}

    data = []
    if raw_text and raw_text.strip():
        data = _parse_requirements_text(raw_text)
    elif filepath and os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    else:
        return categorized

    for req in data:
        req_type = req.get("type", "").upper()
        if req_type in categorized:
            categorized[req_type].append(req)

    return categorized


def _parse_requirements_text(raw_text: str) -> list[dict]:
    text = raw_text.strip()
    if not text:
        return []

    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            items: list[dict] = []
            for req_type in ["FIT", "PARTIAL", "GAP"]:
                for index, item in enumerate(parsed.get(req_type, []), start=1):
                    if isinstance(item, dict):
                        items.append(
                            {
                                "id": item.get("id") or f"{req_type}-JSON-{index:03d}",
                                "type": req_type,
                                "description": item.get("description", ""),
                                "file_hint": item.get("file_hint", "Not specified"),
                            }
                        )
            return items
    except json.JSONDecodeError:
        pass

    requirements: list[dict] = []
    for index, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        parts = [part.strip() for part in stripped.split("|")]
        req_type = "PARTIAL"
        description = stripped
        file_hint = "Not specified"

        if len(parts) >= 3:
            req_type, description, file_hint = parts[:3]
        elif len(parts) == 2:
            left, right = parts
            if left.upper() in {"FIT", "PARTIAL", "GAP"}:
                req_type, description = left, right
            else:
                description, file_hint = left, right
        else:
            if ":" in stripped:
                prefix, remainder = stripped.split(":", 1)
                if prefix.strip().upper() in {"FIT", "PARTIAL", "GAP"} and remainder.strip():
                    req_type = prefix.strip().upper()
                    description = remainder.strip()

        requirements.append(
            {
                "id": f"REQ-TEXT-{index:03d}",
                "type": req_type.upper(),
                "description": description,
                "file_hint": file_hint,
            }
        )
    return requirements
