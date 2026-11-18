"""Print the OpenRouter account balance (total credits, total usage, remaining). Never prints the key."""
import json, os, sys
from urllib.request import Request, urlopen

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from local_paths import local  # noqa: E402


def key():
    if not os.getenv("OPENROUTER_API_KEY"):
        loader = local("key_loader_path")
        if not loader:
            raise SystemExit("Set OPENROUTER_API_KEY (see study/local_paths.py).")
        sys.path.insert(0, loader)
        from system.lib.openrouter_free_runtime import _ensure_env_loaded
        _ensure_env_loaded()
    return os.environ["OPENROUTER_API_KEY"]


def balance():
    req = Request("https://openrouter.ai/api/v1/credits", headers={"Authorization": "Bearer " + key()})
    d = json.load(urlopen(req, timeout=30))["data"]
    return {"total_credits": d["total_credits"], "total_usage": round(d["total_usage"], 6),
            "remaining": round(d["total_credits"] - d["total_usage"], 6)}


if __name__ == "__main__":
    print(json.dumps(balance()))
