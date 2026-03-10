"""
Gemini Live API Module - Real-time voice assistant using WebSocket streaming.
Replaces the separate STT + LLM + TTS pipeline with a single Gemini Live session.
Audio flows: Microphone → Gemini Live → Speaker, with function calling for browser automation.
"""
import asyncio
import os
import sys
import traceback
import logging
import datetime
import pyaudio
from dotenv import load_dotenv
from google import genai
from google.genai import types
from src.logger import logger


from src.weather_controller import get_current_weather
from src.calendar_controller import get_upcoming_events, create_event
from src.browser_controller import play_netflix_movie as play_netflix, play_youtube_video as play_youtube, play_scifi_book, stop_scifi_book
from src.library_controller import search_library, get_books_by_author, get_library_stats
from src.web_server import broadcast_event, command_queue

load_dotenv()

# Audio settings
INPUT_SAMPLE_RATE = 16000   # Gemini expects 16kHz input
OUTPUT_SAMPLE_RATE = 24000  # Gemini outputs 24kHz
CHANNELS = 1
INPUT_CHUNK_SIZE = 1024     # ~64ms chunks at 16kHz
FORMAT = pyaudio.paInt16

# Gemini model — gemini-2.0-flash has stable function calling support
# Note: gemini-2.5-flash-native-audio-preview has a known bug (1008) with tool calls
MODEL = "gemini-2.5-flash-native-audio-latest"

# System instruction in Czech
SYSTEM_INSTRUCTION = """Jsi Jeeves, inteligentní hlasový asistent pro ovládání počítače. Mluvíš česky, jsi stručný, vtipný a přátelský jako správný britský butler.

Tvé hlavní schopnosti:
- Pouštět filmy a seriály na Netflixu pomocí funkce play_netflix_movie
- Pouštět videa na YouTube pomocí funkce play_youtube_video
- Číst a zapisovat události do Google Kalendáře (get_upcoming_events, create_event)
- Sdílet aktuální informace o počasí podle lokace počítače pomocí get_current_weather (POUZE na vyžádání)
- Použít chytrou asistentku 'Mavis' pro předčítání e-knih (sci-fi a fantasy) pomocí funkcí play_scifi_book a stop_scifi_book
- Vyhledávat a analyzovat knihy v lokální databázi Sci-Fi knihovny (funkce search_library, get_books_by_author a get_library_stats)
- Konverzovat s uživatelem v češtině

Když se uživatel ptá na svůj program ("Co mám dnes v plánu?", "Jaké mám schůzky?"), zavolej get_upcoming_events.
Když chce uživatel naplánovat novou schůzku ("Naplánuj mi zítra v 15:00..."), zavolej create_event. Dbej na to, abys správně převedl čas na formát ISO. Dnešní lokální čas je {datetime.datetime.now().isoformat()}
Když se uživatel zeptá na počasí ("Jak je venku?", "Jaké je počasí?"), zavolej funkci get_current_weather a pak jej sděl uživateli. POZOR: Počasí oznamuj opravdu jen tehdy, když se na to sám zeptá.
Když tě uživatel požádá o čtení sci-fi nebo fantasy knihy (např. "Zavolej Mavis, ať mi přečte Hobita", "Chci číst Foundation od Asimova"), zavolej funkci play_scifi_book s názvem knihy. Až ji zavoláš, odpověz "Předávám slovo Mavis" (nebo podobně).
Když tě uživatel požádá, ať Mavis přestane číst ("Zastav Mavis", "Přestaňte číst"), zavolej funkci stop_scifi_book a potvrď zastavení.
Když se uživatel ptá co máme v databázi, jestli máme nějakou knihu atd., použij search_library.
Když uživatel chce vědět, co máme od určitého autora, použij get_books_by_author.
Když se ptá na statistiky knihovny (počet knih atd.), použij get_library_stats.
Když uživatel chce pustit film/seriál na Netflixu, zavolej funkci play_netflix.
Když uživatel chce pustit video, písničku nebo trailer na YouTube, zavolej funkci play_youtube. To platí obecně i pokud nespecifikuje platformu, ale ze zadání je patrné, že jde spíše o video z internetu než dlouhý film.
Když uživatel řekne "konec", "vypni se" nebo "ukonči se", rozluč se a ukonči konverzaci.
Odpovídej krátce a přirozeně, jako by ses bavil s kamarádem.
Při startu konverzace vždy nejprve sám od sebe pozdrav: "Dobrý den, pane." a pak čekej na instrukce."""

