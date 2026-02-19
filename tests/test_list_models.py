"""List all available Gemini models to verify correct names."""
import asyncio
import json
import httpx

API_KEY = "AIzaSyAtoRPzxS4N8bY-rUGql2IdoHknUZj9sSw"


async def main():
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url)
        data = resp.json()

    models = data.get("models", [])
    print(f"Found {len(models)} models\n")

    # Filter for gemini-3 and gemini-2.5 models
    for m in sorted(models, key=lambda x: x.get("name", "")):
        name = m.get("name", "").replace("models/", "")
        if "gemini-3" in name or "gemini-2.5" in name:
            desc = m.get("description", "")[:80]
            input_limit = m.get("inputTokenLimit", "?")
            output_limit = m.get("outputTokenLimit", "?")
            methods = m.get("supportedGenerationMethods", [])
            print(f"  {name}")
            print(f"    Input: {input_limit}  Output: {output_limit}")
            print(f"    Methods: {', '.join(methods)}")
            print(f"    Desc: {desc}")
            print()


if __name__ == "__main__":
    asyncio.run(main())
