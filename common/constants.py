from enum import StrEnum
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent / "data"
WORDS_PATH = BASE_DIR / "words.txt"
GAMES_DIR = BASE_DIR / "games"

MAX_PLAYERS_PER_GAME = 2

class WordCategory(StrEnum):
    TEAM = "TEAM"
    BYSTANDER = "BYSTANDER"
    ASSASSIN = "ASSASSIN"

class ApiEndpoints:
    GAMES = "/games"
    GAME = "/games/{game_id}"

    JOIN = GAME + "/join"
    CLUE = GAME + "/clue"
    GUESS = GAME + "/guess"
    PASS = GAME + "/pass"
    CHAT = GAME + "/chat"

    @staticmethod
    def new_game():
        return ApiEndpoints.GAMES
    
    @staticmethod
    def game(game_id: str):
        return ApiEndpoints.GAME.format(game_id=game_id)

    @staticmethod
    def join(game_id: str):
        return ApiEndpoints.JOIN.format(game_id=game_id)
    
    @staticmethod
    def give_clue(game_id: str):
        return ApiEndpoints.CLUE.format(game_id=game_id)
    
    @staticmethod
    def guess(game_id: str):
        return ApiEndpoints.GUESS.format(game_id=game_id)
    
    @staticmethod
    def pass_turn(game_id: str):
        return ApiEndpoints.PASS.format(game_id=game_id)
    
    @staticmethod
    def chat(game_id: str):
        return ApiEndpoints.CHAT.format(game_id=game_id)
