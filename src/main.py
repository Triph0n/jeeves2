"""
Jeeves - Inteligentní hlasový asistent pro ovládání PC
Powered by Gemini Live API - real-time voice streaming with function calling.
"""
import asyncio
import logging
import uvicorn
import webbrowser
from src.gemini_live import main as gemini_main
from src.logger import logger
from src.web_server import app

async def main():
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="warning")
    server = uvicorn.Server(config)
    
    server_task = asyncio.create_task(server.serve())
    gemini_task = asyncio.create_task(gemini_main())
    
    async def open_browser():
        await asyncio.sleep(1.5)
        await asyncio.to_thread(webbrowser.open, "http://localhost:8000")
        
    # Keep reference to avoid garbage collection
    browser_task = asyncio.create_task(open_browser())
    
    # Wait for either the server or Gemini Live to finish/exit
    done, pending = await asyncio.wait(
        [server_task, gemini_task],
        return_when=asyncio.FIRST_COMPLETED
    )
    
    logger.info("Main loop detected termination. Shutting down remaining tasks...")
    
    # If Gemini finished (e.g. from /shutdown via Web UI), we must stop Uvicorn
    if gemini_task in done:
        server.should_exit = True
    
    # If Uvicorn finished (e.g. Ctrl+C), we must cancel Gemini
    if server_task in done and not gemini_task.done():
        gemini_task.cancel()
    
    # Wait for everything to close
    for i in pending:
        i.cancel()
    
    # Suppress CancelledError outputs when finalizing
    try:
        await asyncio.gather(*pending, return_exceptions=True)
    except Exception:
        pass

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user (Ctrl+C). Goodbye!")
