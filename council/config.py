import json
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
DATA = Path(os.environ.get("COUNCIL_DATA_DIR", ROOT / "data"))
DEFAULT_MODELS = [
    {"id": "openai/gpt-6.1-terra", "name": "GPT", "color": "green"},
    {"id": "anthropic/claude-sonnet-5.5", "name": "Claude", "color": "orange"},
    {"id": "x-ai/grok-4.7", "name": "Grok", "color": "blue"},
    {"id": "google/gemini-3.8-flash", "name": "Gemini", "color": "purple"},
]


def keys() -> dict:
    path = DATA / "credentials.json"
    saved = json.loads(path.read_text()) if path.exists() else {}
    return {
        "openrouter": saved.get("openrouter") or os.getenv("OPENROUTER_API_KEY", ""),
        "tavily": saved.get("tavily") or os.getenv("TAVILY_API_KEY", ""),
    }


def save_keys(values: dict) -> None:
    DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
    saved = keys()
    for key in ("openrouter", "tavily"):
        if values.get(key):
            saved[key] = values[key].strip()
    path = DATA / "credentials.json"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as file:
        json.dump(saved, file)
    path.chmod(0o600)
