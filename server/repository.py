from dataclasses import dataclass
import logging
from pprint import pformat
import random
import uuid

from dataclass_wizard import JSONWizard

from common.constants import WordCategory
from common.logger import setup_logger
from common.types import GameNotFound
from server.game import Cell, Game, GameState, GameStatus, Role
from server.game import GameConfig
from typing import Optional

setup_logger()
logger = logging.getLogger(__name__)

@dataclass
class SaveData(JSONWizard):
    config: GameConfig
    state: GameState

class GameRepository:
    def __init__(self, games_dir: str, words_path: str):
        self.games_dir = games_dir
        self.words_path = words_path
        
    def new_game(self, game_id: Optional[str] = None, config: Optional[GameConfig] = None) -> Game:
        if not config:
            config = GameConfig()
        if not game_id:
            game_id = uuid.uuid4().hex[:8]

        logger.debug("Initializing new game [id=%s, config=%s]", game_id, pformat(config))

        game_words = self._load_words()
        board = _build_board(game_words, config)
        state = GameState(
            id=game_id,
            status=GameStatus.ACTIVE,
            board=board,
            clues=[],
            turn=Role.SPYMASTER,
            rounds_remaining=config.guess_rounds,
            guesses_remaining=0,
            players={},
            log=[],
            chat=[]
        )

        return Game(config=config, state=state)


    def load_game(self, game_id: str) -> Game:
        path = self._get_gamefile_path(game_id)
        if not path.exists():
            raise GameNotFound(f"Game '{game_id} not found'")

        data = SaveData.from_json(path.read_text())
        logger.debug("Loaded game: %s", pformat(data))
        return Game(data.config, data.state)

    def save_game(self, game: Game) -> None:
        self.games_dir.mkdir(exist_ok=True)
        path = self._get_gamefile_path(game.state.id)
        data = SaveData(game.config, game.state)
        path.write_text(data.to_json(indent=2))

    def delete_game(self, game_id: str) -> None:
        path = self._get_gamefile_path(game_id)
        path.unlink(missing_ok=True)

    def exists(self, game_id: str) -> bool:
        return self._get_gamefile_path(game_id).exists()

    def _load_words(self) -> list[str]:
        words = []
        for w in self.words_path.read_text().splitlines():
            if w.strip():
                words.append(w)
        return words
    
    def _get_gamefile_path(self, game_id: str) -> str:
        return self.games_dir / f"{game_id}.json"


def _build_board(words: list[str], config: GameConfig) -> list[Cell]:
    '''
    Helper function to generate a randomized board given constraints from config.
    '''
    total_words = config.team_words + config.assassin_words + config.bystander_words
    if total_words != config.board_size:
        raise ValueError("Total words does not match board size")

    categories = (
        [WordCategory.TEAM] * config.team_words +
        [WordCategory.ASSASSIN] * config.assassin_words +
        [WordCategory.BYSTANDER] * config.bystander_words
    )

    random.shuffle(categories)
    board = []
    for word, category in zip(words, categories):
        board.append(Cell(word, category))
    
    if len(board) != config.board_size:
        raise ValueError(f"Board size mismatch, expected{config.board_size} got {len(board)}")

    return board