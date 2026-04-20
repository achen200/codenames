from dataclasses import dataclass
from typing import Optional

from common.constants import WordCategory
from server.game import Cell, Clue, GameStatus, Role

@dataclass
class GuessResult:
    category: WordCategory
    revealed_index: int
    new_status: Optional[GameStatus] = None
    end_turn: bool = False
    guesses_remaining_delta: int = 0

@dataclass
class ClueValidationResult:
    valid: bool
    reason: Optional[str] = None

class GameRules:
    ##### Turn Rules #####
    @staticmethod
    def should_end_turn(result: GuessResult, guesses_remaining: int) -> bool:
        if result.end_turn or guesses_remaining == 0:
            return True
        return False
    
    @staticmethod
    def next_player(current: Role) -> Role:
        return Role.SPYMASTER if current == Role.GUESSER else Role.GUESSER
    
    @staticmethod
    def remaining_words(board: list[Cell]) -> int:
        return sum(1 for c in board if c.category == WordCategory.TEAM and not c.revealed)

    ##### Clue Rules/Enforcement #####
    @staticmethod
    def validate_clue(board: list[Cell], clue: Clue, team_words: int) -> ClueValidationResult:
        text = clue.clue.strip()
        if " " in text:
            return ClueValidationResult(False, "Clue must be a single word")
        if not 0 <= clue.number <= team_words:
            return ClueValidationResult(False, "Clue number cannot be less than 0 or greater than total team words")
        if any(c.word.upper() == text.upper() for c in board):
                return ClueValidationResult(False, "Clue is on the board")
        return ClueValidationResult(True)

    @staticmethod
    def get_initial_num_guesses(clue: Clue) -> int:
        return clue.number + 1

    ##### Guess Logic #####
    @staticmethod
    def guess_word(board: list[Cell], ind: int) -> GuessResult:
        if ind >= len(board):
            raise IndexError(f"Index {ind} out of bounds")
        cell = board[ind]

        # Check if guess was done already
        if cell.revealed:
            return GuessResult(
                category=cell.category,
                revealed_index=ind
            )

        category = cell.category

        # Guessed Assassin
        if category == WordCategory.ASSASSIN:
            return GuessResult(
                category=category,
                revealed_index=ind,
                new_status=GameStatus.LOST_ASSASSIN,
                end_turn=True
            )

        # Guessed Team
        if category == WordCategory.TEAM:
            if GameRules.remaining_words(board) == 1: # Because reveal is called after in the service layer
                return GuessResult(
                    category=category,
                    revealed_index=ind,
                    new_status=GameStatus.WON,
                    end_turn=True
                )
            return GuessResult(
                category=category,
                revealed_index=ind,
                guesses_remaining_delta=-1,
            )

        # Guessed Bystander
        return GuessResult(
            category=category,
            revealed_index=ind,
            end_turn=True
        )