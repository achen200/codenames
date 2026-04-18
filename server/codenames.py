#!/usr/bin/env python3
"""Cooperative Codenames — 2-player CLI game."""

from enum import StrEnum
import json
import random
import sys
import uuid
import logging

from pathlib import Path
from typing import Optional
from dataclasses import dataclass
from common.logger import setup_logger
from common.constants import WordCategory


DATA_DIR = Path(__file__).parent
WORDS_FILE = DATA_DIR / "words.txt"
GAMES_DIR = DATA_DIR / "games"
CONFIG_FILE = DATA_DIR / "config.json"

# ANSI color codes
GREEN = "\033[92m"
RED = "\033[91m"
DIM = "\033[90m"
RESET = "\033[0m"
YELLOW = "\033[93m"

@dataclass
class GameConfig:
    board_size: int = 25
    guess_rounds: int = 5
    team_words: int = 9
    bystander_words: int = 7
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

@dataclass
class GameState:
    id: str
    status: GameStatus
    words: list[str]
    key: dict[str]
    revealed: list[str] # TODO: Update to dict
    clues: list[Clue]
    turn: Role
    rounds_remaining: int
    guesses_remaining: int
    roles_taken: list[Role]
    players: dict[Role, str]
    log: list[str]
    chat: list[ChatMessage]


setup_logger()
logger = logging.getLogger(__name__)

def load_words():
    return [w.strip() for w in WORDS_FILE.read_text().splitlines() if w.strip()]

def new_game(id: Optional[str] = None, config: Optional[GameConfig] = None):
    # TODO: Validate config values (i.e. team_words+bystander_words+assassin_words = boardsize). If it fails throw an error
    if not config:
        config = GameConfig()

    words = random.sample(load_words(), config.board_size)
    indices = list(range(config.board_size))
    random.shuffle(indices)

    key = {}
    for i in indices[:config.team_words]:
        key[i] = WordCategory.TEAM
    for i in indices[config.team_words:config.team_words + config.bystander_words]:
        key[i] = WordCategory.BYSTANDER
    for i in indices[config.team_words + config.bystander_words:config.team_words + config.bystander_words + config.assassin_words]:
        key[i] = WordCategory.ASSASSIN
    for i in indices[config.team_words + config.bystander_words + config.assassin_words:]:
        key[i] = WordCategory.BYSTANDER

    rounds = config.guess_rounds
    game_id = id or uuid.uuid4().hex[:8]
    state = GameState(id=game_id,
        status=GameStatus.ACTIVE,
        words=words,
        key={str(k): v for k, v in key.items()},
        revealed=[],
        clues=[],
        turn=Role.SPYMASTER,
        rounds_remaining=rounds,
        guesses_remaining=0,
        roles_taken=[],
        players={},
        log=[],
        chat=[]
    )
    save_game(state)
    return state


def save_game(state):
    GAMES_DIR.mkdir(exist_ok=True)
    path = GAMES_DIR / f"{state['id']}.json"
    path.write_text(json.dumps(state, indent=2))


class GameNotFound(Exception):
    pass


def load_game(game_id):
    path = GAMES_DIR / f"{game_id}.json"
    if not path.exists():
        raise GameNotFound(f"Game '{game_id}' not found.")
    return json.loads(path.read_text())


def delete_game(game_id):
    path = GAMES_DIR / f"{game_id}.json"
    if path.exists():
        path.unlink()


def team_words_remaining(state):
    return [i for i in range(BOARD_SIZE)
            if state["key"][str(i)] == "TEAM" and i not in state["revealed"]]


def colorize(text, role, revealed=False):
    if revealed:
        colors = {"TEAM": GREEN, "BYSTANDER": DIM, "ASSASSIN": RED}
    else:
        colors = {"TEAM": GREEN, "BYSTANDER": RESET, "ASSASSIN": RED}
    return f"{colors[role]}{text}{RESET}"


def render_board(state, show_key=False):
    print()
    for row in range(5):
        cells = []
        for col in range(5):
            idx = row * 5 + col
            word = state["words"][idx]
            role = state["key"][str(idx)]
            if idx in state["revealed"]:
                cells.append(colorize(f"[{word}]", role, revealed=True))
            elif show_key:
                cells.append(colorize(word, role))
            else:
                cells.append(word)
        print("  ".join(f"{c:<20}" for c in cells))
    print()


