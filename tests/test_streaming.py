"""Quick streaming test for Gemini models via our AgentLLM."""
import asyncio
import time
from cvc.agent.llm import AgentLLM

API_KEY = "AIzaSyAtoRPzxS4N8bY-rUGql2IdoHknUZj9sSw"


async def test_stream(model: str):
    llm = AgentLLM("google", API_KEY, model)
    t0 = time.monotonic()
    txt = ""
    try:
        async for e in llm.chat_stream(
            messages=[{"role": "user", "content": "Say hello briefly."}],
            tools=[], temperature=0.7, max_tokens=200,
        ):
            if e.type == "text_delta":
                txt += e.text
            elif e.type == "done":
                pass
    except Exception as ex:
        print(f"  {model}: ERROR - {str(ex)[:100]}  ({time.monotonic()-t0:.1f}s)")
        return
    finally:
        await llm.close()

    elapsed = time.monotonic() - t0
    status = "PASS" if txt.strip() else "FAIL: empty"
    print(f"  {model}: '{txt.strip()[:80]}'  ({elapsed:.1f}s) [{status}]")


async def main():
    print("=== Streaming tests ===")
    await test_stream("gemini-2.5-flash")
    await test_stream("gemini-3-flash-preview")
    # Skip gemini-3-pro-preview — takes 2+ minutes, tested separately
    print("\n=== DONE ===")


if __name__ == "__main__":
    asyncio.run(main())
