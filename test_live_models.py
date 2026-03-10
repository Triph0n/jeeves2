import os
import asyncio
from dotenv import load_dotenv
from google import genai

load_dotenv()

async def test_model(model_name):
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    try:
        async with client.aio.live.connect(model=model_name, config={"response_modalities": ["AUDIO"]}) as session:
            print(f"SUCCESS: {model_name} connected successfully!")
            return True
    except Exception as e:
        print(f"FAILED: {model_name} failed with error: {e}")
        return False

async def main():
    models_to_test = [
        "gemini-2.0-flash",
        "gemini-2.5-flash",
        "gemini-2.5-flash-native-audio-latest",
        "gemini-2.5-pro",
    ]
    for m in models_to_test:
        await test_model(m)

if __name__ == "__main__":
    asyncio.run(main())