def print_status(state):
    remaining = team_words_remaining(state)
    print(f"Team words left: {len(remaining)} | Guess rounds left: {state['guesses_left']}")
    if state["clues"]:
        print(f"All clues: {', '.join(c['word']+':'+str(c['number']) for c in state['clues'])}")


def find_word(state, guess):
    guess = guess.strip().upper()
    for i, w in enumerate(state["words"]):
        if w.upper() == guess:
            return i
    return None


def end_guesser_turn(state):
    """End the guesser's turn, hand control back to spymaster."""
    state["turn"] = "spymaster"
    state["clue_guesses_left"] = 0
    state["guesses_left"] -= 1
    if state["guesses_left"] <= 0:
        state["status"] = "lost — out of guesses"


def cmd_new(args):
    custom_id = args[0] if args else None
    if custom_id and (GAMES_DIR / f"{custom_id}.json").exists():
        print(f"{RED}Game '{custom_id}' already exists.{RESET}")
        return
    state = new_game(custom_id)
    max_rounds = get_max_guess_rounds()
    print(f"New game created! ID: {state['id']}")
    print(f"Team words to find: {TEAM_COUNT} | Guess rounds: {max_rounds}")
    print(f"\nSpymaster: run  codenames.py spymaster {state['id']}")
    print(f"Guesser:   run  codenames.py guesser {state['id']}")


def cmd_spymaster(args):
    if not args:
        print("Usage: codenames.py spymaster <game_id> [clue word] [number]")
        return
    state = load_game(args[0])
    if state["status"] != "active":
        print(f"Game is over: {state['status']}")
        delete_game(args[0])
        return

    render_board(state, show_key=True)
    print_status(state)

    if len(args) == 3:
        # Trying to give a clue — check it's the spymaster's turn
        if state["turn"] != "spymaster":
            print(f"{YELLOW}It's the guesser's turn — they have {state['clue_guesses_left']} guess(es) left.{RESET}")
            return

        clue_word = args[1].upper()
        if ' ' in clue_word.strip():
            print(f"{RED}Clue must be a single word.{RESET}")
            return
        visible = [state["words"][i].upper() for i in range(BOARD_SIZE) if i not in state["revealed"]]
        if clue_word in visible:
            print(f"{RED}'{clue_word}' is on the board — pick a different clue.{RESET}")
            return
        for v in visible:
            if clue_word in v.split() or v in clue_word.split():
                print(f"{RED}'{clue_word}' overlaps with board word '{v}' — pick a different clue.{RESET}")
                return
        try:
            clue_num = int(args[2])
        except ValueError:
            print("Number must be an integer.")
            return
        if clue_num < 0:
            print("Number must be non-negative.")
            return

        state["clues"].append({"word": clue_word, "number": clue_num})
        state["turn"] = "guesser"
        state["clue_guesses_left"] = clue_num + 1  # standard: clue number + 1
        save_game(state)
        print(f"Clue given: {clue_word} : {clue_num}")
        print(f"Guesser may now make up to {state['clue_guesses_left']} guess(es).")
    else:
        if state["turn"] == "spymaster":
            print(f"{YELLOW}Your turn! Give a clue: codenames.py spymaster <game_id> <word> <number>{RESET}")
        else:
            print(f"Waiting for guesser ({state['clue_guesses_left']} guess(es) remaining).")
        if state["clues"]:
            print(f"Previous clues: {', '.join(c['word']+':'+str(c['number']) for c in state['clues'])}")


