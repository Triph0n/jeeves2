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
import os
import sys
import asyncio
import traceback
import logging
import datetime
import pyaudio
from google import genai
from google.genai import types

from src.browser_controller import play_netflix_movie, play_youtube_video
from src.calendar_controller import get_upcoming_events, create_event
from src.weather_controller import get_current_weather
from src.mavis_controller import start_reading, stop_reading

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
- Použít chytrou asistentku 'Mavis' pro předčítání e-knih (sci-fi a fantasy) pomocí funkcí start_mavis_reading a stop_mavis_reading
- Konverzovat s uživatelem v češtině

Když se uživatel ptá na svůj program ("Co mám dnes v plánu?", "Jaké mám schůzky?"), zavolej get_upcoming_events.
Když chce uživatel naplánovat novou schůzku ("Naplánuj mi zítra v 15:00..."), zavolej create_event. Dbej na to, abys správně převedl čas na formát ISO. Dnešní lokální čas je {datetime.datetime.now().isoformat()}
Když se uživatel zeptá na počasí ("Jak je venku?", "Jaké je počasí?"), zavolej funkci get_current_weather a pak jej sděl uživateli. POZOR: Počasí oznamuj opravdu jen tehdy, když se na to sám zeptá.
Když tě uživatel požádá o čtení sci-fi nebo fantasy knihy (např. "Zavolej Mavis, ať mi přečte Hobita", "Chci číst Foundation od Asimova"), zavolej funkci start_mavis_reading s názvem/čemu hledá. Až ji zavoláš, odpověz "Předávám slovo Mavis" (nebo podobně).
Když tě uživatel požádá, ať Mavis přestane číst ("Zastav Mavis", "Přestaňte číst"), zavolej funkci stop_mavis_reading a potvrď zastavení.
Když uživatel chce pustit film/seriál na Netflixu, zavolej funkci play_netflix_movie.
Když uživatel chce pustit video, písničku nebo trailer na YouTube, zavolej funkci play_youtube_video. To platí obecně i pokud nespecifikuje platformu, ale ze zadání je patrné, že jde spíše o video z internetu než dlouhý film.
Když uživatel řekne "konec", "vypni se" nebo "ukonči se", rozluč se a ukonči konverzaci.
Odpovídej krátce a přirozeně, jako by ses bavil s kamarádem.
Při startu konverzace vždy nejprve sám od sebe pozdrav: "Dobrý den, pane." a pak čekej na instrukce."""

# Function declarations for tool use
PLAY_MOVIE_TOOL = {
    "name": "play_netflix_movie",
    "description": "Spustí film nebo seriál na Netflixu. Otevře prohlížeč, vyhledá film a pustí ho.",
    "parameters": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Název filmu nebo seriálu k přehrání, např. 'Matrix', 'Stranger Things'"
            }
        },
        "required": ["title"]
    }
}

PLAY_YOUTUBE_TOOL = {
    "name": "play_youtube_video",
    "description": "Spustí video na YouTube. Otevře prohlížeč, vyhledá video podle názvu a pustí ho.",
    "parameters": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Název videa nebo tématu k vyhledání a přehrání na YouTube."
            }
        },
        "required": ["title"]
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
                "description": "Maximální počet nadcházejících událostí, které se mají vrátit (výchozí 10)."
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
            "summary": {
                "type": "string",
                "description": "Název schůzky nebo události."
            },
            "start_time": {
                "type": "string",
                "description": "Čas začátku schůzky ve formátu ISO 8601, např. '2026-03-10T15:00:00'."
            },
            "end_time": {
                "type": "string",
                "description": "Čas konce schůzky ve formátu ISO 8601, např. '2026-03-10T16:00:00'."
            },
            "description": {
                "type": "string",
                "description": "Volitelný popis schůzky."
            }
        },
        "required": ["summary", "start_time", "end_time"]
    }
}

GET_WEATHER_TOOL = {
    "name": "get_current_weather",
    "description": "Zjistí podle polohy počítače aktuální počasí (teplotu, oblačnost, vítr).",
    "parameters": {
        "type": "object",
        "properties": {}
    }
}

START_MAVIS_TOOL = {
    "name": "start_mavis_reading",
    "description": "Zavolá čtečku Mavis, která vyhledá a začne číst e-knihu.",
    "parameters": {
        "type": "object",
        "properties": {
            "search_query": {
                "type": "string",
                "description": "Jméno knihy nebo autora (např. 'Pán prstenů', 'Asimov')."
            }
        },
        "required": ["search_query"]
    }
}

STOP_MAVIS_TOOL = {
    "name": "stop_mavis_reading",
    "description": "Zastaví čtečku Mavis, pokud zrovna čte knihu.",
    "parameters": {
        "type": "object",
        "properties": {}
    }
}

TOOLS = [{"function_declarations": [PLAY_MOVIE_TOOL, PLAY_YOUTUBE_TOOL, GET_CALENDAR_EVENTS_TOOL, CREATE_CALENDAR_EVENT_TOOL, GET_WEATHER_TOOL, START_MAVIS_TOOL, STOP_MAVIS_TOOL]}]


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
                    await asyncio.to_thread(stream.write, audio_data)
                except asyncio.TimeoutError:
                    continue
        finally:
            stream.stop_stream()
            stream.close()
    
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
                    await self._handle_tool_calls(session, response.tool_call)
    
    async def _handle_tool_calls(self, session, tool_call):
        """Execute function calls requested by Gemini and send results back."""
        function_responses = []
        
        for fc in tool_call.function_calls:
            logger.info(f"Function call: {fc.name}({fc.args})")
            
            if fc.name == "play_netflix_movie":
                title = fc.args.get("title", "")
                logger.info(f"Executing play_netflix_movie('{title}')...")
                
                try:
                    success = await asyncio.to_thread(play_netflix_movie, title)
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
            elif fc.name == "play_youtube_video":
                title = fc.args.get("title", "")
                logger.info(f"Executing play_youtube_video('{title}')...")
                
                try:
                    success = await asyncio.to_thread(play_youtube_video, title)
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
                    msg = await asyncio.to_thread(start_reading, query)
                    result = {
                        "success": True,
                        "message": msg
                    }
                except Exception as e:
                    logger.error(f"Mavis start error: {e}")
                    result = {"success": False, "message": str(e)}
                
                function_responses.append(
                    types.FunctionResponse(id=fc.id, name=fc.name, response=result)
                )
            elif fc.name == "stop_mavis_reading":
                logger.info("Executing stop_mavis_reading()...")
                
                try:
                    msg = await asyncio.to_thread(stop_reading)
                    result = {
                        "success": True,
                        "message": msg
                    }
                except Exception as e:
                    logger.error(f"Mavis stop error: {e}")
                    result = {"success": False, "message": str(e)}
                
                function_responses.append(
                    types.FunctionResponse(id=fc.id, name=fc.name, response=result)
                )
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
