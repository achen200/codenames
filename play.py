#!/usr/bin/env python3
"""Interactive TUI for Cooperative Codenames."""

import curses
import sys
from codenames import (
    new_game, load_game, save_game, find_word, team_words_remaining,
    end_guesser_turn, GameNotFound, BOARD_SIZE, TEAM_COUNT, get_max_guess_rounds,
    GAMES_DIR, delete_game,
)


def init_colors():
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_GREEN, -1)   # TEAM
    curses.init_pair(2, curses.COLOR_RED, -1)      # ASSASSIN
    curses.init_pair(3, curses.COLOR_WHITE, -1)    # BYSTANDER / default
    curses.init_pair(4, curses.COLOR_BLACK, curses.COLOR_WHITE)  # cursor highlight
    curses.init_pair(5, curses.COLOR_YELLOW, -1)   # messages
    curses.init_pair(6, curses.COLOR_BLACK, curses.COLOR_GREEN)  # cursor on team (spymaster)
    curses.init_pair(7, curses.COLOR_BLACK, curses.COLOR_RED)    # cursor on assassin (spymaster)
    curses.init_pair(8, 8, -1)                     # dim/gray for revealed bystander
    curses.init_pair(9, curses.COLOR_BLUE, -1)      # current user chat name


def color_for_role(role, revealed=False):
    if role == "TEAM":
        return curses.color_pair(1) | curses.A_BOLD
    elif role == "ASSASSIN":
        return curses.color_pair(2) | curses.A_BOLD
    else:
        if revealed:
            return curses.color_pair(8) | curses.A_DIM
        return curses.color_pair(3)


def cursor_color_for_role(role, show_key):
    if show_key:
        if role == "TEAM":
            return curses.color_pair(6) | curses.A_BOLD
        elif role == "ASSASSIN":
            return curses.color_pair(7) | curses.A_BOLD
    return curses.color_pair(4) | curses.A_BOLD


def draw_board(win, state, show_key, cursor_idx, start_y=2):
    """Draw the 5x5 board. Returns the row after the board."""
    col_width = 16
    for row in range(5):
        for col in range(5):
            idx = row * 5 + col
            word = state["words"][idx]
            role = state["key"][str(idx)]
            x = 2 + col * col_width
            y = start_y + row

            is_cursor = (idx == cursor_idx)
            revealed = idx in state["revealed"]

            if revealed:
                attr = cursor_color_for_role(role, True) if is_cursor else color_for_role(role, revealed=True)
                display = f"[{word}]"
            elif show_key:
                if is_cursor:
                    attr = cursor_color_for_role(role, True)
                else:
                    attr = color_for_role(role)
                display = word
            else:
                if is_cursor and not revealed:
                    attr = curses.color_pair(4) | curses.A_BOLD
                else:
                    attr = curses.color_pair(3)
                display = word

            # Pad to col_width
            display = display.ljust(col_width - 1)
            try:
                win.addstr(y, x, display, attr)
            except curses.error:
                pass

    return start_y + 5


def text_input(win, y, x, prompt, max_len=30, wrap_width=0, reject_chars=""):
    """Simple text input at position. If wrap_width > 0, input wraps within that width."""
    curses.curs_set(1)
    win.addstr(y, x, prompt, curses.color_pair(5))
    win.refresh()
    if wrap_width <= 0:
        curses.echo()
        inp = win.getstr(y, x + len(prompt), max_len).decode("utf-8").strip()
        curses.noecho()
        curses.curs_set(0)
        return inp
    # Character-by-character input with wrapping
    curses.noecho()
    buf = []
    start_x = x + len(prompt)
    line_w = wrap_width - start_x
    while True:
        # Compute cursor position
        pos = len(buf)
        cy = y + pos // line_w
        cx = start_x + pos % line_w
        try:
            win.move(cy, cx)
        except curses.error:
            pass
        win.refresh()
        ch = win.getch()
        if ch in (curses.KEY_ENTER, 10, 13):
            break
        elif ch in (curses.KEY_BACKSPACE, 127, 8):
            if buf:
                buf.pop()
                # Clear old char
                pos = len(buf)
                cy = y + pos // line_w
                cx = start_x + pos % line_w
                try:
                    win.addch(cy, cx, ' ')
                except curses.error:
                    pass
        elif ch == 27:  # Escape — cancel
            curses.curs_set(0)
            return ""
        elif 32 <= ch <= 126 and len(buf) < max_len and chr(ch) not in reject_chars:
            buf.append(chr(ch))
            pos = len(buf) - 1
            cy = y + pos // line_w
            cx = start_x + pos % line_w
            try:
                win.addch(cy, cx, ch, curses.color_pair(3))
            except curses.error:
                pass
    curses.curs_set(0)
    return "".join(buf).strip()


