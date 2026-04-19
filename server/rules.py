from dataclasses import dataclass
from typing import Optional

from common.constants import WordCategory
from server.game import Clue, Game, GameStatus, Role

@dataclass
class GuessResult:
    category: WordCategory
    revealed_index: int
    is_repeat: bool = False
    is_game_over: bool = False
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

    ##### Clue Rules/Enforcement #####
    @staticmethod
    def validate_clue(game: Game, clue: Clue) -> ClueValidationResult:
        text = clue.clue.strip()
        if " " in text:
            return ClueValidationResult(False, "Clue must be a single word")
        if clue.number < 0 or clue.number >= game.config.team_words:
            return ClueValidationResult(False, "Clue number cannot be less than 0 or greater than total team words")

        for cell in game.board():
            if cell.word.upper() == text.upper():
                return ClueValidationResult(False, "Clue is on the board")
        return ClueValidationResult(True)
    
    @staticmethod
    def get_initial_num_guesses(clue: Clue) -> int:
        return clue.number + 1
    
    ##### Guess Logic #####
    @staticmethod
    def guess_word(game: Game, ind: int) -> GuessResult:
        cell = game.cell(ind)

        # Check if guess was done already
        if cell.revealed:
            return GuessResult(
                category=cell.category,
                revealed_index=ind,
                is_repeat=True
            )

        category = cell.category

        # Guessed Assassin
        if category == WordCategory.ASSASSIN:
            return GuessResult(
                category=category,
                revealed_index=ind,
                is_game_over=True,
                new_status=GameStatus.LOST_ASSASSIN,
                end_turn=True
            )
        
        # Guessed Team
        if category == WordCategory.TEAM:
            if GameRules.remaining_words(game) == 1: # Because reveal is called after in the service layer
                return GuessResult(
                    category=category,
                    revealed_index=ind,
                    is_game_over=True,
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

    ##### Utility #####   
    @staticmethod
    def remaining_words(game: Game) -> int:
        '''
        Returns the number of team words on the board
        '''
        remaining = 0
        for cell in game.board():
            if cell.category == WordCategory.TEAM and not cell.revealed:
                remaining += 1
        return remaining