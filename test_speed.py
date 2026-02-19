"""Quick latency test for Gemini models with thinkingLevel vs thinkingBudget."""
import asyncio, time, os, sys, json, httpx
sys.path.insert(0, ".")

API_KEY = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY", "")
if not API_KEY:
    from dotenv import load_dotenv
    load_dotenv()
    API_KEY = os.environ.get("GOOGLE_API_KEY", "")

MODEL = "gemini-3-pro-preview"
PROMPT = [{"role": "user", "parts": [{"text": "Say hello in one sentence."}]}]

CONFIGS = [
    ("thinkingLevel=low", {"thinkingConfig": {"thinkingLevel": "low"}, "temperature": 1.0, "maxOutputTokens": 256}),
    ("thinkingBudget=512", {"thinkingConfig": {"thinkingBudget": 512}, "temperature": 1.0, "maxOutputTokens": 256}),
    ("thinkingBudget=128", {"thinkingConfig": {"thinkingBudget": 128}, "temperature": 1.0, "maxOutputTokens": 256}),
]


async def test_config(label: str, gen_config: dict):
    body = {
        "contents": PROMPT,
        "generationConfig": gen_config,
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"
    
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, read=300.0)) as client:
        t0 = time.perf_counter()
        try:
            resp = await client.post(url, json=body)
            elapsed = time.perf_counter() - t0
            if resp.status_code != 200:
                print(f"  {label}: HTTP {resp.status_code} after {elapsed:.1f}s — {resp.text[:200]}")
                return
            data = resp.json()
            usage = data.get("usageMetadata", {})
            parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            text = " ".join(p.get("text", "") for p in parts if not p.get("thought") and "text" in p)
            think_tokens = usage.get("thoughtsTokenCount", 0)
            total_tokens = usage.get("candidatesTokenCount", 0)
            print(f"  {label}: {elapsed:.1f}s, think={think_tokens}, out={total_tokens}, text={text[:80]!r}")
        except Exception as e:
            elapsed = time.perf_counter() - t0
            print(f"  {label}: ERROR after {elapsed:.1f}s — {e}")


async def main():
    print(f"API key: ...{API_KEY[-8:]}")
    print(f"Model: {MODEL}\n")
    for label, gc in CONFIGS:
        await test_config(label, gc)


if __name__ == "__main__":
    asyncio.run(main())