# Function declarations for tool use
GET_CURRENT_WEATHER_TOOL = {
    "name": "get_current_weather",
    "description": "Zjistí podle polohy počítače aktuální počasí (teplotu, oblačnost, vítr).",
    "parameters": {
        "type": "object",
        "properties": {}
    }
}

GET_WEATHER_FORECAST_TOOL = {
    "name": "get_weather_forecast",
    "description": "Zjistí předpověď počasí pro aktuální polohu počítače na následující dny.",
    "parameters": {
        "type": "object",
        "properties": {
            "days": {
                "type": "integer",
                "description": "Počet dní, pro které se má vrátit předpověď (výchozí 3)."
            }
        }
    }
}

PLAY_NETFLIX_TOOL = {
    "name": "play_netflix",
    "description": "Spustí film nebo seriál na Netflixu. Otevře prohlížeč, vyhledá film a pustí ho.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Název filmu nebo seriálu k přehrání, např. 'Matrix', 'Stranger Things'"
            }
        },
        "required": ["query"]
    }
}

PLAY_YOUTUBE_TOOL = {
    "name": "play_youtube",
    "description": "Spustí video na YouTube. Otevře prohlížeč, vyhledá video podle názvu a pustí ho.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Název videa nebo tématu k vyhledání a přehrání na YouTube."
            }
        },
        "required": ["query"]
    }
}

CALL_MAVIS_TOOL = {
    "name": "play_scifi_book",
    "description": "Spustí aplikaci Mavis (Sci-Fi knihovnu) ve webovém prohlížeči a začne předčítat konkrétní knihu. Použij, když uživatel řekne 'Zavolej Mavis ať přečte...' nebo 'Pusť mi audioknihu...'. Parametr query obsahuje název knihy nebo jméno autora.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Název knihy nebo jméno autora."
            }
        },
        "required": ["query"]
    }
}

STOP_MAVIS_TOOL = {
    "name": "stop_scifi_book",
    "description": "Zastaví předčítání běžící knihy v Mavis (Sci-Fi knihovně) ve webovém prohlížeči. Použij, když uživatel řekne 'Mavis stop', 'Zastav Mavis', 'Vypni audioknihu' atd.",
    "parameters": {
        "type": "object",
        "properties": {}
    }
}

# Library DB Tools
SEARCH_LIBRARY_TOOL = {
    "name": "search_library",
    "description": "Vyhledá knihy ve tvé lokální Sci-Fi databázi (Mavis knihovna) podle názvu nebo klíčového slova. Použij když se uživatel ptá, jestli máme nějakou konkrétní knihu nebo knihu o něčem.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Název knihy nebo klíčové slovo pro vyhledávání."
            }
        },
        "required": ["query"]
    }
}

GET_AUTHOR_BOOKS_TOOL = {
    "name": "get_books_by_author",
    "description": "Vrátí seznam všech knih v databázi od zadaného autora. Použij když chce uživatel vědět, jaké knihy od konkrétního autora máme.",
    "parameters": {
        "type": "object",
        "properties": {
            "author": {
                "type": "string",
                "description": "Jméno autora."
            }
        },
        "required": ["author"]
    }
}

GET_LIBRARY_STATS_TOOL = {
    "name": "get_library_stats",
    "description": "Vrátí základní statistiky o tvé lokální Sci-Fi databázi (počet knih celkem, počet autorů a zastoupení žánrů). Použij když se tě uživatel zeptá, kolik knih máme celkem v knihovně.",
    "parameters": {
        "type": "object",
        "properties": {}
    }
}

GET_CALENDAR_EVENTS_TOOL = {
    "name": "get_upcoming_events",
    "description": "Vrátí seznam nadcházejících událostí z uživatelova kalendáře (dnešní a budoucí schůzky).",
    "parameters": {
        "type": "object",
        "properties": {
            "max_results": {
                "type": "integer",
                "description": "Maximální počet nadcházejících událostí."
            }
        }
    }
}