def pick_role(stdscr, prompt, players=None):
    """Arrow-key role picker. Grays out taken roles showing player name. Returns role string."""
    if players is None:
        players = {}
    stdscr.clear()
    stdscr.addstr(1, 2, prompt, curses.color_pair(5))
    roles = ["Spymaster", "Guesser"]
    role_keys = ["spymaster", "guesser"]
    available = [r not in players for r in role_keys]

    # Start cursor on first available role
    sel = 0 if available[0] else 1
    while True:
        for i, r in enumerate(roles):
            if not available[i]:
                taken_by = players.get(role_keys[i], "?")
                stdscr.addstr(3 + i, 4, f"  {r}  (taken by {taken_by})", curses.color_pair(8) | curses.A_DIM)
            elif i == sel:
                stdscr.addstr(3 + i, 4, f"  {r}  ", curses.color_pair(4) | curses.A_BOLD)
            else:
                stdscr.addstr(3 + i, 4, f"  {r}  ", curses.color_pair(3))
        stdscr.refresh()
        k = stdscr.getch()
        if k == curses.KEY_UP and sel > 0:
            sel -= 1
        elif k == curses.KEY_DOWN and sel < 1:
            sel += 1
        elif k in (curses.KEY_ENTER, 10, 13):
            if available[sel]:
                return role_keys[sel]


def prompt_name(stdscr, y=9):
    """Ask for player name. Returns non-empty string."""
    while True:
        name = text_input(stdscr, y, 2, "Your name: ", 20)
        if name:
            return name
        stdscr.addstr(y + 1, 2, "Name cannot be empty.", curses.color_pair(2))
        stdscr.refresh()


def menu_screen(stdscr):
    """Main menu. Returns (role, game_id, player_name) or None to quit."""
    stdscr.clear()
    stdscr.addstr(1, 2, "=== COOPERATIVE CODENAMES ===", curses.color_pair(1) | curses.A_BOLD)
    options = ["Create New Game", "Join Game", "Quit"]
    selected = 0

    while True:
        for i, opt in enumerate(options):
            attr = curses.color_pair(4) | curses.A_BOLD if i == selected else curses.color_pair(3)
            stdscr.addstr(3 + i, 4, f"  {opt}  ", attr)
        stdscr.addstr(7, 2, "Use ↑/↓ arrows and Enter to select", curses.color_pair(8) | curses.A_DIM)
        stdscr.refresh()

        key = stdscr.getch()
        if key == curses.KEY_UP and selected > 0:
            selected -= 1
        elif key == curses.KEY_DOWN and selected < len(options) - 1:
            selected += 1
        elif key in (curses.KEY_ENTER, 10, 13):
            if selected == 2:  # Quit
                return None

            if selected == 0:  # Create
                game_id = text_input(stdscr, 9, 2, "Game ID (blank for auto): ", 30)
                game_id = game_id if game_id else None
                if game_id and (GAMES_DIR / f"{game_id}.json").exists():
                    stdscr.addstr(11, 2, f"Game '{game_id}' already exists! Press any key.", curses.color_pair(2))
                    stdscr.refresh()
                    stdscr.getch()
                    stdscr.clear()
                    continue
                name = prompt_name(stdscr, 11)
                state = new_game(game_id)
                role = pick_role(stdscr, f"Game '{state['id']}' created. Join as:", state.get("players", {}))
                state = load_game(state["id"])
                state["roles_taken"].append(role)
                state["players"][role] = name
                save_game(state)
                return (role, state["id"], name)

            else:  # Join / Resume
                game_id = text_input(stdscr, 9, 2, "Game ID: ", 30)
                if not game_id:
                    stdscr.clear()
                    continue
                if not (GAMES_DIR / f"{game_id}.json").exists():
                    stdscr.addstr(11, 2, f"Game '{game_id}' not found! Press any key.", curses.color_pair(2))
                    stdscr.refresh()
                    stdscr.getch()
                    stdscr.clear()
                    continue
                name = prompt_name(stdscr, 11)
                state = load_game(game_id)
                players = state.get("players", {})

                # Check if this player is already in the game — resume their role
                for r, n in players.items():
                    if n == name:
                        return (r, game_id, name)

                # New player joining — check if game is full
                if len(players) >= 2:
                    stdscr.addstr(13, 2, "Game is full! Both roles taken. Press any key.", curses.color_pair(2))
                    stdscr.refresh()
                    stdscr.getch()
                    stdscr.clear()
                    continue

                role = pick_role(stdscr, f"Joining game '{game_id}'. Play as:", players)
                state = load_game(game_id)
                state["roles_taken"].append(role)
                state["players"][role] = name
                save_game(state)
                return (role, game_id, name)


