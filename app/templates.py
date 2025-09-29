import json
import os
from typing import Dict, Any, List

TEMPLATES_DIR = os.path.join(os.path.expanduser("~"), ".photo_watermark2", "templates")
LAST_USED = os.path.join(os.path.expanduser("~"), ".photo_watermark2", "last_used.json")

def ensure_dirs():
    os.makedirs(TEMPLATES_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(LAST_USED), exist_ok=True)

def save_template(name: str, data: Dict[str, Any]):
    ensure_dirs()
    path = os.path.join(TEMPLATES_DIR, f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_template(name: str) -> Dict[str, Any]:
    path = os.path.join(TEMPLATES_DIR, f"{name}.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def list_templates() -> List[str]:
    ensure_dirs()
    names = []
    for fn in os.listdir(TEMPLATES_DIR):
        if fn.endswith(".json"):
            names.append(os.path.splitext(fn)[0])
    return sorted(names)

def delete_template(name: str):
    path = os.path.join(TEMPLATES_DIR, f"{name}.json")
    if os.path.exists(path):
        os.remove(path)

def save_last_used(data: Dict[str, Any]):
    ensure_dirs()
    with open(LAST_USED, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_last_used() -> Dict[str, Any]:
    if not os.path.exists(LAST_USED):
        return {}
    with open(LAST_USED, "r", encoding="utf-8") as f:
        return json.load(f)
