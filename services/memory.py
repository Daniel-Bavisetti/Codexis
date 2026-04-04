import json
import os

MEMORY_FILE = "data/memory.json"

def _load_memory() -> dict:
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"successful_patterns": [], "common_issues": []}

def _save_memory(mem: dict):
    os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(mem, f, indent=2)

def add_successful_pattern(req_desc: str, file_path: str):
    mem = _load_memory()
    mem["successful_patterns"].append({"req": req_desc, "file": file_path})
    _save_memory(mem)

def add_common_issue(issue: str):
    mem = _load_memory()
    mem["common_issues"].append(issue)
    _save_memory(mem)

def get_memory_context() -> str:
    return json.dumps(_load_memory())