LOG_COL = 85  # x position for the log panel (when wide enough)
CHAT_COL = 85  # x position for the chat panel (when wide enough)
SIDE_PANEL_MIN_WIDTH = 130  # minimum terminal width to use side panel layout


def _panel_layout(win):
    """Return (col, max_text_width, is_side) for log/chat panels based on terminal width."""
    _, max_x = win.getmaxyx()
    if max_x >= SIDE_PANEL_MIN_WIDTH:
        return LOG_COL, max_x - LOG_COL - 1, True
    return 2, max_x - 3, False


def draw_log(win, state, start_y=1, max_lines=10, scroll=0):
    """Draw the action log. Uses side panel if wide enough, otherwise uses start_y."""
    col, max_w, is_side = _panel_layout(win)
    y = 1 if is_side else start_y
    try:
        win.addstr(y, col, "── Action Log ──", curses.color_pair(5) | curses.A_BOLD)
    except curses.error:
        return start_y if not is_side else start_y
    log = state.get("log", [])
    total = len(log)
    end = total - scroll
    start = max(0, end - max_lines)
    visible = log[start:end]
    above = start
    below = total - end
    if above > 0:
        try:
            win.addstr(y + 1, col, f"  ↑ {above} more (-)", curses.color_pair(8) | curses.A_DIM)
        except curses.error:
            pass
        row_offset = y + 2
    else:
        row_offset = y + 1
    for i, entry in enumerate(visible):
        row = row_offset + i
        if entry.startswith("[CLUE]"):
            attr = curses.color_pair(5)
        elif "TEAM" in entry:
            attr = curses.color_pair(1)
        elif "ASSASSIN" in entry:
            attr = curses.color_pair(2) | curses.A_BOLD
        elif "bystander" in entry.lower():
            attr = curses.color_pair(8) | curses.A_DIM
        else:
            attr = curses.color_pair(3)
        text = entry[:max_w]
        try:
            win.addstr(row, col, text, attr)
        except curses.error:
            pass
    end_y = row_offset + len(visible)
    if below > 0:
        try:
            win.addstr(end_y, col, f"  ↓ {below} more (=)", curses.color_pair(8) | curses.A_DIM)
        except curses.error:
            pass
        end_y += 1
    return end_y if not is_side else start_y


