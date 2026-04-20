#!/usr/bin/env python3
"""Cooperative Codenames — 2-player CLI game."""
from __future__ import annotations
import json
import sys

from dataclasses import dataclass
from typing import Optional
from common.constants import WordCategory
from dataclass_wizard import JSONWizard

from common.types import ChatMessage, Clue, GameConfig, GameStatus, Role

@dataclass
class Cell:
    word: str
    category: WordCategory
    revealed: bool = False

@dataclass
class GameState(JSONWizard):
    id: str
    status: GameStatus
    board: list[Cell]

    clues: list[Clue]
    turn: Role
    rounds_remaining: int
    guesses_remaining: int
    players: dict[str, Role]
    log: list[str]
    chat: list[ChatMessage]

class Game:
    def __init__(self, config: GameConfig, state: GameState):
        self.config = config
        self.state = state

    ### Read only functions ###
    def board(self) -> list[Cell]:
        '''
        Gets current board
        '''
        return self.state.board

    def cell(self, ind: int) -> Cell:
        '''
        Gets specified cell in board
        '''
        board = self.board()
        if ind >= len(board):
            raise IndexError(f"Index {ind} is out of bounds for board length {len(board)}")
        return board[ind] 
    
    def players(self) -> dict[str, Role]:
        return self.state.players
    
    def status(self) -> GameStatus:
        return self.state.status
    
    def turn(self) -> Role:
        return self.state.turn
    
    def rounds(self) -> int:
        return self.state.rounds_remaining
    
    def num_guesses(self) -> int:
        return self.state.guesses_remaining

    def num_team_words(self) -> int:
        return self.config.team_words
    
    def get_word_ind(self, word: str) -> Optional[int]:
        word = word.strip().upper()
        for i, cell in enumerate(self.board()):
            if word == cell.word.upper() and not cell.revealed:
                return i

    ### Mutating Functions ###
    def add_player(self, name: str, role: Role):
        self.state.players[name] = role

    def reveal(self, ind: int) -> None:
        cell = self.cell(ind)
        if cell.revealed:
            raise ValueError(f"Cell: {ind} word: {cell.word} already revealed")
        cell.revealed = True

    def add_clue(self, clue: Clue) -> None:
        self.state.clues.append(clue)
    
    def set_status(self, status: GameStatus) -> None:
        self.state.status = status
    
    def set_turn(self, role: Role) -> None:
        self.state.turn = role

    def set_guesses(self, guesses: int) -> None:
        self.state.guesses_remaining = guesses
    
    def set_rounds(self, rounds: int) -> None:
        self.state.rounds_remaining = rounds

    ### Chat/Game History ###
    def add_chat(self, msg: ChatMessage) -> None:
        self.state.chat.append(msg)

    def log_action(self, message: str) -> None:
        self.state.log.append(message)