def cmd_guesser(args):
    if not args:
        print("Usage: codenames.py guesser <game_id> [word]")
        return
    state = load_game(args[0])
    if state["status"] != "active":
        print(f"Game is over: {state['status']}")
        render_board(state, show_key=True)
        delete_game(args[0])
        return

    render_board(state, show_key=False)
    print_status(state)

    # Show current clue if one exists
    if state["clues"] and state["turn"] == "guesser":
        last = state["clues"][-1]
        print(f"Current clue: {last['word']} : {last['number']}  |  Guesses this round: {state['clue_guesses_left']} left")

    # Check if it's the guesser's turn
    if state["turn"] != "guesser":
        print(f"{YELLOW}Waiting for the spymaster to give a clue.{RESET}")
        return

    if len(args) >= 2:
        guess = " ".join(args[1:])

        if guess.upper() == "PASS":
            end_guesser_turn(state)
            save_game(state)
            if state["status"] != "active":
                print("Passed. No guess rounds left. Game over.")
                render_board(state, show_key=True)
            else:
                print(f"Passed. Guess rounds left: {state['guesses_left']}")
            return

        idx = find_word(state, guess)
        if idx is None:
            print(f"'{guess}' is not on the board.")
            return
        if idx in state["revealed"]:
            print("That card is already revealed.")
            return

        word = state["words"][idx]
        role = state["key"][str(idx)]
        state["revealed"].append(idx)

        if role == "ASSASSIN":
            state["status"] = "lost — assassin"
            save_game(state)
            print(f"{RED}'{word}' is the ASSASSIN! Game over.{RESET}")
            render_board(state, show_key=True)
            return

        elif role == "TEAM":
            print(f"{GREEN}'{word}' is a TEAM word!{RESET}")
            if not team_words_remaining(state):
                state["status"] = "won"
                save_game(state)
                print(f"{GREEN}All team words found! You win!{RESET}")
                render_board(state, show_key=True)
                return
            state["clue_guesses_left"] -= 1
            if state["clue_guesses_left"] <= 0:
                # Used all guesses for this clue — back to spymaster
                end_guesser_turn(state)
                save_game(state)
                print("No more guesses for this clue. Spymaster's turn.")
                if state["status"] != "active":
                    print("No guess rounds left. Game over.")
                    render_board(state, show_key=True)
                return

        else:
            print(f"{DIM}'{word}' is a bystander. Turn ends.{RESET}")
            end_guesser_turn(state)
            save_game(state)
            if state["status"] != "active":
                print("No guess rounds left. Game over.")
                render_board(state, show_key=True)
                return

        save_game(state)
        render_board(state, show_key=False)
        remaining = team_words_remaining(state)
        print(f"Team words left: {len(remaining)} | Guess rounds left: {state['guesses_left']} | Guesses this round: {state['clue_guesses_left']}")
    else:
        print(f"\nTo guess: codenames.py guesser <game_id> <word>")
        print(f"To pass:  codenames.py guesser <game_id> pass")


def cmd_list(_args):
    if not GAMES_DIR.exists():
        print("No games yet.")
        return
    for f in sorted(GAMES_DIR.glob("*.json")):
        s = json.loads(f.read_text())
        remaining = len(team_words_remaining(s))
        print(f"  {s['id']}  status={s['status']}  team_left={remaining}  guesses_left={s['guesses_left']}")


def cmd_delete(args):
    if not args:
        print("Usage: codenames.py delete <game_id>")
        return
    game_id = args[0]
    path = GAMES_DIR / f"{game_id}.json"
    if not path.exists():
        raise GameNotFound(f"Game '{game_id}' not found.")
    delete_game(game_id)
    print(f"Game {game_id} deleted.")


COMMANDS = {
    "new": cmd_new,
    "spymaster": cmd_spymaster,
    "guesser": cmd_guesser,
    "list": cmd_list,
    "delete": cmd_delete,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print("Cooperative Codenames")
        print("Usage:")
        print("  codenames.py new [id]                     — Start a new game (optional custom ID)")
        print("  codenames.py spymaster <id>               — Spymaster view (see key)")
        print("  codenames.py spymaster <id> <word> <num>  — Give a clue")
        print("  codenames.py guesser <id>                 — Guesser view")
        print("  codenames.py guesser <id> <word>          — Guess a word")
        print("  codenames.py guesser <id> pass            — Pass (costs a guess round)")
        print("  codenames.py list                         — List all games")
        print("  codenames.py delete <id>                  — Delete a game")
        sys.exit(0)

    cmd = sys.argv[1]
    try:
        COMMANDS[cmd](sys.argv[2:])
    except GameNotFound as e:
        print(f"{RED}Error: {e}{RESET}")
        sys.exit(1)


if __name__ == "__main__":
    main()