def draw_chat(win, state, start_y, max_lines=8, scroll=0, player_name=""):
    """Draw the chat panel. Uses side panel if wide enough, otherwise uses start_y."""
    col, max_w, is_side = _panel_layout(win)
    if is_side:
        # Find where log ended on the side
        log = state.get("log", [])
        visible_log = log[-10:]
        base_y = 1 + 1 + len(visible_log)
    else:
        base_y = start_y
    try:
        win.addstr(base_y + 1, col, "── Chat ──", curses.color_pair(5) | curses.A_BOLD)
    except curses.error:
        return start_y if not is_side else start_y
    chat = state.get("chat", [])
    total = len(chat)
    end = total - scroll
    start = max(0, end - max_lines)
    visible = chat[start:end]
    above = start
    below = total - end
    if above > 0:
        try:
            win.addstr(base_y + 2, col, f"  ↑ {above} more", curses.color_pair(8) | curses.A_DIM)
        except curses.error:
            pass
        msg_start = base_y + 3
    else:
        msg_start = base_y + 2
    row = msg_start
    for entry in visible:
        name_str = f"{entry['name']}: "
        name_color = curses.color_pair(9) | curses.A_BOLD if entry['name'] == player_name else curses.color_pair(5) | curses.A_BOLD
        full_msg = name_str + entry['msg']
        # Wrap into lines of max_w
        lines = [full_msg[j:j+max_w] for j in range(0, len(full_msg), max_w)]
        for k, line in enumerate(lines):
            try:
                if k == 0:
                    win.addstr(row, col, name_str, name_color)
                    win.addstr(row, col + len(name_str), line[len(name_str):], curses.color_pair(3))
                else:
                    win.addstr(row, col, line, curses.color_pair(3))
            except curses.error:
                pass
            row += 1
    if below > 0:
        try:
            win.addstr(row, col, f"  ↓ {below} more", curses.color_pair(8) | curses.A_DIM)
        except curses.error:
            pass
        row += 1
    if not is_side:
        return row
    return start_y


def draw_game_screen(win, state, role, game_id, cursor_idx=-1, message="", msg_color=None, chat_scroll=0, log_scroll=0, player_name=""):
    """Draw the full persistent game screen: header, board, status, log, message."""
    if msg_color is None:
        msg_color = curses.color_pair(3)
    show_key = (role == "spymaster")

    win.clear()
    # Header
    role_label = "SPYMASTER" if role == "spymaster" else "GUESSER"
    players = state.get("players", {})
    player_info = "  |  ".join(f"{r.title()}: {n}" for r, n in players.items())
    win.addstr(0, 2, f"{role_label}  |  Game: {game_id}  |  {player_info}",
               curses.color_pair(1 if role == "spymaster" else 5) | curses.A_BOLD)

    # Board
    after_board = draw_board(win, state, show_key=show_key, cursor_idx=cursor_idx, start_y=2)

    # Status below board
    y = after_board + 1
    remaining = len(team_words_remaining(state))
    win.addstr(y, 2, f"Team words left: {remaining}  |  Guess rounds left: {state['guesses_left']}", curses.color_pair(5))
    y += 1
    if state["turn"] == "guesser" and state["clues"]:
        last = state["clues"][-1]
        win.addstr(y, 2, f"Current clue: {last['word']} : {last['number']}  |  Guesses this round: {state['clue_guesses_left']}", curses.color_pair(1) | curses.A_BOLD)
        y += 1

    # Message line
    if message:
        win.addstr(y, 2, message, msg_color)
        y += 1

    # Log and chat panels (side or below depending on width)
    _, max_x = win.getmaxyx()
    if max_x >= SIDE_PANEL_MIN_WIDTH:
        draw_log(win, state, scroll=log_scroll)
        draw_chat(win, state, y, scroll=chat_scroll, player_name=player_name)
    else:
        y = draw_log(win, state, start_y=y + 1, scroll=log_scroll)
        y = draw_chat(win, state, start_y=y, scroll=chat_scroll, player_name=player_name)

    return y


def wait_for_quit(stdscr):
    """Block until 'q' is pressed."""
    while stdscr.getch() != ord('q'):
        pass


def show_game_over(stdscr, state, role, game_id, message):
    """Show final board with key revealed and game over message."""
    stdscr.clear()
    players = state.get("players", {})
    player_info = "  |  ".join(f"{r.title()}: {n}" for r, n in players.items())
    stdscr.addstr(0, 2, f"GAME OVER  |  Game: {game_id}  |  {player_info}", curses.color_pair(2) | curses.A_BOLD)
    draw_board(stdscr, state, show_key=True, cursor_idx=-1, start_y=2)
    y = 8
    _, max_x = stdscr.getmaxyx()
    if max_x >= SIDE_PANEL_MIN_WIDTH:
        draw_log(stdscr, state)
    else:
        stdscr.addstr(y, 2, message, curses.color_pair(2) | curses.A_BOLD)
        y += 2
        y = draw_log(stdscr, state, start_y=y)
        stdscr.addstr(y + 1, 2, "Press 'q' to return to menu.", curses.color_pair(3))
        stdscr.refresh()
        wait_for_quit(stdscr)
        delete_game(game_id)
        return
    stdscr.addstr(8, 2, message, curses.color_pair(2) | curses.A_BOLD)
    stdscr.addstr(10, 2, "Press 'q' to return to menu.", curses.color_pair(3))
    stdscr.refresh()
    wait_for_quit(stdscr)
    delete_game(game_id)


