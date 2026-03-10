"""
Intent Parser Module - LLM-based intent extraction
Takes Czech text from STT and extracts structured JSON intent using Gemini API.
"""
import os
import json
from dotenv import load_dotenv
from src.logger import logger

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

SYSTEM_PROMPT = """Jsi hlasový asistent Jeeves. Tvým úkolem je z uživatelova příkazu v češtině extrahovat strukturovaný záměr (intent) a vrátit ho VÝHRADNĚ jako platný JSON.

Podporované akce:
- play_movie: Spustit film/seriál na streamovací platformě
- search_movie: Pouze vyhledat film/seriál (bez spuštění)
- unknown: Nerozpoznaný příkaz

Platformy: netflix, disney_plus, hbo_max, youtube

Formát odpovědi (POUZE JSON, nic jiného):
{"action": "<akce>", "platform": "<platforma>", "title": "<název filmu/seriálu>", "response": "<krátká česká odpověď pro uživatele>"}

Příklady:
Vstup: "Pusť mi Matrix na Netflixu"
{"action": "play_movie", "platform": "netflix", "title": "Matrix", "response": "Jdu na to, pouštím Matrix na Netflixu."}

Vstup: "Najdi mi něco o robotech na Disney Plus"  
{"action": "search_movie", "platform": "disney_plus", "title": "roboti", "response": "Hledám filmy o robotech na Disney Plus."}

Vstup: "Jaké je počasí?"
{"action": "unknown", "platform": null, "title": null, "response": "Promiň, tohle zatím neumím. Umím pouštět filmy na Netflixu a dalších platformách."}

DŮLEŽITÉ: Odpovídej POUZE platným JSON objektem. Žádný další text."""


def parse_intent(user_text: str) -> dict | None:
    """
    Parse user's Czech text into a structured intent using Gemini API.
    
    Args:
        user_text: Transcribed Czech speech from STT.
    
    Returns:
        Dict with keys: action, platform, title, response. Or None on error.
    """
    if not GEMINI_API_KEY or GEMINI_API_KEY == "your_gemini_api_key_here":
        logger.warning("GEMINI_API_KEY not set. Using offline fallback parser.")
        return _fallback_parse(user_text)
    
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        
        model = genai.GenerativeModel("gemini-2.0-flash-lite")
        
        response = model.generate_content(
            f"{SYSTEM_PROMPT}\n\nVstup: \"{user_text}\"",
            generation_config=genai.types.GenerationConfig(
                temperature=0.1,
                max_output_tokens=200,
            )
        )
        
        raw_text = response.text.strip()
        
        # Strip markdown code fences if present
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[-1]
            raw_text = raw_text.rsplit("```", 1)[0].strip()
        
        intent = json.loads(raw_text)
        logger.info(f"Parsed intent: {intent}")
        return intent
        
    except json.JSONDecodeError as e:
        logger.error(f"LLM returned invalid JSON: {raw_text[:200]}")
        return _fallback_parse(user_text)
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        return _fallback_parse(user_text)


def _fallback_parse(user_text: str) -> dict:
    """
    Simple offline keyword-based fallback parser for when API is unavailable.
    """
    text_lower = user_text.lower()
    
    # Detect platform
    platform = "netflix"  # default
    if "disney" in text_lower:
        platform = "disney_plus"
    elif "hbo" in text_lower:
        platform = "hbo_max"
    elif "youtube" in text_lower:
        platform = "youtube"
    
    # Detect action
    action = "unknown"
    title = None
    
    play_keywords = ["pusť", "spusť", "zahraj", "přehraj", "hraj", "dej", "pusti", "puť"]
    search_keywords = ["najdi", "hledej", "vyhledej", "najít"]
    
    for kw in play_keywords:
        if kw in text_lower:
            action = "play_movie"
            # Try to extract title: everything after the keyword, cleaned up
            parts = text_lower.split(kw, 1)
            if len(parts) > 1:
                title = _clean_title(parts[1])
            break
    
    if action == "unknown":
        for kw in search_keywords:
            if kw in text_lower:
                action = "search_movie"
                parts = text_lower.split(kw, 1)
                if len(parts) > 1:
                    title = _clean_title(parts[1])
                break
    
    response_map = {
        "play_movie": f"Jdu na to, pouštím {title or 'film'} na {platform}.",
        "search_movie": f"Hledám {title or 'film'} na {platform}.",
        "unknown": "Promiň, nerozuměl jsem. Zkus to prosím znovu.",
    }
    
    result = {
        "action": action,
        "platform": platform,
        "title": title,
        "response": response_map[action],
    }
    logger.info(f"Fallback parsed intent: {result}")
    return result


def _clean_title(raw: str) -> str | None:
    """Clean up extracted title from raw text."""
    # Remove common prepositions and platform names
    remove_words = ["mi", "na", "netflixu", "netflix", "disney", "plus", "hbo", "youtube", "prosím", "film"]
    words = raw.strip().split()
    cleaned = [w for w in words if w.lower() not in remove_words]
    title = " ".join(cleaned).strip(" .,!?")
    return title if title else None


if __name__ == "__main__":
    logger.info("Testing intent parser module...")
    
    test_phrases = [
        "Pusť mi Matrix na Netflixu",
        "Najdi něco o robotech na Disney Plus",
        "Jaké je počasí?",
        "Dej mi Inception",
        "Spusť Temný rytíř",
    ]
    
    for phrase in test_phrases:
        logger.info(f"\nInput: '{phrase}'")
        result = parse_intent(phrase)
        logger.info(f"Result: {json.dumps(result, ensure_ascii=False, indent=2)}")
