from pathlib import Path 
import json
def load_constraints(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        print(f"[warn] constraints file not found: {p} -> using empty rules")
        return {"hard": {}, "soft": {}}
    with p.open("r", encoding="utf-8") as f:
        obj = json.load(f)
    # normalize minimal shape
    return {
        "hard": obj.get("hard", {}) or {},
        "soft": obj.get("soft", {}) or {}
    }