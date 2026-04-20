import os
from typing import Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from common.constants import GAMES_DIR, WORDS_PATH
from common.types import Clue, GameAlreadyOver, GameNotFound, InvalidAction, Role, WrongTurn
from server.repository import GameRepository
from server.service import GameService


app = FastAPI()
security = HTTPBearer(auto_error=False)

##### Dependencies #####
def get_service() -> GameService:
    repo = GameRepository(GAMES_DIR, WORDS_PATH)
    return GameService(repo)

def verify_token(creds: HTTPAuthorizationCredentials = Depends(security)) -> None:
    token = os.getenv("CODENAMES_TOKEN", "")
    if not token:
        return
    if creds is None or creds.credentials != token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
##### Request Bodies #####
class NewGameRequest(BaseModel):
    game_id: Optional[str] = None

class JoinRequest(BaseModel):
    name: str
    role: Role

class ClueRequest(BaseModel):
    word: str
    number: int

class GuessRequest(BaseModel):
    word: str

class ChatRequest(BaseModel):
    name: str
    msg: str

##### Errors #####
def handle_service_error(e: Exception) -> None:
    if isinstance(e, GameNotFound):
        raise HTTPException(status_code=404, detail=str(e))
    if isinstance(e, (WrongTurn, GameAlreadyOver, InvalidAction)):
        raise HTTPException(status_code=400, detail=str(e))
    raise e

##### Router #####
router = APIRouter(dependencies=[Depends(verify_token)])

@router.post("/games", status_code=201)
def new_game(body: NewGameRequest, service: GameService = Depends(get_service)):
    try:
        game = service.new_game(body.game_id)
        return {"id": game.state.id}
    except Exception as e:
        handle_service_error(e)

@router.get("/games/{game_id}")
def get_game(game_id: str, service: GameService = Depends(get_service)):
    try:
        return service.get_game(game_id)
    except Exception as e:
        handle_service_error(e)

@router.delete("/games/{game_id}")
def delete_game(game_id: str, service: GameService = Depends(get_service)):
    try:
        service.delete_game(game_id)
        return {"ok": True}
    except Exception as e:
        handle_service_error(e)

@router.post("/games/{game_id}/join")
def join_game(game_id: str, body: JoinRequest, service: GameService = Depends(get_service)):
    try:
        return service.join_game(game_id, body.name, body.role)
    except Exception as e:
        handle_service_error(e)

@router.post("/games/{game_id}/clue")
def give_clue(game_id: str, body: ClueRequest, service: GameService = Depends(get_service)):
    try:
        service.give_clue(game_id, Clue(body.word, body.number))
        return {"ok": True}
    except Exception as e:
        handle_service_error(e)

@router.post("/games/{game_id}/guess")
def make_guess(game_id: str, body: GuessRequest, service: GameService = Depends(get_service)):
    try:
        return service.make_guess(game_id, body.word)
    except Exception as e:
        handle_service_error(e)

@router.post("/games/{game_id}/pass")
def pass_turn(game_id: str, service: GameService = Depends(get_service)):
    try:
        return service.pass_turn(game_id)
    except Exception as e:
        handle_service_error(e)

@router.post("/games/{game_id}/chat")
def send_chat(game_id: str, body: ChatRequest, service: GameService = Depends(get_service)):
    try:
        service.send_chat(game_id, body.name, body.msg)
        return {"ok": True}
    except Exception as e:
        handle_service_error(e)

app.include_router(router)