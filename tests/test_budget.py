"""Test different thinkingBudget values on Gemini 3 Pro to find optimal."""
import asyncio, time, json
import httpx

API_KEY = "AIzaSyAtoRPzxS4N8bY-rUGql2IdoHknUZj9sSw"
MODEL = "gemini-3-pro-preview"
BASE = "https://generativelanguage.googleapis.com"

async def test_budget(budget, label=""):
    client = httpx.AsyncClient(base_url=BASE, timeout=300.0)
    body = {
        "contents": [{"role": "user", "parts": [{"text": "Say hello in one sentence."}]}],
        "generationConfig": {
            "temperature": 1.0,
            "maxOutputTokens": 100,
            "thinkingConfig": {"thinkingBudget": budget},
        },
    }
    url = f"/v1beta/models/{MODEL}:generateContent?key={API_KEY}"
    t0 = time.time()
    try:
        resp = await client.post(url, json=body)
        elapsed = time.time() - t0
        if resp.status_code != 200:
            err = resp.text[:200]
            print(f"  budget={budget:>6} ({label:>10}): {elapsed:.1f}s — HTTP {resp.status_code}: {err}")
        else:
            data = resp.json()
            parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            text = " ".join(p.get("text", "") for p in parts if "text" in p and not p.get("thought"))
            usage = data.get("usageMetadata", {})
            think_tok = usage.get("thoughtsTokenCount", 0)
            out_tok = usage.get("candidatesTokenCount", 0)
            print(f"  budget={budget:>6} ({label:>10}): {elapsed:.1f}s — think={think_tok}, out={out_tok} — {text!r}")
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  budget={budget:>6} ({label:>10}): {elapsed:.1f}s — ERROR: {e}")
    finally:
        await client.aclose()

async def main():
    print(f"Testing {MODEL} with different thinkingBudget values:\n")
    for budget, label in [
        (128, "minimal"),
        (512, "low"),
        (1024, "medium"),
        (4096, "high"),
        (16384, "very high"),
    ]:
        await test_budget(budget, label)
    print("\nDone.")

asyncio.run(main())
