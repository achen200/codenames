#!/usr/bin/env python3
"""Codenames TUI client."""

import curses
import math
import time
from enum import Enum, auto
from typing import Optional

import httpx

from common.constants import WordCategory
from common.types import Role
from client.config import CLIConfig, load_config, save_config

##### Constants #####
REFRESH_INTERVAL = 3


##### Screens #####
class Screen(Enum):
    MENU = auto()
    CREATE = auto()
    JOIN = auto()
    SETTINGS = auto()
    GAME = auto()


##### API #####
class CodenamesClient:
    def __init__(self, config: CLIConfig):
        self.config = config
        self._make_client()

    def _make_client(self):
        self.client = httpx.Client(
            base_url=f"http://{self.config.host}",
            headers={"Authorization": f"Bearer {self.config.token}"} if self.config.token else {}
        )

    def update_config(self, config: CLIConfig):
        self.config = config
        self.client.close()
        self._make_client()

    def get_game(self) -> Optional[dict]:
        try:
            r = self.client.get(f"/games/{self.config.game_id}")
            r.raise_for_status()
            data = r.json()
            return data["state"]
        except Exception as e:
            print(f"get_game error: {e}")
            return None

    def create_game(self, game_id: Optional[str]) -> tuple[bool, str]:
        try:
            r = self.client.post("/games", json={"game_id": game_id or None})
            r.raise_for_status()
            return True, r.json()["id"]
        except httpx.HTTPStatusError as e:
            return False, self._parse_error(e)
        except Exception as e:
            return False, str(e)

    def join_game(self, game_id: str, name: str, role: Role) -> tuple[bool, str]:
        try:
            r = self.client.post(f"/games/{game_id}/join", json={
                "name": name,
                "role": role.value,
            })
            r.raise_for_status()
            return True, ""
        except httpx.HTTPStatusError as e:
            return False, self._parse_error(e)
        except Exception as e:
            return False, str(e)

    def guess(self, word: str) -> tuple[bool, str]:
        try:
            r = self.client.post(f"/games/{self.config.game_id}/guess", json={"word": word})
            r.raise_for_status()
            return True, ""
        except httpx.HTTPStatusError as e:
            return False, self._parse_error(e)

    def clue(self, word: str, number: int) -> tuple[bool, str]:
        try:
            r = self.client.post(f"/games/{self.config.game_id}/clue", json={
                "word": word,
                "number": number,
            })
            r.raise_for_status()
            return True, ""
        except httpx.HTTPStatusError as e:
            return False, self._parse_error(e)

    def pass_turn(self) -> tuple[bool, str]:
        try:
            r = self.client.post(f"/games/{self.config.game_id}/pass")
            r.raise_for_status()
            return True, ""
        except httpx.HTTPStatusError as e:
            return False, self._parse_error(e)

    def chat(self, msg: str) -> tuple[bool, str]:
        try:
            r = self.client.post(f"/games/{self.config.game_id}/chat", json={
                "name": self.config.name,
                "msg": msg,
            })
            r.raise_for_status()
            return True, ""
        except httpx.HTTPStatusError as e:
            return False, self._parse_error(e)

    def close(self):
        self.client.close()
    
    def _parse_error(self, e: httpx.HTTPStatusError) -> str:
        try:
            return e.response.json().get("detail", "Error")
        except Exception:
            return f"HTTP {e.response.status_code}"


