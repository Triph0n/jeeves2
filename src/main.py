"""
Jeeves - Inteligentní hlasový asistent pro ovládání PC
Powered by Gemini Live API - real-time voice streaming with function calling.
"""
import asyncio
import logging
import uvicorn
from src.gemini_live import main as gemini_main
from src.logger import logger
from src.web_server import app

async def run_server():
    logger.info("Starting Mission Control web server on http://localhost:8000")
    # Listen on all interfaces so mobile devices can access it
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve()

async def main():
    server_task = asyncio.create_task(run_server())
    gemini_task = asyncio.create_task(gemini_main())
    
    await asyncio.gather(server_task, gemini_task)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user (Ctrl+C). Goodbye!")
