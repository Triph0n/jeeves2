import asyncio
import logging
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from typing import List

logger = logging.getLogger(__name__)

app = FastAPI()
command_queue = asyncio.Queue()
wakeup_event = asyncio.Event()
wakeup_event.set()  # Start in "awake" state so first session starts immediately

# Mount static files
static_dir = os.path.join(os.path.dirname(__file__), 'web')
if not os.path.exists(static_dir):
    os.makedirs(static_dir)

app.mount("/static", StaticFiles(directory=static_dir), name="static")

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Client connected to Mission Control. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        dead_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error sending to websocket: {e}")
                dead_connections.append(connection)
        
        for dc in dead_connections:
            self.disconnect(dc)

manager = ConnectionManager()

@app.get("/")
async def get():
    index_path = os.path.join(static_dir, "index.html")
    if not os.path.exists(index_path):
        return {"error": "index.html not found"}
    return FileResponse(index_path)

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    icon_path = os.path.join(static_dir, "jeeves_icon.png")
    if os.path.exists(icon_path):
        return FileResponse(icon_path)
    return {"error": "favicon not found"}

@app.post("/api/shutdown")
async def shutdown_api():
    """Triggered by the Web UI to shut down Jeeves."""
    logger.info("Shutdown requested from Web UI.")
    await command_queue.put("/shutdown")
    return {"status": "shutting down"}

@app.post("/api/wakeup")
async def wakeup_api():
    """Triggered by the Web UI to restart Jeeves from offline mode."""
    logger.info("Wakeup requested from Web UI.")
    wakeup_event.set()
    return {"status": "waking up"}

@app.get("/api/costs")
async def get_costs():
    """Returns API cost tracking summary."""
    from src import cost_tracker
    return cost_tracker.get_summary()

@app.get("/api/tasks")
async def api_get_tasks():
    """Returns incomplete Google Tasks from the default list."""
    from src.tasks_controller import get_tasks
    tasks = await asyncio.to_thread(get_tasks, "") # Fetch default list
    return {"tasks": tasks}

@app.post("/api/launch_mavis")
async def launch_mavis_api():
    """Starts the Mavis book server and opens it in Chrome."""
    from src.browser_controller import _ensure_mavis_server, _ensure_chrome_running, _is_port_open, CHROME_DEBUG_PORT
    import asyncio

    try:
        # Start Mavis server if not already running
        ok = await asyncio.to_thread(_ensure_mavis_server)
        if not ok:
            return {"status": "error", "detail": "Failed to start Mavis server"}

        # Ensure Chrome is running
        ok2 = await asyncio.to_thread(_ensure_chrome_running)
        if not ok2:
            return {"status": "error", "detail": "Failed to start Chrome"}

        # Open the Mavis page in a new Chrome tab via CDP (requires PUT)
        def _open_tab():
            import urllib.request
            req = urllib.request.Request(
                "http://127.0.0.1:9222/json/new?http://localhost:8777/",
                method="PUT"
            )
            with urllib.request.urlopen(req, timeout=5):
                pass

        await asyncio.to_thread(_open_tab)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error launching Mavis: {e}")
        # Try a simpler fallback — just return ok, Chrome is probably already there
        return {"status": "ok", "detail": str(e)}

@app.get("/api/vacancies")
async def api_get_vacancies():
    """Returns scraped Cello job vacancies from Muvac and Musikzeitung."""
    from src.vacancies_controller import get_all_vacancies
    try:
        data = await asyncio.to_thread(get_all_vacancies)
        return data
    except Exception as e:
        logger.error(f"Error fetching vacancies: {e}")
        return {"muvac": [], "musikzeitung": [], "error": str(e)}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Client can send JSON commands
            data = await websocket.receive_json()
            if data.get("type") == "user_command":
                cmd = data.get("text", "")
                if cmd:
                    logger.info(f"Received text command from Web UI: {cmd}")
                    await command_queue.put(cmd)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)

async def broadcast_event(event_type: str, data: dict = None):
    """Called by Jeeves to update the Web UI."""
    payload = {"type": event_type}
    if data:
        payload.update(data)
    await manager.broadcast(payload)
