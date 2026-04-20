from dataclasses import dataclass
from enum import StrEnum


@dataclass
class GameConfig:
    board_size: int = 25
    guess_rounds: int = 5
    team_words: int = 9
    bystander_words: int = 15
    assassin_words: int = 1

@dataclass
class ChatMessage:
    name: str
    msg: str

class GameStatus(StrEnum):
    ACTIVE = "active"
    LOST_GUESSES = "lost — out of guesses"
    LOST_ASSASSIN = "lost — assassin"
    WON = "won"

class Role(StrEnum):
    SPYMASTER = "spymaster"
    GUESSER = "guesser"

@dataclass
class Clue:
    clue: str
    number: int

class GameNotFound(Exception):
    pass

class GameServiceError(Exception):
    pass

class InvalidAction(GameServiceError):
    pass

class WrongTurn(InvalidAction):
    pass

class GameAlreadyOver(InvalidAction):
    pass