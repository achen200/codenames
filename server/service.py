from dataclasses import dataclass
from typing import Optional

from common.constants import MAX_PLAYERS_PER_GAME, WordCategory
from common.types import ChatMessage, Clue, GameAlreadyOver, GameConfig, GameStatus, InvalidAction, Role, WrongTurn
from server.game import Game
from server.repository import GameRepository
from server.rules import GameRules, GuessResult

@dataclass
class JoinResponse:
    role: Role
    resumed: bool

@dataclass
class GuessResponse:
    category: WordCategory
    end_turn: bool
    status: GameStatus

class GameService:
    def __init__(self, repo: GameRepository):
        self.repo = repo

    def new_game(self, game_id: Optional[str] = None, config: Optional[GameConfig] = None) -> Game:
        if game_id and self.repo.exists(game_id):
            raise InvalidAction(f"Game '{game_id}' already exists")
        
        game = self.repo.new_game(game_id, config)
        self.repo.save_game(game)
        return game
    
    def get_game(self, game_id: str) -> Game:
        return self.repo.load_game(game_id)
        
    def join_game(self, game_id: str, name: str, role: Role) -> JoinResponse:
        game = self.get_game(game_id)
        self._assert_active(game)

        if not name:
            raise InvalidAction("Name is required")        

        players = game.players()
        existing_role = players.get(name)

        if existing_role is not None:
            return JoinResponse(existing_role, True)
        if len(players) >= MAX_PLAYERS_PER_GAME:
            raise InvalidAction("Game is full")
        if role in players.values():
            raise InvalidAction(f"{role} is already taken")
        
        game.add_player(name, role)
        game.log_action(f"[JOIN] {name} joined as {role}")
        self.repo.save_game(game)
        return JoinResponse(role, False)

    def delete_game(self, game_id: str) -> None:
        self.repo.delete_game(game_id)

    def give_clue(self, game_id: str, clue: Clue) -> None:
        game = self.get_game(game_id)
        self._assert_active(game)
        self._assert_turn(game, Role.SPYMASTER)
        
        result = GameRules.validate_clue(game.board(), clue, game.num_team_words())
        if not result.valid:
            raise InvalidAction(result.reason)
        
        guesses = GameRules.get_initial_num_guesses(clue)
        game.add_clue(clue)
        game.set_turn(Role.GUESSER)
        game.set_guesses(guesses)
        game.log_action(f"[CLUE] {clue.clue}: {clue.number}")
        self.repo.save_game(game)

    def make_guess(self, game_id: str, word: str) -> GuessResult:
        game = self.get_game(game_id)
        self._assert_active(game)
        self._assert_turn(game, Role.GUESSER)

        ind = game.get_word_ind(word)
        if ind is None:
            raise InvalidAction(f"'{word}' is not on the board or is already revealed")

        board = game.board()
        result = GameRules.guess_word(board, ind)
        game.reveal(ind)
        game.log_action(f"[GUESS] {word} → {result.category}")

        # Hanlde game over state
        if result.new_status is not None:
            game.set_status(result.new_status)
            game.set_rounds(0)
        else:
            game.set_guesses(game.num_guesses() + result.guesses_remaining_delta)
            if GameRules.should_end_turn(result, game.num_guesses()):
                game.set_guesses(0)
                game.set_turn(Role.SPYMASTER)
                game.set_rounds(game.rounds() - 1)

                if game.rounds() <= 0:
                    game.set_status(result.new_status)

        self.repo.save_game(game)
        return GuessResponse(result.category, result.end_turn, game.status())

    def pass_turn(self, game_id: str) -> GameStatus:
        game = self.get_game(game_id)
        self._assert_active(game)
        self._assert_turn(game, Role.GUESSER)

        game.set_rounds(game.rounds() - 1)
        game.set_guesses(0)
        game.set_turn(Role.SPYMASTER)
        game.log_action(f"[PASS] {game.rounds()} rounds remaining")

        if game.rounds() <= 0:
            game.set_status(GameStatus.LOST_GUESSES)

        self.repo.save_game(game)
        return game.status()

    def send_chat(self, game_id: str, name: str, msg: str) -> None:
        game = self.get_game(game_id)
        self._assert_active(game)

        game.add_chat(ChatMessage(name, msg))
        self.repo.save_game(game)

    ### Helpers
    def _assert_turn(self, game: Game, role: Role) -> None:
        if game.turn() != role:
            raise WrongTurn(f"It is not {role}'s turn")
    
    def _assert_active(self, game: Game) -> None:
        if game.status() != GameStatus.ACTIVE:
            raise GameAlreadyOver("Game no longer active")