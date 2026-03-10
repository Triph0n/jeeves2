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
