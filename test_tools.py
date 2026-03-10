import os
import asyncio
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

PLAY_MOVIE_TOOL = {
    "name": "play_netflix_movie",
    "description": "Spustí film nebo seriál.",
    "parameters": {
        "type": "object",
        "properties": {
            "title": {"type": "string"}
        },
        "required": ["title"]
    }
}
TOOLS = [{"function_declarations": [PLAY_MOVIE_TOOL]}]

async def test_tool_support(model_name):
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    try:
        async with client.aio.live.connect(
            model=model_name, 
            config={"response_modalities": ["AUDIO"], "tools": TOOLS}
        ) as session:
            print(f"SUCCESS: {model_name} connected with tools successfully!")
            return True
    except Exception as e:
        print(f"FAILED: {model_name} failed with tools: {e}")
        return False

async def main():
    await test_tool_support("gemini-2.5-flash-native-audio-latest")

if __name__ == "__main__":
    asyncio.run(main())
