from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import json

app = FastAPI(title="Hyperbot Dashboard")

# Cartella templates (la creiamo se non esiste)
templates_dir = Path(__file__).parent / "templates"
templates_dir.mkdir(exist_ok=True)
templates = Jinja2Templates(directory=str(templates_dir))

# Stato globale condiviso (verrà aggiornato dal bot)
bot_status = {
    "running": False,
    "mode": "PAPER",
    "network": "TESTNET",
    "symbol": "ETH",
    "mid": 0.0,
    "center": 0.0,
    "levels": 0,
    "open_orders": 0,
    "realized_pnl": 0.0,
    "leverage": 0.0,
    "kill_switch": False,
    "last_update": "",
}


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request, "status": bot_status})


@app.get("/api/status")
async def api_status():
    return bot_status


@app.get("/health")
async def health():
    return {"status": "ok"}