def send_chat(stdscr, state, game_id, name, y):
    """Prompt for a chat message and save it."""
    _, max_x = stdscr.getmaxyx()
    wrap_w = min(max_x, LOG_COL) if max_x >= SIDE_PANEL_MIN_WIDTH else max_x
    msg = text_input(stdscr, y, 2, "Chat: ", 200, wrap_width=wrap_w)
    if msg:
        state = load_game(game_id)
        state.setdefault("chat", []).append({"name": name, "msg": msg})
        save_game(state)
    return 0  # reset scroll to bottom after sending


def clamp_scroll(state, scroll, max_lines=8):
    total = len(state.get("chat", []))
    max_scroll = max(0, total - max_lines)
    return max(0, min(scroll, max_scroll))


def clamp_log_scroll(state, scroll, max_lines=10):
    total = len(state.get("log", []))
    max_scroll = max(0, total - max_lines)
    return max(0, min(scroll, max_scroll))


def show_win(stdscr, state, role, game_id):
    stdscr.clear()
    players = state.get("players", {})
    player_info = "  |  ".join(f"{r.title()}: {n}" for r, n in players.items())
    stdscr.addstr(0, 2, f"YOU WIN!  |  Game: {game_id}  |  {player_info}", curses.color_pair(1) | curses.A_BOLD)
    draw_board(stdscr, state, show_key=True, cursor_idx=-1, start_y=2)
    y = 8
    _, max_x = stdscr.getmaxyx()
    if max_x >= SIDE_PANEL_MIN_WIDTH:
        draw_log(stdscr, state)
    else:
        stdscr.addstr(y, 2, "All team words found! You win!", curses.color_pair(1) | curses.A_BOLD)
        y += 2
        y = draw_log(stdscr, state, start_y=y)
        stdscr.addstr(y + 1, 2, "Press 'q' to return to menu.", curses.color_pair(3))
        stdscr.refresh()
        wait_for_quit(stdscr)
        delete_game(game_id)
        return
    stdscr.addstr(8, 2, "All team words found! You win!", curses.color_pair(1) | curses.A_BOLD)
    stdscr.addstr(10, 2, "Press 'q' to return to menu.", curses.color_pair(3))
    stdscr.refresh()
    wait_for_quit(stdscr)
    delete_game(game_id)


def add_log(state, entry):
    state.setdefault("log", []).append(entry)


