"""Local replay-first platform: submit, simulate in a worker, watch later."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import threading
import uuid
import subprocess
import sys
import tempfile
import json
import hashlib
import io
import zipfile
from functools import lru_cache
from ..player.process import terminate_tree, validate_player
from ..player.example import ExamplePlayer

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..simulator.types.identifiers import PlayerId
from .bot_registry import BotRegistry
from .bot_runner import BotRunner
from .recording import RecordingSimulator
from .replay_store import ReplayStore
from .room_service import RoomService
from .auth import AuthService

DATABASE_URL = os.getenv("CATAN_DB_URL", "sqlite:///catan_platform.db")
default_replays = (DATABASE_URL.removeprefix("sqlite:///") + ".replays"
                   if DATABASE_URL.startswith("sqlite:///") else "catan_replays")
store = ReplayStore(os.getenv("CATAN_REPLAY_DIR", default_replays),
                    DATABASE_URL.removeprefix("sqlite:///") if DATABASE_URL.startswith("sqlite:///") else None)
store.recover()
room_service = RoomService(use_database=True, database_url=DATABASE_URL)
bot_registry = BotRegistry(use_database=True, database_url=DATABASE_URL)
auth_service = AuthService(DATABASE_URL)
AUTH_REQUIRED = os.getenv("CATAN_AUTH_REQUIRED", "0").lower() not in ("0", "false", "no")
for _old_game in store.list_games():
    if _old_game.get("room_id") and _old_game["status"] not in ("queued", "running"):
        room_service.room_repository.update_room_status(_old_game["room_id"], "finished")
workers = ThreadPoolExecutor(max_workers=2, thread_name_prefix="catan-match")
mutation_lock = threading.RLock()
app = FastAPI(title="Catan replay studio")
frontend_origins = [origin.strip().rstrip("/") for origin in
                    os.getenv("CATAN_FRONTEND_ORIGINS", "").split(",") if origin.strip()]
if frontend_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=frontend_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization"],
    )
assets = Path(__file__).with_name("static")
app.mount("/static", StaticFiles(directory=assets, check_dir=False), name="static")


class BotUploadRequest(BaseModel):
    bot_name: str = Field(max_length=80)
    bot_version: str = Field(max_length=40)
    entrypoint: str = Field(default="main.py", max_length=120)
    description: str = Field(default="", max_length=2000)
    bot_code: str = Field(default="", max_length=200_000)
    use_sandbox: bool = True


class RoomJoinRequest(BaseModel):
    player_name: str = Field(min_length=1, max_length=80)


class RoomReadyRequest(RoomJoinRequest):
    ready: bool = True


class AttachBotRequest(RoomJoinRequest):
    bot_name: str
    bot_version: str = "v1"


class StartGameRequest(BaseModel):
    seed: int = Field(default=42, ge=0, le=2**31 - 1)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=40)
    email: str = Field(max_length=254)
    password: str = Field(min_length=10, max_length=256)


class LoginRequest(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)


@app.exception_handler(KeyError)
async def missing(request: Request, error: KeyError):
    return JSONResponse(status_code=404, content={"detail": "The requested item was not found."})


@app.exception_handler(ValueError)
async def invalid(request: Request, error: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(error)})


def now():
    return datetime.now(timezone.utc).isoformat()


def bearer(request: Request) -> str | None:
    value = request.headers.get("authorization", "")
    return value[7:].strip() if value.lower().startswith("bearer ") else None


def current_user(request: Request, required: bool = True):
    user = auth_service.user_for_token(bearer(request))
    if user is None and required and AUTH_REQUIRED:
        raise HTTPException(401, "Sign in to continue")
    return user


def owns_bot(package, user) -> bool:
    return user is None or package.owner_id in (None, user["user_id"])


def package_data(package):
    return {"bot_id": package.bot_id, "name": package.name, "version": package.version,
            "entrypoint": package.entrypoint, "description": package.description,
            "validated": package.validated, "validation_errors": package.validation_errors,
            "use_sandbox": package.use_sandbox, "owner_id": package.owner_id}


def require_bot(bot_id, user=None):
    package = bot_registry.get_bot(bot_id) if bot_id else None
    if package is None or not package.validated:
        raise ValueError("Select an existing, valid bot version")
    if not owns_bot(package, user):
        raise HTTPException(403, "That bot belongs to another account")
    return package


@app.post("/auth/register")
def register(request: RegisterRequest):
    user, token = auth_service.register(request.username, request.email, request.password)
    return {"user": user, "token": token}


@app.post("/auth/login")
def login(request: LoginRequest):
    user, token = auth_service.login(request.email, request.password)
    return {"user": user, "token": token}


@app.get("/auth/me")
def me(request: Request):
    user = current_user(request)
    if user is None:
        raise HTTPException(401, "Sign in to continue")
    return {"user": user}


@app.post("/auth/logout")
def logout(request: Request):
    token = bearer(request)
    if token:
        auth_service.logout(token)
    return {"ok": True}


@app.get("/account/stats")
def account_stats(request: Request):
    user = current_user(request)
    if user is None:
        raise HTTPException(401, "Sign in to continue")
    games = [game for game in store.list_games()
             if any(p.get("user_id") == user["user_id"] for p in game.get("participants", []))]
    completed = [game for game in games if game.get("status") == "completed"]
    wins = sum(any(p.get("user_id") == user["user_id"] and p.get("player_id") == game.get("winner")
                   for p in game.get("participants", [])) for game in completed)
    return {"games_played": len(completed), "wins": wins,
            "win_rate": round(100 * wins / len(completed), 1) if completed else 0,
            "bots": len(bot_registry.list_bots(user["user_id"])), "recent_matches": games[:10]}


def _run_match(metadata, packages):
    process=None
    try:
        metadata.update(status='running',started_at=now())
        store.save_metadata(metadata)
        job={'metadata':metadata,'replay_directory':str(store.directory.resolve()),
             'catalog_path':str(Path(store.catalog_path).resolve()),
             'packages':[{'code':p.bot_code if p.use_sandbox else None} if p else None for p in packages]}
        with tempfile.TemporaryDirectory(prefix='catan_match_') as directory:
            path=Path(directory)/'job.json';path.write_text(json.dumps(job),encoding='utf-8')
            process=subprocess.Popen([sys.executable,'-m','src.platform.match_worker',str(path)],
                cwd=Path(__file__).resolve().parents[2],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0,
                start_new_session=os.name!='nt')
            _,diagnostics=process.communicate(timeout=180)
            if process.returncode:
                logging.error('Match worker diagnostics: %s', diagnostics[-8192:].decode('utf-8',errors='replace'))
                raise RuntimeError('Match worker failed')
        metadata=store.metadata(metadata['game_id'])
        metadata['finished_at']=now()
        store.save_metadata(metadata)
    except Exception:
        if process is not None: terminate_tree(process)
        logging.exception('Match %s failed',metadata['game_id'])
        metadata.update(status='failed',finished_at=now(),reason='Match worker failed or exceeded its time limit.')
        store.save_metadata(metadata)
    finally:
        if metadata.get('room_id'):
            room_service.room_repository.update_room_status(metadata['room_id'],'finished')


def launch(seed, participants, packages, room_id=None, room_name=None):
    game_id = f"game-{uuid.uuid4().hex}"
    metadata = {"game_id": game_id, "seed": seed, "room_id": room_id, "room_name": room_name,
                "players": [p["name"] for p in participants], "participants": participants,
                "status": "queued", "created_at": now(), "winner": None, "replay_available": False}
    metadata["implementation_hashes"] = [hashlib.sha256(p.bot_code.encode()).hexdigest() for p in packages]
    store.save_metadata(metadata)
    workers.submit(_run_match, dict(metadata), packages)
    return {"game_id": game_id, "room_id": room_id}


@lru_cache(maxsize=1)
def sample_recording():
    """A deterministic real-engine replay that never enters the match catalog."""
    participants = [
        {"player_id": pid.value, "name": name, "bot_id": "sample-player-v1",
         "bot_name": "Sample Player", "bot_version": "v1", "color": color}
        for pid, name, color in zip(
            PlayerId.all_players(),
            ("Ada", "Grace", "Linus", "Margaret"),
            ("#d45b37", "#377da5", "#7759a6", "#d0a229"),
        )
    ]
    simulator = RecordingSimulator(seed=2026)
    simulator.register_players({pid: ExamplePlayer() for pid in PlayerId.all_players()})
    simulator.begin_recording()
    simulator.run()
    simulator.assert_invariants()
    metadata = {"game_id": "demo", "seed": 2026, "room_id": None,
                "room_name": "Sample match", "players": [p["name"] for p in participants],
                "participants": participants, "status": simulator.result["status"],
                "created_at": "2026-01-01T00:00:00+00:00", "winner": simulator.result["winner"],
                "replay_available": True, "engine_version": "2.0", "protocol_version": 1}
    return simulator.export_recording(metadata)


@app.get("/demo/replay")
def demo_replay():
    return sample_recording()


@app.get("/games")
def list_games():
    return {"games": store.list_games()}


@app.get("/games/{game_id}")
def get_game_metadata(game_id: str):
    return store.metadata(game_id)


@app.get("/game/{game_id}/replay")
def replay(game_id: str):
    recording = store.replay(game_id)
    if recording is None:
        raise HTTPException(409, "This run has no saved replay yet. Check its status on Matches.")
    return recording


@app.get("/game/{game_id}/state")
def state(game_id: str, player: str | None = None):
    if player is not None:
        raise HTTPException(403, "Private player views are not available in this local viewer.")
    return replay(game_id)["frames"][-1]["state"]


@app.get("/rooms")
def list_rooms():
    return {"rooms": room_service.list_rooms()}


@app.get("/rooms/{room_id}")
def get_room(room_id: str):
    room = room_service.get_room(room_id).to_dict()
    matches = [g for g in store.list_games() if g.get("room_id") == room_id]
    room["game"] = matches[0] if matches else None
    return {"room": room}


@app.post("/rooms")
def create_room(request: Request, room_name: str = "New room", created_by: str = "Player"):
    user = current_user(request)
    if user:
        created_by = user["username"]
    if not room_name.strip() or not created_by.strip() or max(len(room_name), len(created_by)) > 80:
        raise ValueError("Room and player names must contain 1–80 characters")
    with mutation_lock:
        return {"room": room_service.create_room(room_name.strip(), created_by.strip(),
                                                  user["user_id"] if user else None).to_dict()}


@app.post("/rooms/{room_id}/join")
def join_room(room_id: str, payload: RoomJoinRequest, request: Request):
    user = current_user(request)
    player_name = user["username"] if user else payload.player_name.strip()
    if not player_name:
        raise ValueError("Enter a player name")
    with mutation_lock:
        return {"room": room_service.join_room(room_id, player_name,
                                                user["user_id"] if user else None).to_dict()}


@app.post("/rooms/{room_id}/ready")
def set_room_ready(room_id: str, payload: RoomReadyRequest, request: Request):
    user = current_user(request)
    player_name = user["username"] if user else payload.player_name
    with mutation_lock:
        room = room_service.get_room(room_id)
        seat = next((s for s in room.seats if s.player_name == player_name), None)
        if seat is None:
            raise ValueError("Join this room first")
        if payload.ready:
            require_bot(seat.to_dict()["bot_runner"], user)
        return {"room": room_service.set_ready(room_id, player_name, payload.ready).to_dict()}


@app.post("/rooms/{room_id}/attach-bot")
def attach_bot(room_id: str, payload: AttachBotRequest, request: Request):
    user = current_user(request)
    player_name = user["username"] if user else payload.player_name
    with mutation_lock:
        requested_id = payload.bot_name if bot_registry.get_bot(payload.bot_name) else f"{payload.bot_name}-{payload.bot_version}"
        package = require_bot(requested_id, user)
        reference = BotRunner(bot_id=package.bot_id, name=package.name, version=package.version)
        return {"room": room_service.attach_bot(room_id, player_name, reference).to_dict()}


@app.post("/rooms/{room_id}/start-game")
def start_room_game(room_id: str, payload: StartGameRequest, request: Request):
    user = current_user(request)
    with mutation_lock:
        room = room_service.get_room(room_id)
        if user and not any(s.user_id == user["user_id"] for s in room.seats):
            raise HTTPException(403, "Join this room before starting its match")
        if not room.is_ready():
            raise ValueError("All four seats need a valid bot and must be ready")
        packages = [require_bot(s.to_dict()["bot_runner"]) for s in room.seats]
        participants = [{"player_id": pid.value, "name": s.player_name, "bot_id": b.bot_id,
                         "bot_name": b.name, "bot_version": b.version, "color": s.color,
                         "user_id": s.user_id}
                        for pid, s, b in zip(PlayerId.all_players(), room.seats, packages)]
        room_service.start_game(room_id)
        return launch(payload.seed, participants, packages, room_id, room.name)


@app.get("/bots")
def list_bots(request: Request):
    user = current_user(request)
    return {"bots": bot_registry.list_bots(user["user_id"] if user else None)}


@app.post("/bots/upload")
def upload_bot(payload: BotUploadRequest, request: Request):
    user = current_user(request)
    with mutation_lock:
        if not payload.use_sandbox or not payload.bot_code.strip():
            raise ValueError("Upload a Python Player implementation")
        existing = bot_registry.list_bots(user["user_id"] if user else None)
        if any(b["name"] == payload.bot_name.strip() and b["version"] == payload.bot_version.strip() for b in existing):
            raise HTTPException(409, "That version already exists. Choose a new version name.")
        name = payload.bot_name.strip()
        version = payload.bot_version.strip()
        if user:
            name_for_id = f"{user['user_id'][:13]}-{name}"
        else:
            name_for_id = name
        package = bot_registry.register(name_for_id, version,
                                       entrypoint=payload.entrypoint, description=payload.description,
                                       bot_code=payload.bot_code if payload.use_sandbox else None,
                                       use_sandbox=payload.use_sandbox, owner_id=user["user_id"] if user else None)
        package.name = name
        if user:
            with bot_registry.db_manager as session:
                from .database import Bot
                row = session.query(Bot).filter(Bot.id == package.bot_id).first()
                row.name = name
        if payload.bot_code and payload.use_sandbox:
            try:
                compile(payload.bot_code, "uploaded-bot.py", "exec")
                validate_player(payload.bot_code)
            except (SyntaxError, RuntimeError, TimeoutError, OSError, ValueError) as error:
                package.validated = False
                package.validation_errors = ["Player validation failed: define one Player subclass with choose_action and protocol version 1."]
                bot_registry.bot_repository.update_bot_validation(package.bot_id, False, package.validation_errors)
        return package_data(package)


@app.get("/bots/{bot_id}")
def get_bot(bot_id: str, request: Request):
    user = current_user(request)
    package = bot_registry.get_bot(bot_id)
    if package is None:
        raise KeyError(bot_id)
    if not owns_bot(package, user):
        raise HTTPException(403, "That bot belongs to another account")
    return package_data(package)


@app.get("/", response_class=HTMLResponse)
@app.get("/ui", response_class=HTMLResponse)
def index():
    return (assets / "index.html").read_text(encoding="utf-8")


@app.get("/health")
def health():
    """Container and reverse-proxy liveness endpoint."""
    return {"status": "ok"}


@app.get('/player-sdk.zip')
def player_sdk():
    root=Path(__file__).resolve().parents[2]
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for path in ('src/__init__.py','src/player/__init__.py','src/player/interface.py',
                     'src/player/example.py','examples/my_player.py','PLAYER_API.md'):
            archive.write(root/path,path)
    return Response(output.getvalue(),media_type='application/zip',
                    headers={'Content-Disposition':'attachment; filename="catan-player-sdk.zip"'})