##### TUI #####
class TUI:
    # Color pairs
    C_HEADER = 1
    C_TEAM = 2
    C_ASSASSIN = 3
    C_BYSTANDER = 4
    C_SELECTED = 5
    C_REVEALED_TEAM = 6
    C_REVEALED_ASSASSIN = 7
    C_ERROR = 8
    C_DIM = 9
    C_HIGHLIGHT = 10

    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.config = self._load_config_safe()
        self.api = CodenamesClient(self.config)

        # Screen state
        self.screen = Screen.MENU
        self.error: Optional[str] = None

        # Menu state
        self.menu_items = ["Create game", "Join game", "Settings", "Quit"]
        self.menu_cursor = 0

        # Create screen state
        self.create_game_id: str = ""

        # Join screen state
        self.join_game_id: str = ""
        self.join_name: str = ""
        self.join_role: Role = Role.GUESSER
        self.join_field: int = 0  # 0=game_id, 1=name, 2=role

        # Settings screen state
        self.settings_host: str = self.config.host or ""
        self.settings_token: str = self.config.token or ""
        self.settings_field: int = 0  # 0=host, 1=token

        # Game state
        self.game: Optional[dict] = None
        self.is_typing: bool = False
        self.input_buf: str = ""
        self.cursor_row: int = 0
        self.cursor_col: int = 0
        self.board_cols: int = 0
        self.log_scroll: int = 0
        self.chat_scroll: int = 0
        self.last_refresh: float = 0

        self._init_curses()
        self._init_colors()

    def _load_config_safe(self) -> CLIConfig:
        try:
            return load_config()
        except FileNotFoundError:
            return CLIConfig(host="", token="")

    def _init_curses(self):
        curses.curs_set(1)
        self.stdscr.nodelay(True)
        self.stdscr.keypad(True)

    def _init_colors(self):
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(self.C_HEADER, curses.COLOR_CYAN, -1)
        curses.init_pair(self.C_TEAM, curses.COLOR_GREEN, -1)
        curses.init_pair(self.C_ASSASSIN, curses.COLOR_RED, -1)
        curses.init_pair(self.C_BYSTANDER, curses.COLOR_WHITE, -1)
        curses.init_pair(self.C_SELECTED, curses.COLOR_BLACK, curses.COLOR_CYAN)
        curses.init_pair(self.C_REVEALED_TEAM, curses.COLOR_BLACK, curses.COLOR_GREEN)
        curses.init_pair(self.C_REVEALED_ASSASSIN, curses.COLOR_BLACK, curses.COLOR_RED)
        curses.init_pair(self.C_ERROR, curses.COLOR_RED, -1)
        curses.init_pair(self.C_DIM, curses.COLOR_WHITE, -1)
        curses.init_pair(self.C_HIGHLIGHT, curses.COLOR_CYAN, -1)

    def run(self):
        try:
            while True:
                rows, cols = self.stdscr.getmaxyx()
                self.stdscr.erase()

                if self.screen == Screen.MENU:
                    self._render_menu(rows, cols)
                elif self.screen == Screen.CREATE:
                    self._render_create(rows, cols)
                elif self.screen == Screen.JOIN:
                    self._render_join(rows, cols)
                elif self.screen == Screen.SETTINGS:
                    self._render_settings(rows, cols)
                elif self.screen == Screen.GAME:
                    self._render_game(rows, cols)

                self.stdscr.refresh()

                key = self.stdscr.getch()
                if key == -1:
                    # No input — check refresh
                    if self.screen == Screen.GAME and not self.is_typing:
                        now = time.time()
                        if now - self.last_refresh >= REFRESH_INTERVAL:
                            self.game = self.api.get_game()
                            self.last_refresh = now
                    time.sleep(0.05)
                    continue

                should_continue = self._handle_key(key)
                if not should_continue:
                    break
        finally:
            self.api.close()

    ##### Rendering #####

    def _addstr(self, row: int, col: int, text: str, attr=curses.A_NORMAL):
        rows, cols = self.stdscr.getmaxyx()
        if row < 0 or row >= rows or col < 0:
            return
        text = text[:cols - col - 1]
        try:
            self.stdscr.addstr(row, col, text, attr)
        except curses.error:
            pass

    def _render_header(self, row: int, cols: int, title: str = "") -> int:
        header = f"[ codenames ] {title}"
        self._addstr(row, 0, header, curses.color_pair(self.C_HEADER) | curses.A_BOLD)
        return row + 1

    def _render_divider(self, row: int, cols: int) -> int:
        self._addstr(row, 0, "─" * (cols - 1))
        return row + 1

    def _render_footer(self, rows: int, cols: int, hints: str):
        self._render_divider(rows - 2, cols)
        self._addstr(rows - 1, 0, hints, curses.A_DIM)

    def _render_error(self, row: int):
        if self.error:
            self._addstr(row, 0, f"  ! {self.error}", curses.color_pair(self.C_ERROR))

    def _render_menu(self, rows: int, cols: int):
        row = 0
        row = self._render_header(row, cols)
        row = self._render_divider(row, cols)

        row += 1
        for i, item in enumerate(self.menu_items):
            if i == self.menu_cursor:
                self._addstr(row, 2, f"> {item}", curses.color_pair(self.C_HIGHLIGHT) | curses.A_BOLD)
            else:
                self._addstr(row, 4, item)
            row += 1

        row += 1
        host = self.config.host or "not configured"
        self._addstr(row, 2, f"connected to: {host}", curses.A_DIM)

        self._render_error(rows - 3)
        self._render_footer(rows, cols, "arrows=navigate  enter=select  q=quit")

    def _render_create(self, rows: int, cols: int):
        row = 0
        row = self._render_header(row, cols, "create game")
        row = self._render_divider(row, cols)

        row += 1
        self._addstr(row, 2, "Game ID (optional):", curses.A_BOLD)
        self._addstr(row, 22, self.create_game_id + ("_" if True else ""))
        row += 2

        self._render_error(rows - 3)
        self._render_footer(rows, cols, "enter=create  q=back")

    def _render_join(self, rows: int, cols: int):
        row = 0
        row = self._render_header(row, cols, "join game")
        row = self._render_divider(row, cols)

        row += 1
        fields = [
            ("Game ID:", self.join_game_id),
            ("Name:   ", self.join_name),
        ]
        for i, (label, value) in enumerate(fields):
            attr = curses.A_BOLD if self.join_field == i else curses.A_NORMAL
            self._addstr(row, 2, label, attr)
            cursor = "_" if self.join_field == i else ""
            self._addstr(row, 12, value + cursor)
            row += 1

        # Role toggle
        role_attr = curses.A_BOLD if self.join_field == 2 else curses.A_NORMAL
        self._addstr(row, 2, "Role:   ", role_attr)
        for i, role in enumerate(Role):
            if role == self.join_role:
                self._addstr(row, 12 + i * 12, f"[{role.value}]", curses.color_pair(self.C_HIGHLIGHT) | curses.A_BOLD)
            else:
                self._addstr(row, 12 + i * 12, f" {role.value} ", curses.A_DIM)

        self._render_error(rows - 3)
        self._render_footer(rows, cols, "tab=next field  arrows=toggle role  enter=join  q=back")

    def _render_settings(self, rows: int, cols: int):
        row = 0
        row = self._render_header(row, cols, "settings")
        row = self._render_divider(row, cols)

        row += 1
        fields = [
            ("Host: ", self.settings_host),
            ("Token:", self.settings_token),
        ]
        for i, (label, value) in enumerate(fields):
            attr = curses.A_BOLD if self.settings_field == i else curses.A_NORMAL
            self._addstr(row, 2, label, attr)
            cursor = "_" if self.settings_field == i else ""
            self._addstr(row, 10, value + cursor)
            row += 1

        self._render_error(rows - 3)
        self._render_footer(rows, cols, "tab=next field  enter=save  q=back")

    def _render_game(self, rows: int, cols: int):
        row = 0
        row = self._render_header(row, cols, self._game_header())
        row = self._render_divider(row, cols)
        row = self._render_board(row, cols)
        row = self._render_divider(row, cols)
        row = self._render_panels(row, cols, rows)
        self._render_divider(rows - 3, cols)
        self._render_hints(rows - 2, cols)
        self._render_input(rows - 1, cols)

    def _game_header(self) -> str:
        if not self.game:
            return "connecting..."
        rounds = self.game.get("rounds_remaining", "?")
        guesses = self.game.get("guesses_remaining", "?")
        status = self.game.get("status", "?")
        return (
            f"game: {self.config.game_id} | "
            f"role: {self.config.role} | "
            f"rounds: {rounds} | "
            f"guesses: {guesses} | "
            f"status: {status}"
        )

    def _render_board(self, row: int, cols: int) -> int:
        if not self.game:
            self._addstr(row, 0, "  waiting for game state...")
            return row + 1

        board = self.game["board"]
        size = len(board)
        board_cols = math.isqrt(size)
        self.board_cols = board_cols
        cell_width = max(len(c["word"]) for c in board) + 2

        for r in range(board_cols):
            col_offset = 2
            for c in range(board_cols):
                idx = r * board_cols + c
                cell = board[idx]
                word = cell["word"]
                category = WordCategory(cell["category"])
                revealed = cell["revealed"]
                is_selected = (
                    self.config.role == Role.GUESSER and
                    self.cursor_row == r and
                    self.cursor_col == c
                )
                attr = self._cell_attr(category, revealed, is_selected)
                self._addstr(row + r, col_offset, word.center(cell_width), attr)
                col_offset += cell_width + 2

        return row + board_cols

    def _cell_attr(self, category: WordCategory, revealed: bool, is_selected: bool):
        if is_selected:
            return curses.color_pair(self.C_SELECTED) | curses.A_BOLD
        if revealed:
            if category == WordCategory.TEAM:
                return curses.color_pair(self.C_REVEALED_TEAM) | curses.A_DIM
            if category == WordCategory.ASSASSIN:
                return curses.color_pair(self.C_REVEALED_ASSASSIN) | curses.A_DIM
            return curses.A_DIM
        if self.config.role == Role.SPYMASTER:
            if category == WordCategory.TEAM:
                return curses.color_pair(self.C_TEAM)
            if category == WordCategory.ASSASSIN:
                return curses.color_pair(self.C_ASSASSIN)
            return curses.color_pair(self.C_BYSTANDER)
        return curses.A_NORMAL

    def _render_panels(self, row: int, cols: int, total_rows: int) -> int:
        panel_height = total_rows - row - 4
        if panel_height <= 0:
            return row

        mid = cols // 2
        self._addstr(row, 0, "[log]", curses.A_BOLD)
        self._addstr(row, mid, "[chat]", curses.A_BOLD)

        log = self.game.get("log", []) if self.game else []
        chat = self.game.get("chat", []) if self.game else []

        log_visible = panel_height - 1
        chat_visible = panel_height - 1

        log_start = max(0, len(log) - log_visible - self.log_scroll)
        chat_start = max(0, len(chat) - chat_visible - self.chat_scroll)

        for i in range(log_visible):
            log_idx = log_start + i
            if log_idx < len(log):
                self._addstr(row + 1 + i, 0, log[log_idx][:mid - 2])
            chat_idx = chat_start + i
            if chat_idx < len(chat):
                entry = chat[chat_idx]
                msg = f"{entry['name']}: {entry['msg']}"
                self._addstr(row + 1 + i, mid, msg[:cols - mid - 2])

        return row + panel_height

    def _render_hints(self, row: int, cols: int):
        if self.config.role == Role.GUESSER:
            hints = "arrows=navigate  enter=guess  /pass  /clue spymaster-only  []=log  -==chat  q=quit"
        else:
            hints = "/clue <word> <n>  []=scroll log  -==scroll chat  q=quit"
        self._addstr(row, 0, hints[:cols - 1], curses.A_DIM)

    def _render_input(self, row: int, cols: int):
        if self.error:
            self._addstr(row, 0, f"> {self.error}", curses.color_pair(self.C_ERROR))
        else:
            prompt = f"> {self.input_buf}"
            self._addstr(row, 0, prompt[:cols - 1])
            try:
                self.stdscr.move(row, min(len(prompt), cols - 2))
            except curses.error:
                pass

    ##### Input Handling #####

    def _handle_key(self, key: int) -> bool:
        if self.screen == Screen.MENU:
            return self._handle_menu(key)
        elif self.screen == Screen.CREATE:
            return self._handle_create(key)
        elif self.screen == Screen.JOIN:
            return self._handle_join(key)
        elif self.screen == Screen.SETTINGS:
            return self._handle_settings(key)
        elif self.screen == Screen.GAME:
            return self._handle_game(key)
        return True

    def _handle_menu(self, key: int) -> bool:
        if key == curses.KEY_UP:
            self.menu_cursor = max(0, self.menu_cursor - 1)
        elif key == curses.KEY_DOWN:
            self.menu_cursor = min(len(self.menu_items) - 1, self.menu_cursor + 1)
        elif key in (ord('\n'), curses.KEY_ENTER):
            selected = self.menu_items[self.menu_cursor]
            if selected == "Quit":
                return False
            elif selected == "Create game":
                self.create_game_id = ""
                self.error = None
                self.screen = Screen.CREATE
            elif selected == "Join game":
                self.join_game_id = ""
                self.join_name = ""
                self.join_role = Role.GUESSER
                self.join_field = 0
                self.error = None
                self.screen = Screen.JOIN
            elif selected == "Settings":
                self.settings_host = self.config.host or ""
                self.settings_token = self.config.token or ""
                self.settings_field = 0
                self.error = None
                self.screen = Screen.SETTINGS
        elif key == ord('q'):
            return False
        return True

    def _handle_create(self, key: int) -> bool:
        if key == ord('q'):
            self.screen = Screen.MENU
            self.error = None
        elif key in (curses.KEY_BACKSPACE, 127, 8):
            self.create_game_id = self.create_game_id[:-1]
        elif key in (ord('\n'), curses.KEY_ENTER):
            ok, result = self.api.create_game(self.create_game_id or None)
            if ok:
                self.config.game_id = result
                save_config(self.config)
                # Go to join screen with game_id pre-populated
                self.join_game_id = result
                self.join_name = self.config.name or ""
                self.join_role = self.config.role or Role.GUESSER
                self.join_field = 1  # skip to name since game_id is set
                self.error = None
                self.screen = Screen.JOIN
            else:
                self.error = result
        elif 32 <= key <= 126:
            self.create_game_id += chr(key)
        return True

    def _handle_join(self, key: int) -> bool:
        if key == ord('q'):
            self.screen = Screen.MENU
            self.error = None
        elif key == ord('\t'):
            self.join_field = (self.join_field + 1) % 3
        elif key in (curses.KEY_BACKSPACE, 127, 8):
            if self.join_field == 0:
                self.join_game_id = self.join_game_id[:-1]
            elif self.join_field == 1:
                self.join_name = self.join_name[:-1]
        elif key in (curses.KEY_LEFT, curses.KEY_RIGHT) and self.join_field == 2:
            roles = list(Role)
            idx = roles.index(self.join_role)
            self.join_role = roles[(idx + 1) % len(roles)]
        elif key in (ord('\n'), curses.KEY_ENTER):
            if not self.join_game_id:
                self.error = "Game ID is required"
            elif not self.join_name:
                self.error = "Name is required"
            else:
                ok, err = self.api.join_game(self.join_game_id, self.join_name, self.join_role)
                if ok:
                    self.config.game_id = self.join_game_id
                    self.config.name = self.join_name
                    self.config.role = self.join_role
                    save_config(self.config)
                    self.api.update_config(self.config)
                    self.game = self.api.get_game()
                    self.last_refresh = time.time()
                    self.screen = Screen.GAME
                    self.error = None
                else:
                    self.error = err
        elif 32 <= key <= 126:
            if self.join_field == 0:
                self.join_game_id += chr(key)
            elif self.join_field == 1:
                self.join_name += chr(key)
        return True

    def _handle_settings(self, key: int) -> bool:
        if key == ord('q'):
            self.screen = Screen.MENU
            self.error = None
        elif key == ord('\t'):
            self.settings_field = (self.settings_field + 1) % 2
        elif key in (curses.KEY_BACKSPACE, 127, 8):
            if self.settings_field == 0:
                self.settings_host = self.settings_host[:-1]
            else:
                self.settings_token = self.settings_token[:-1]
        elif key in (ord('\n'), curses.KEY_ENTER):
            if not self.settings_host:
                self.error = "Host is required"
            else:
                self.config.host = self.settings_host
                self.config.token = self.settings_token
                save_config(self.config)
                self.api.update_config(self.config)
                self.screen = Screen.MENU
                self.error = None
        elif 32 <= key <= 126:
            if self.settings_field == 0:
                self.settings_host += chr(key)
            else:
                self.settings_token += chr(key)
        return True

    def _handle_game(self, key: int) -> bool:
        # Clear error on any keypress
        if self.error:
            self.error = None
            return True

        # Quit
        if key == ord('q') and not self.input_buf:
            return False

        # Scroll keys
        if key == ord('['):
            max_scroll = max(0, len(self.game.get("log", [])) - 1) if self.game else 0
            self.log_scroll = min(self.log_scroll + 1, max_scroll)
            return True
        if key == ord(']'):
            self.log_scroll = max(0, self.log_scroll - 1)
            return True
        if key == ord('-'):
            max_scroll = max(0, len(self.game.get("chat", [])) - 1) if self.game else 0
            self.chat_scroll = min(self.chat_scroll + 1, max_scroll)
            return True
        if key == ord('='):
            self.chat_scroll = max(0, self.chat_scroll - 1)
            return True

        # Arrow keys for guesser board navigation
        if self.config.role == Role.GUESSER and not self.input_buf:
            if key == curses.KEY_UP:
                self.cursor_row = max(0, self.cursor_row - 1)
                return True
            if key == curses.KEY_DOWN:
                self.cursor_row = min(self.board_cols - 1, self.cursor_row + 1)
                return True
            if key == curses.KEY_LEFT:
                self.cursor_col = max(0, self.cursor_col - 1)
                return True
            if key == curses.KEY_RIGHT:
                self.cursor_col = min(self.board_cols - 1, self.cursor_col + 1)
                return True
            if key in (ord('\n'), curses.KEY_ENTER) and not self.input_buf:
                self._submit_board_guess()
                return True

        # Backspace
        if key in (curses.KEY_BACKSPACE, 127, 8):
            self.input_buf = self.input_buf[:-1]
            self.is_typing = bool(self.input_buf)
            return True

        # Enter — submit
        if key in (ord('\n'), curses.KEY_ENTER):
            self._submit_input()
            self.is_typing = False
            self.game = self.api.get_game()
            self.last_refresh = time.time()
            return True

        # Regular character
        if 32 <= key <= 126:
            self.input_buf += chr(key)
            self.is_typing = True
            return True

        return True

    def _submit_board_guess(self):
        if not self.game:
            return
        board = self.game["board"]
        idx = self.cursor_row * self.board_cols + self.cursor_col
        word = board[idx]["word"]
        ok, err = self.api.guess(word)
        if not ok:
            self.error = err
        else:
            self.game = self.api.get_game()
            self.last_refresh = time.time()

    def _submit_input(self):
        text = self.input_buf.strip()
        self.input_buf = ""

        if not text:
            return

        if text.startswith("/clue "):
            parts = text.split()
            if len(parts) != 3:
                self.error = "Usage: /clue <word> <number>"
                return
            try:
                number = int(parts[2])
            except ValueError:
                self.error = "Number must be an integer"
                return
            ok, err = self.api.clue(parts[1], number)
            if not ok:
                self.error = err

        elif text == "/pass":
            if self.config.role == Role.SPYMASTER:
                self.error = "/pass is for guesser only"
                return
            ok, err = self.api.pass_turn()
            if not ok:
                self.error = err

        elif text.startswith("/guess "):
            if self.config.role == Role.SPYMASTER:
                self.error = "/guess is for guesser only"
                return
            word = text[7:].strip()
            ok, err = self.api.guess(word)
            if not ok:
                self.error = err

        else:
            ok, err = self.api.chat(text)
            if not ok:
                self.error = err


##### Entry Point #####
def run():
    curses.wrapper(main)

def main(stdscr):
    tui = TUI(stdscr)
    tui.run()

if __name__ == "__main__":
    curses.wrapper(main)