CREATE_CALENDAR_EVENT_TOOL = {
    "name": "create_event",
    "description": "Vytvoří novou událost v kalendáři.",
    "parameters": {
        "type": "object",
        "properties": {
            "summary": { "type": "string", "description": "Název schůzky." },
            "start_time": { "type": "string", "description": "Čas začátku." },
            "end_time": { "type": "string", "description": "Čas konce." },
            "description": { "type": "string", "description": "Volitelný popis." }
        },
        "required": ["summary", "start_time", "end_time"]
    }
}

# Combining native generic tools and explicit function calling intent tools
ALL_TOOLS = [
    GET_CURRENT_WEATHER_TOOL,
    PLAY_NETFLIX_TOOL,
    PLAY_YOUTUBE_TOOL,
    CALL_MAVIS_TOOL,
    STOP_MAVIS_TOOL,
    SEARCH_LIBRARY_TOOL,
    GET_AUTHOR_BOOKS_TOOL,
    GET_LIBRARY_STATS_TOOL,
    GET_CALENDAR_EVENTS_TOOL,
    CREATE_CALENDAR_EVENT_TOOL
]

TOOLS = [{"function_declarations": ALL_TOOLS}]


class JeevesLive:
    """Real-time voice assistant powered by Gemini Live API."""
    
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key or api_key == "your_gemini_api_key_here":
            logger.error("GEMINI_API_KEY is not set in .env!")
            raise ValueError("Missing GEMINI_API_KEY")
        
        self.client = genai.Client(api_key=api_key)
        self.audio = pyaudio.PyAudio()
        self.is_running = False
        self.audio_out_queue = asyncio.Queue()
        self.current_state = "offline"
        
    async def set_state(self, state: str, message: str = ""):
        """Broadcast state changes to Web UI."""
        if self.current_state != state:
            self.current_state = state
            await broadcast_event("state_change", {"state": state})
        if message:
            await broadcast_event("action_log", {"message": message})
        
    async def start(self):
        """Start the Gemini Live session with audio streaming."""
        
        config = {
            "response_modalities": ["AUDIO"],
            "tools": TOOLS,
            "system_instruction": SYSTEM_INSTRUCTION,
            "speech_config": {"voice_config": {"prebuilt_voice_config": {"voice_name": "Fenrir"}}},
        }
        
        logger.info("=" * 60)
        logger.info("  JEEVES Live — Gemini Voice Assistant")
        logger.info("  Mluv česky, Jeeves naslouchá. Řekni 'konec' pro ukončení.")
        logger.info("=" * 60)
        
        try:
            async with self.client.aio.live.connect(
                model=MODEL, 
                config=config
            ) as session:
                logger.info("Gemini Live session connected!")
                self.is_running = True
                
                # Run three tasks concurrently:
                # 1. Capture audio from microphone
                # 2. Play audio responses from Gemini
                # 3. Receive and process responses from Gemini
                async with asyncio.TaskGroup() as tg:
                    tg.create_task(self._capture_audio(session))
                    tg.create_task(self._play_audio())
                    tg.create_task(self._receive_responses(session))
                    tg.create_task(self._process_web_commands(session))
                        
        except asyncio.CancelledError:
            logger.info("Session cancelled.")
        except ExceptionGroup as eg:
            # TaskGroup wraps exceptions in ExceptionGroup
            for e in eg.exceptions:
                if not isinstance(e, asyncio.CancelledError):
                    logger.error(f"Task error: {e}")
                    traceback.print_exception(type(e), e, e.__traceback__)
        except Exception as e:
            logger.exception("Gemini Live session error:")
        finally:
            self.is_running = False
            asyncio.create_task(self.set_state("offline", "Spojení přerušeno"))
            self.audio.terminate()
            logger.info("Jeeves Live session ended.")
    
    async def _capture_audio(self, session):
        """Capture audio from microphone and send to Gemini Live."""
        stream = self.audio.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=INPUT_SAMPLE_RATE,
            input=True,
            frames_per_buffer=INPUT_CHUNK_SIZE,
        )
        
        logger.info("Microphone active. Listening...")
        await self.set_state("listening", "Naslouchám...")
        
        try:
            while self.is_running:
                # Read audio from microphone (non-blocking via executor)
                data = await asyncio.to_thread(
                    stream.read, INPUT_CHUNK_SIZE, exception_on_overflow=False
                )
                
                # Send raw PCM audio to Gemini
                await session.send_realtime_input(
                    audio=types.Blob(
                        data=data,
                        mime_type="audio/pcm;rate=16000"
                    )
                )
        finally:
            stream.stop_stream()
            stream.close()
    
    async def _play_audio(self):
        """Play audio responses from Gemini through speakers."""
        stream = self.audio.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=OUTPUT_SAMPLE_RATE,
            output=True,
            frames_per_buffer=2048,
        )
        
        try:
            while self.is_running:
                try:
                    audio_data = await asyncio.wait_for(
                        self.audio_out_queue.get(), timeout=0.1
                    )
                    await self.set_state("speaking")
                    await asyncio.to_thread(stream.write, audio_data)
                except asyncio.TimeoutError:
                    if self.current_state == "speaking":
                        await self.set_state("listening")
                    continue
        finally:
            stream.stop_stream()
            stream.close()

    async def _process_web_commands(self, session):
        """Listen for text commands originating from the Web UI."""
        try:
            while self.is_running:
                cmd = await command_queue.get()
                logger.info(f"Sending web command to Gemini: {cmd}")
                await self.set_state("thinking", "Píšu...")
                # Native fast endpoint:
                await session.send(input=cmd, end_of_turn=True)
        except asyncio.CancelledError:
            pass
    
    async def _receive_responses(self, session):
        """Receive and process responses from Gemini Live."""
        while self.is_running:
            async for response in session.receive():
                # Handle audio output
                if response.data is not None:
                    self.audio_out_queue.put_nowait(response.data)
                
                # Handle server content (turn completion etc.)
                if response.server_content and response.server_content.turn_complete:
                    logger.debug("Gemini turn complete.")
                
                # Handle function calls
                if response.tool_call:
                    logger.info("Gemini requested tool call!")
                    await self.set_state("thinking", "Zpracovávám požadavek...")
                    await self._handle_tool_calls(session, response.tool_call)
    
    async def _handle_tool_calls(self, session, tool_call):
        """Execute function calls requested by Gemini and send results back."""
        function_responses = []
        
        for fc in tool_call.function_calls:
            logger.info(f"Function call: {fc.name}({fc.args})")
            await self.set_state("thinking", f"Provádím: {fc.name}")
            
            if fc.name == "play_netflix_movie" or fc.name == "play_netflix": # Handle both old and new name
                title = fc.args.get("title", fc.args.get("query", ""))
                logger.info(f"Executing play_netflix('{title}')...")
                
                try:
                    success = await asyncio.to_thread(play_netflix, title)
                    result = {
                        "success": success,
                        "message": f"Film '{title}' {'byl úspěšně spuštěn' if success else 'se nepodařilo spustit'} na Netflixu."
                    }
                except Exception as e:
                    logger.error(f"Browser automation error: {e}")
                    result = {
                        "success": False,
                        "message": f"Chyba při spouštění filmu: {str(e)}"
                    }
                
                function_responses.append(
                    types.FunctionResponse(
                        id=fc.id,
                        name=fc.name,
                        response=result
                    )
                )
            elif fc.name == "play_youtube_video" or fc.name == "play_youtube": # Handle both old and new name
                title = fc.args.get("title", fc.args.get("query", ""))
                logger.info(f"Executing play_youtube('{title}')...")
                
                try:
                    success = await asyncio.to_thread(play_youtube, title)
                    result = {
                        "success": success,
                        "message": f"Video '{title}' {'bylo úspěšně spuštěno' if success else 'se nepodařilo spustit'} na YouTube."
                    }
                except Exception as e:
                    logger.error(f"Browser automation error: {e}")
                    result = {
                        "success": False,
                        "message": f"Chyba při spouštění videa: {str(e)}"
                    }
                
                function_responses.append(
                    types.FunctionResponse(
                        id=fc.id,
                        name=fc.name,
                        response=result
                    )
                )
            elif fc.name == "get_upcoming_events":
                max_results = int(fc.args.get("max_results", 10))
                logger.info(f"Executing get_upcoming_events({max_results})...")
                
                try:
                    events = await asyncio.to_thread(get_upcoming_events, max_results)
                    result = {
                        "success": True,
                        "events": events
                    }
                except Exception as e:
                    logger.error(f"Calendar error: {e}")
                    result = {
                        "success": False,
                        "message": str(e)
                    }
                
                function_responses.append(
                    types.FunctionResponse(
                        id=fc.id,
                        name=fc.name,
                        response=result
                    )
                )
            elif fc.name == "create_event":
                summary = fc.args.get("summary", "")
                start_time = fc.args.get("start_time", "")
                end_time = fc.args.get("end_time", "")
                desc = fc.args.get("description", "")
                logger.info(f"Executing create_event('{summary}', start='{start_time}', end='{end_time}')...")
                
                try:
                    msg = await asyncio.to_thread(create_event, summary, start_time, end_time, desc)
                    result = {
                        "success": True,
                        "message": msg
                    }
                except Exception as e:
                    logger.error(f"Calendar error: {e}")
                    result = {
                        "success": False,
                        "message": str(e)
                    }
                
                function_responses.append(
                    types.FunctionResponse(
                        id=fc.id,
                        name=fc.name,
                        response=result
                    )
                )
            elif fc.name == "get_current_weather":
                logger.info("Executing get_current_weather()...")
                
                try:
                    weather = await asyncio.to_thread(get_current_weather)
                    result = {
                        "success": True,
                        "message": weather
                    }
                except Exception as e:
                    logger.error(f"Weather error: {e}")
                    result = {
                        "success": False,
                        "message": str(e)
                    }
                
                function_responses.append(
                    types.FunctionResponse(
                        id=fc.id,
                        name=fc.name,
                        response=result
                    )
                )
            elif fc.name == "start_mavis_reading":
                query = fc.args.get("search_query", "")
                logger.info(f"Executing start_mavis_reading('{query}')...")
                
                try:
                    # Run search+start in background to not block Gemini loop
                    success = await asyncio.to_thread(play_scifi_book, query)
                    if success:
                        result = {"success": True, "message": f"Mavis začala číst knihu '{query}'."}
                    else:
                        result = {"success": False, "message": "Nenalezena žádná kniha nebo se nepodařilo otevřít čtečku."}
                except Exception as e:
                    logger.error(f"Mavis start error: {e}")
                    result = {"success": False, "message": str(e)}
                
                function_responses.append(
                    types.FunctionResponse(id=fc.id, name=fc.name, response=result)
                )
            elif fc.name == "stop_mavis_reading":
                logger.info("Executing stop_mavis_reading()...")
                
                try:
                    success = await asyncio.to_thread(stop_scifi_book)
                    if success:
                        result = {"success": True, "message": "Mavis přestala číst a knihovna byla pozastavena."}
                    else:
                        result = {"success": False, "message": "Při zastavování čtečky Mavis došlo k chybě."}
                except Exception as e:
                    logger.error(f"Mavis stop error: {e}")
                    result = {"success": False, "message": str(e)}
                
                function_responses.append(
                    types.FunctionResponse(id=fc.id, name=fc.name, response=result)
                )
            elif fc.name == "search_library":
                query = fc.args.get("query", "")
                logger.info(f"Executing search_library('{query}')...")
                try:
                    books = await asyncio.to_thread(search_library, query)
                    result = {"success": True, "books": books}
                except Exception as e:
                    logger.error(f"Library search error: {e}")
                    result = {"success": False, "message": str(e)}
                function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response=result))
            elif fc.name == "get_books_by_author":
                author = fc.args.get("author", "")
                logger.info(f"Executing get_books_by_author('{author}')...")
                try:
                    books = await asyncio.to_thread(get_books_by_author, author)
                    result = {"success": True, "books": books}
                except Exception as e:
                    logger.error(f"Library author search error: {e}")
                    result = {"success": False, "message": str(e)}
                function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response=result))
            elif fc.name == "get_library_stats":
                logger.info(f"Executing get_library_stats()...")
                try:
                    stats = await asyncio.to_thread(get_library_stats)
                    result = {"success": True, "stats": stats}
                except Exception as e:
                    logger.error(f"Library stats error: {e}")
                    result = {"success": False, "message": str(e)}
                function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response=result))
            else:
                logger.warning(f"Unknown function: {fc.name}")
                function_responses.append(
                    types.FunctionResponse(
                        id=fc.id,
                        name=fc.name,
                        response={"error": f"Unknown function: {fc.name}"}
                    )
                )
        
        if function_responses:
            await session.send_tool_response(function_responses=function_responses)
            logger.info("Tool response sent back to Gemini.")


async def main():
    """Entry point for Jeeves Live."""
    jeeves = JeevesLive()
    await jeeves.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user (Ctrl+C). Goodbye!")