def spymaster_screen(stdscr, game_id, player_name):
    """Spymaster game loop."""
    chat_scroll = 0
    log_scroll = 0
    while True:
        try:
            state = load_game(game_id)
        except GameNotFound:
            wait_for_quit(stdscr)
            return

        if state["status"] != "active":
            if "won" in state["status"]:
                show_win(stdscr, state, "spymaster", game_id)
            else:
                show_game_over(stdscr, state, "spymaster", game_id, f"Game over: {state['status']}")
            return

        y = draw_game_screen(stdscr, state, "spymaster", game_id, chat_scroll=chat_scroll, log_scroll=log_scroll, player_name=player_name)

        if state["turn"] == "spymaster":
            stdscr.addstr(y, 2, "YOUR TURN — press Enter to give a clue!", curses.color_pair(5) | curses.A_BOLD)
            y += 1
            stdscr.addstr(y, 2, "'c' chat  '[' ']' chat scroll  '-' '=' log scroll  'q' quit", curses.color_pair(8) | curses.A_DIM)
            stdscr.refresh()
            stdscr.timeout(1000)
            got_input = False
            while True:
                k = stdscr.getch()
                if k == ord('q'):
                    stdscr.timeout(-1)
                    return
                if k in (ord('c'), ord('C')):
                    stdscr.timeout(-1)
                    chat_scroll = send_chat(stdscr, state, game_id, player_name, y + 1)
                    break
                if k == ord('['):
                    chat_scroll = clamp_scroll(state, chat_scroll + 1)
                    break
                if k == ord(']'):
                    chat_scroll = clamp_scroll(state, chat_scroll - 1)
                    break
                if k == ord('-'):
                    log_scroll = clamp_log_scroll(state, log_scroll + 1)
                    break
                if k == ord('='):
                    log_scroll = clamp_log_scroll(state, log_scroll - 1)
                    break
                if k in (curses.KEY_ENTER, 10, 13):
                    got_input = True
                    break
                # Timeout — refresh state for chat/player updates
                try:
                    state = load_game(game_id)
                except GameNotFound:
                    stdscr.timeout(-1)
                    wait_for_quit(stdscr)
                    return
                if state["status"] != "active":
                    break
                y = draw_game_screen(stdscr, state, "spymaster", game_id, chat_scroll=chat_scroll, log_scroll=log_scroll, player_name=player_name)
                stdscr.addstr(y, 2, "YOUR TURN — press Enter to give a clue!", curses.color_pair(5) | curses.A_BOLD)
                y += 1
                stdscr.addstr(y, 2, "'c' chat  '[' ']' chat scroll  '-' '=' log scroll  'q' quit", curses.color_pair(8) | curses.A_DIM)
                stdscr.refresh()
            stdscr.timeout(-1)
            if not got_input:
                continue
            y += 1
            clue_word = text_input(stdscr, y, 2, "Clue word: ", 30, wrap_width=80, reject_chars="[]-=")
            if not clue_word:
                continue
            clue_word = clue_word.upper()

            # Must be a single word
            if ' ' in clue_word.strip():
                stdscr.addstr(y + 1, 2, "Clue must be a single word! Press any key.", curses.color_pair(2))
                stdscr.refresh()
                stdscr.getch()
                continue

            # Validate
            visible = [state["words"][i].upper() for i in range(BOARD_SIZE) if i not in state["revealed"]]
            invalid = False
            if clue_word in visible:
                stdscr.addstr(y + 1, 2, f"'{clue_word}' is on the board! Press any key.", curses.color_pair(2))
                stdscr.refresh()
                stdscr.getch()
                continue
            for v in visible:
                if clue_word in v.split() or v in clue_word.split():
                    stdscr.addstr(y + 1, 2, f"'{clue_word}' overlaps with '{v}'! Press any key.", curses.color_pair(2))
                    stdscr.refresh()
                    stdscr.getch()
                    invalid = True
                    break
            if invalid:
                continue

            y += 1
            clue_num_str = text_input(stdscr, y, 2, "Number: ", 5, wrap_width=80)
            try:
                clue_num = int(clue_num_str)
                if clue_num < 0:
                    raise ValueError
            except ValueError:
                stdscr.addstr(y + 1, 2, "Invalid number. Press any key.", curses.color_pair(2))
                stdscr.refresh()
                stdscr.getch()
                continue

            spy_name = state.get("players", {}).get("spymaster", "Spymaster")
            add_log(state, f"[CLUE] {spy_name}: {clue_word} : {clue_num}")
            state["clues"].append({"word": clue_word, "number": clue_num})
            state["turn"] = "guesser"
            state["clue_guesses_left"] = clue_num + 1
            save_game(state)
        else:
            stdscr.addstr(y, 2, f"Waiting for guesser... ({state['clue_guesses_left']} guess(es) left)", curses.color_pair(5))
            stdscr.addstr(y + 1, 2, "'c' chat  '[' ']' chat scroll  '-' '=' log scroll  'q' quit", curses.color_pair(8) | curses.A_DIM)
            stdscr.refresh()
            stdscr.timeout(1000)
            while True:
                k = stdscr.getch()
                if k == ord('q'):
                    stdscr.timeout(-1)
                    return
                if k in (ord('c'), ord('C')):
                    stdscr.timeout(-1)
                    chat_scroll = send_chat(stdscr, state, game_id, player_name, y + 2)
                    stdscr.timeout(1000)
                    break
                if k == ord('['):
                    chat_scroll = clamp_scroll(state, chat_scroll + 1)
                    break
                if k == ord(']'):
                    chat_scroll = clamp_scroll(state, chat_scroll - 1)
                    break
                if k == ord('-'):
                    log_scroll = clamp_log_scroll(state, log_scroll + 1)
                    break
                if k == ord('='):
                    log_scroll = clamp_log_scroll(state, log_scroll - 1)
                    break
                try:
                    new_state = load_game(game_id)
                except GameNotFound:
                    stdscr.timeout(-1)
                    wait_for_quit(stdscr)
                    return
                if new_state["turn"] == "spymaster" or new_state["status"] != "active":
                    break
                y = draw_game_screen(stdscr, new_state, "spymaster", game_id, log_scroll=log_scroll, player_name=player_name)
                stdscr.addstr(y, 2, f"Waiting for guesser... ({new_state['clue_guesses_left']} guess(es) left)", curses.color_pair(5))
                stdscr.addstr(y + 1, 2, "'c' chat  '[' ']' chat scroll  '-' '=' log scroll  'q' quit", curses.color_pair(8) | curses.A_DIM)
                stdscr.refresh()
            stdscr.timeout(-1)


