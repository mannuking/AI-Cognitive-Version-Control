"""Test Gemini 3 models with extended timeout."""
import asyncio
import json
import time
import httpx

API_KEY = "AIzaSyAtoRPzxS4N8bY-rUGql2IdoHknUZj9sSw"
BASE = "https://generativelanguage.googleapis.com/v1beta"


async def test(model: str, thinking_config: dict | None = None):
    body = {
        "contents": [{"role": "user", "parts": [{"text": "Say hello in one sentence."}]}],
        "generationConfig": {
            "temperature": 1.0,
            "maxOutputTokens": 1024,
        },
    }
    if thinking_config:
        body["generationConfig"]["thinkingConfig"] = thinking_config

    url = f"{BASE}/models/{model}:generateContent?key={API_KEY}"

    print(f"\n--- {model} (thinkingConfig={thinking_config}) ---")
    t0 = time.monotonic()

    # 5-minute timeout for slow thinking models
    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=300, write=30, pool=10)) as client:
        try:
            resp = await client.post(url, json=body)
        except httpx.ReadTimeout:
            print(f"  TIMED OUT after {time.monotonic() - t0:.1f}s")
            return
        except Exception as e:
            print(f"  ERROR: {e}")
            return

    elapsed = time.monotonic() - t0
    print(f"  Status: {resp.status_code}  Time: {elapsed:.1f}s")

    if resp.status_code != 200:
        print(f"  Error: {resp.text[:300]}")
        return

    data = resp.json()
    usage = data.get("usageMetadata", {})
    print(f"  Prompt: {usage.get('promptTokenCount', '?')}  "
          f"Candidates: {usage.get('candidatesTokenCount', '?')}  "
          f"Thoughts: {usage.get('thoughtsTokenCount', '?')}  "
          f"Total: {usage.get('totalTokenCount', '?')}")

    candidates = data.get("candidates", [])
    if candidates:
        parts = candidates[0].get("content", {}).get("parts", [])
        for i, p in enumerate(parts):
            tag = "[THOUGHT]" if p.get("thought") else "[OUTPUT]"
            txt = p.get("text", "")[:300]
            print(f"    Part {i}: {tag}")
            if txt:
                print(f"      '{txt}'")
        print(f"  Finish: {candidates[0].get('finishReason', '?')}")
    else:
        print("  NO CANDIDATES")


async def main():
    # Fast control test
    await test("gemini-2.5-flash", {"thinkingBudget": 0})

    # Gemini 3 Flash (should be faster than Pro)
    await test("gemini-3-flash-preview", {"thinkingLevel": "low"})

    # Gemini 3 Pro with low thinking
    await test("gemini-3-pro-preview", {"thinkingLevel": "low"})

    # Gemini 3 Pro with NO thinkingConfig (let API decide)
    await test("gemini-3-pro-preview", None)

    print("\n=== ALL TESTS DONE ===")


if __name__ == "__main__":
    asyncio.run(main())
