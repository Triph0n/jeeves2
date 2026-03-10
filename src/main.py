"""
Jeeves - Inteligentní hlasový asistent pro ovládání PC
Powered by Gemini Live API - real-time voice streaming with function calling.
"""
import asyncio
from src.gemini_live import main as gemini_main
from src.logger import logger


if __name__ == "__main__":
    try:
        asyncio.run(gemini_main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user (Ctrl+C). Goodbye!")
