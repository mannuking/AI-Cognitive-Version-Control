"""Quick test: Gemini 3 Pro raw API call to debug empty responses."""
import asyncio
import json
import httpx

API_KEY = "AIzaSyAtoRPzxS4N8bY-rUGql2IdoHknUZj9sSw"
BASE = "https://generativelanguage.googleapis.com/v1beta"


async def test_model(model: str, thinking_config: dict, label: str):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"  Model: {model}  |  thinkingConfig: {thinking_config}")
    print(f"{'='*60}")

    body = {
        "contents": [{"role": "user", "parts": [{"text": "Say hello in one sentence."}]}],
        "generationConfig": {
            "temperature": 1.0,
            "maxOutputTokens": 1024,  # generous budget
            "thinkingConfig": thinking_config,
        },
    }

    url = f"{BASE}/models/{model}:generateContent?key={API_KEY}"

    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = await client.post(url, json=body)
        print(f"  HTTP Status: {resp.status_code}")

        if resp.status_code != 200:
            print(f"  Error body: {resp.text[:500]}")
            return

        data = resp.json()

        # Show usage
        usage = data.get("usageMetadata", {})
        print(f"  Prompt tokens:     {usage.get('promptTokenCount', '?')}")
        print(f"  Candidates tokens: {usage.get('candidatesTokenCount', '?')}")
        print(f"  Total tokens:      {usage.get('totalTokenCount', '?')}")
        # Gemini 3 has thoughtsTokenCount
        if "thoughtsTokenCount" in usage:
            print(f"  Thoughts tokens:   {usage['thoughtsTokenCount']}")

        # Show candidates
        candidates = data.get("candidates", [])
        if not candidates:
            print("  NO CANDIDATES!")
            return

        parts = candidates[0].get("content", {}).get("parts", [])
        print(f"  Parts count: {len(parts)}")
        for i, part in enumerate(parts):
            is_thought = part.get("thought", False)
            has_text = "text" in part
            has_fc = "functionCall" in part
            text_preview = part.get("text", "")[:200] if has_text else ""
            tag = "[THOUGHT]" if is_thought else "[OUTPUT]"
            print(f"    Part {i}: {tag} text={has_text} fc={has_fc}")
            if text_preview:
                print(f"      '{text_preview}'")

        finish = candidates[0].get("finishReason", "?")
        print(f"  Finish reason: {finish}")


async def main():
    # Test 1: gemini-2.5-flash with thinkingBudget=0 (should work fine)
    await test_model(
        "gemini-2.5-flash",
        {"thinkingBudget": 0},
        "Test 1: gemini-2.5-flash (thinkingBudget=0)"
    )

    # Test 2: gemini-3-pro-preview with thinkingLevel=low
    await test_model(
        "gemini-3-pro-preview",
        {"thinkingLevel": "low"},
        "Test 2: gemini-3-pro-preview (thinkingLevel=low)"
    )

    # Test 3: gemini-3-pro-preview with thinkingLevel=medium
    await test_model(
        "gemini-3-pro-preview",
        {"thinkingLevel": "medium"},
        "Test 3: gemini-3-pro-preview (thinkingLevel=medium)"
    )

    # Test 4: gemini-3-pro-preview WITHOUT any thinkingConfig
    print(f"\n{'='*60}")
    print(f"  Test 4: gemini-3-pro-preview (NO thinkingConfig)")
    print(f"{'='*60}")
    body = {
        "contents": [{"role": "user", "parts": [{"text": "Say hello in one sentence."}]}],
        "generationConfig": {
            "temperature": 1.0,
            "maxOutputTokens": 1024,
        },
    }
    url = f"{BASE}/models/gemini-3-pro-preview:generateContent?key={API_KEY}"
    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = await client.post(url, json=body)
        print(f"  HTTP Status: {resp.status_code}")
        if resp.status_code != 200:
            print(f"  Error: {resp.text[:500]}")
        else:
            data = resp.json()
            usage = data.get("usageMetadata", {})
            print(f"  Prompt: {usage.get('promptTokenCount', '?')}  Candidates: {usage.get('candidatesTokenCount', '?')}  Thoughts: {usage.get('thoughtsTokenCount', '?')}")
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                for i, p in enumerate(parts):
                    tag = "[THOUGHT]" if p.get("thought") else "[OUTPUT]"
                    txt = p.get("text", "")[:200]
                    print(f"    Part {i}: {tag} '{txt}'")
                print(f"  Finish: {candidates[0].get('finishReason', '?')}")

    print("\n=== DONE ===")


if __name__ == "__main__":
    asyncio.run(main())