def guesser_screen(stdscr, game_id, player_name):
    """Guesser game loop with arrow-key word selection."""
    cursor = 0
    chat_scroll = 0
    log_scroll = 0

    while True:
        try:
            state = load_game(game_id)
        except GameNotFound:
            wait_for_quit(stdscr)
            return

        if state["status"] != "active":
            if "won" in state["status"]:
                show_win(stdscr, state, "guesser", game_id)
            else:
                show_game_over(stdscr, state, "guesser", game_id, f"Game over: {state['status']}")
            return

        if state["turn"] != "guesser":
            y = draw_game_screen(stdscr, state, "guesser", game_id, chat_scroll=chat_scroll, log_scroll=log_scroll, player_name=player_name)
            stdscr.addstr(y, 2, "Waiting for spymaster to give a clue...", curses.color_pair(5))
            stdscr.addstr(y + 1, 2, "'c' chat  '[' ']' chat scroll  '-' '=' log scroll  'q' quit", curses.color_pair(8) | curses.A_DIM)
            stdscr.refresh()
            stdscr.timeout(1000)
            while True:
                k = stdscr.getch()
                if k == ord('q'):
                    stdscr.timeout(-1)
                    return
                if k in (ord('c'), ord('C')):
                    stdscr.timeout(-1)
                    chat_scroll = send_chat(stdscr, state, game_id, player_name, y + 2)
                    stdscr.timeout(1000)
                    break
                if k == ord('['):
                    chat_scroll = clamp_scroll(state, chat_scroll + 1)
                    break
                if k == ord(']'):
                    chat_scroll = clamp_scroll(state, chat_scroll - 1)
                    break
                if k == ord('-'):
                    log_scroll = clamp_log_scroll(state, log_scroll + 1)
                    break
                if k == ord('='):
                    log_scroll = clamp_log_scroll(state, log_scroll - 1)
                    break
                try:
                    new_state = load_game(game_id)
                except GameNotFound:
                    stdscr.timeout(-1)
                    wait_for_quit(stdscr)
                    return
                if new_state["turn"] == "guesser" or new_state["status"] != "active":
                    break
            stdscr.timeout(-1)
            continue

        # Active guessing loop
        message = ""
        msg_color = curses.color_pair(3)

        while True:
            y = draw_game_screen(stdscr, state, "guesser", game_id,
                                 cursor_idx=cursor, message=message, msg_color=msg_color, chat_scroll=chat_scroll, log_scroll=log_scroll, player_name=player_name)

            # Controls
            stdscr.addstr(y, 2, "↑↓←→ move | Enter guess | P pass | C chat | [ ] chat | - = log | Q quit", curses.color_pair(8) | curses.A_DIM)
            y += 1
            word = state["words"][cursor]
            stdscr.addstr(y, 2, f"Selected: {word}", curses.color_pair(4) | curses.A_BOLD)
            stdscr.refresh()

            key = stdscr.getch()
            message = ""  # clear message on next action

            # Navigation
            row, col = divmod(cursor, 5)
            if key == curses.KEY_UP and row > 0:
                cursor -= 5
            elif key == curses.KEY_DOWN and row < 4:
                cursor += 5
            elif key == curses.KEY_LEFT and col > 0:
                cursor -= 1
            elif key == curses.KEY_RIGHT and col < 4:
                cursor += 1

            elif key in (curses.KEY_ENTER, 10, 13):
                if cursor in state["revealed"]:
                    message = "Already revealed!"
                    msg_color = curses.color_pair(2)
                    continue

                word = state["words"][cursor]
                role = state["key"][str(cursor)]
                state["revealed"].append(cursor)
                guesser_name = state.get("players", {}).get("guesser", "Guesser")

                if role == "ASSASSIN":
                    add_log(state, f"[GUESS] {guesser_name}: {word} → ASSASSIN!")
                    state["status"] = "lost — assassin"
                    save_game(state)
                    show_game_over(stdscr, state, "guesser", game_id, f"'{word}' is the ASSASSIN! Game over.")
                    return

                elif role == "TEAM":
                    add_log(state, f"[GUESS] {guesser_name}: {word} → TEAM ✓")
                    if not team_words_remaining(state):
                        state["status"] = "won"
                        save_game(state)
                        show_win(stdscr, state, "guesser", game_id)
                        return
                    state["clue_guesses_left"] -= 1
                    if state["clue_guesses_left"] <= 0:
                        add_log(state, "[TURN] Round over — no guesses left")
                        end_guesser_turn(state)
                        save_game(state)
                        if state["status"] != "active":
                            show_game_over(stdscr, state, "guesser", game_id, "No guess rounds left. Game over.")
                            return
                        break
                    message = f"'{word}' is a TEAM word!"
                    msg_color = curses.color_pair(1) | curses.A_BOLD
                    save_game(state)

                else:
                    add_log(state, f"[GUESS] {guesser_name}: {word} → bystander")
                    add_log(state, "[TURN] Bystander hit — turn ends")
                    end_guesser_turn(state)
                    save_game(state)
                    if state["status"] != "active":
                        show_game_over(stdscr, state, "guesser", game_id, "No guess rounds left. Game over.")
                        return
                    break

            elif key in (ord('p'), ord('P')):
                guesser_name = state.get("players", {}).get("guesser", "Guesser")
                add_log(state, f"[PASS] {guesser_name} passed")
                end_guesser_turn(state)
                save_game(state)
                if state["status"] != "active":
                    show_game_over(stdscr, state, "guesser", game_id, "No guess rounds left. Game over.")
                    return
                break

            elif key in (ord('q'), ord('Q')):
                return

            elif key in (ord('c'), ord('C')):
                chat_scroll = send_chat(stdscr, state, game_id, player_name, y + 1)
                state = load_game(game_id)

            elif key == ord('['):
                chat_scroll = clamp_scroll(state, chat_scroll + 1)

            elif key == ord(']'):
                chat_scroll = clamp_scroll(state, chat_scroll - 1)

            elif key == ord('-'):
                log_scroll = clamp_log_scroll(state, log_scroll + 1)

            elif key == ord('='):
                log_scroll = clamp_log_scroll(state, log_scroll - 1)


def main(stdscr):
    curses.curs_set(0)
    stdscr.scrollok(False)
    init_colors()

    while True:
        result = menu_screen(stdscr)
        if result is None:
            break
        role, game_id, name = result[0], result[1], result[2]
        try:
            if role == "spymaster":
                spymaster_screen(stdscr, game_id, name)
            else:
                guesser_screen(stdscr, game_id, name)
        except GameNotFound as e:
            stdscr.clear()
            stdscr.addstr(2, 2, str(e), curses.color_pair(2))
            stdscr.addstr(4, 2, "Press any key to return to menu.", curses.color_pair(3))
            stdscr.refresh()
            stdscr.getch()


if __name__ == "__main__":
    curses.wrapper(main)
