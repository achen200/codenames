import math
from common.types import GameStatus, Role
from common.constants import WordCategory

# ANSI color codes
GREEN = "\033[92m"
RED = "\033[91m"
DIM = "\033[90m"
RESET = "\033[0m"
YELLOW = "\033[93m"
BOLD = "\033[1m"

def _colorize(text: str, category: WordCategory, revealed: bool, show_key: bool) -> str:
    if revealed:
        colors = {
            WordCategory.TEAM: GREEN,
            WordCategory.BYSTANDER: DIM,
            WordCategory.ASSASSIN: RED,
        }
        return f"{colors[category]}{text}{RESET}"
    if show_key:
        colors = {
            WordCategory.TEAM: GREEN,
            WordCategory.BYSTANDER: RESET,
            WordCategory.ASSASSIN: RED,
        }
        return f"{colors[category]}{text}{RESET}"
    return text


def render_board(board: list[dict], role: Role) -> None:
    show_key = role == Role.SPYMASTER
    size = len(board)
    cols = math.isqrt(size)

    cell_width = max(len(cell["word"]) for cell in board) + 2

    print()
    for row in range(cols):
        cells = []
        for col in range(cols):
            idx = row * cols + col
            cell = board[idx]
            word = cell["word"]
            category = WordCategory(cell["category"])
            revealed = cell["revealed"]
            colored = _colorize(word, category, revealed, show_key)
            cells.append(f"{colored:<{cell_width}}")
        print("  ".join(cells))
    print()


def print_status(game: dict, role: Role) -> None:
    rounds = game["rounds_remaining"]
    guesses = game["guesses_remaining"]
    status = game["status"]

    if status != GameStatus.ACTIVE:
        _print_game_over(status)
        return

    remaining = sum(1 for c in game["board"] if c["category"] == WordCategory.TEAM and not c["revealed"])
    print(f"Team words left: {remaining} | Rounds left: {rounds}", end="")
    if role == Role.GUESSER and guesses > 0:
        print(f" | Guesses this round: {guesses}", end="")
    print()

    if game["clues"]:
        last = game["clues"][-1]
        print(f"Current clue: {BOLD}{last['clue']} : {last['number']}{RESET}")


def _print_game_over(status: GameStatus) -> None:
    messages = {
        GameStatus.WON: f"{GREEN}You won!{RESET}",
        GameStatus.LOST_ASSASSIN: f"{RED}You hit the assassin! Game over.{RESET}",
        GameStatus.LOST_GUESSES: f"{RED}Out of rounds! Game over.{RESET}",
    }
    print(messages.get(status, "Game over."))


def print_clues(game: dict) -> None:
    if game["clues"]:
        formatted = ", ".join(f"{c['clue']}:{c['number']}" for c in game["clues"])
        print(f"All clues: {formatted}")


def print_error(msg: str) -> None:
    print(f"{RED}Error: {msg}{RESET}")


def print_success(msg: str) -> None:
    print(f"{GREEN}{msg}{RESET}")


def print_warning(msg: str) -> None:
    print(f"{YELLOW}{msg}{RESET}")