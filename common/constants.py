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