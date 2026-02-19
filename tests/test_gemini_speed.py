"""Quick test: verify Gemini 3 Pro responds fast with thinkingBudget."""
import asyncio, time
from cvc.agent.llm import AgentLLM

API_KEY = "AIzaSyAtoRPzxS4N8bY-rUGql2IdoHknUZj9sSw"

async def test_model(model: str):
    llm = AgentLLM("google", API_KEY, model)
    t0 = time.time()
    text = ""
    try:
        async for event in llm.chat_stream(
            messages=[{"role": "user", "content": "Say hello in one sentence."}],
            tools=[], temperature=0.7, max_tokens=100,
        ):
            if event.type == "text_delta":
                text += event.text
            elif event.type == "done":
                pass
        elapsed = time.time() - t0
        print(f"  {model}: {elapsed:.1f}s — {text!r}")
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  {model}: {elapsed:.1f}s — ERROR: {str(e)[:120]}")
    finally:
        await llm.close()

async def main():
    print("Testing Gemini models (thinkingBudget approach):\n")
    for model in ["gemini-2.5-flash", "gemini-3-flash-preview", "gemini-3-pro-preview"]:
        await test_model(model)
    print("\nDone.")

asyncio.run(main())
