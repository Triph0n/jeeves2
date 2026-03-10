import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

print("Fetching all models...")
for m in client.models.list():
    if "gemini-2" in m.name or "gemini-2" in getattr(m, 'display_name', ''):
        methods = getattr(m, 'supported_generation_methods', [])
        print(f"Model ID: {m.name}")
        print(f"  Methods: {methods}")
