#!/usr/bin/env python3
"""Codenames network client — connects to a server and provides the TUI."""

import curses
import json
import sys
import urllib.request
import urllib.error

BOARD_SIZE = 25
BASE_URL = ""
AUTH_TOKEN = ""


def api(method, path, body=None):
    """Make an API call. Returns (status_code, parsed_json)."""
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"}
    if AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {AUTH_TOKEN}"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        resp = urllib.request.urlopen(req)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def init_colors():
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_GREEN, -1)
    curses.init_pair(2, curses.COLOR_RED, -1)
    curses.init_pair(3, curses.COLOR_WHITE, -1)
    curses.init_pair(4, curses.COLOR_BLACK, curses.COLOR_WHITE)
    curses.init_pair(5, curses.COLOR_YELLOW, -1)
    curses.init_pair(6, curses.COLOR_BLACK, curses.COLOR_GREEN)
    curses.init_pair(7, curses.COLOR_BLACK, curses.COLOR_RED)
    curses.init_pair(8, 8, -1)
    curses.init_pair(9, curses.COLOR_BLUE, -1)


def color_for_role(role, revealed=False):
    if role == "TEAM":
        return curses.color_pair(1) | curses.A_BOLD
    elif role == "ASSASSIN":
        return curses.color_pair(2) | curses.A_BOLD
    else:
        return (curses.color_pair(8) | curses.A_DIM) if revealed else curses.color_pair(3)


def cursor_color_for_role(role, show_key):
    if show_key:
        if role == "TEAM":
            return curses.color_pair(6) | curses.A_BOLD
        elif role == "ASSASSIN":
            return curses.color_pair(7) | curses.A_BOLD
    return curses.color_pair(4) | curses.A_BOLD


LOG_COL = 85
CHAT_COL = 85
SIDE_PANEL_MIN_WIDTH = 130


def _panel_layout(win):
    """Return (col, max_text_width, is_side) for log/chat panels based on terminal width."""
    _, max_x = win.getmaxyx()
    if max_x >= SIDE_PANEL_MIN_WIDTH:
        return LOG_COL, max_x - LOG_COL - 1, True
    return 2, max_x - 3, False


def draw_board(win, state, show_key, cursor_idx, start_y=2):
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
                attr = cursor_color_for_role(role, True) if is_cursor else color_for_role(role)
                display = word
            else:
                attr = (curses.color_pair(4) | curses.A_BOLD) if (is_cursor and not revealed) else curses.color_pair(3)
                display = word
            try:
                win.addstr(y, x, display.ljust(col_width - 1), attr)
            except curses.error:
                pass
    return start_y + 5


def draw_log(win, state, start_y=1, max_lines=10, scroll=0):
    col, max_w, is_side = _panel_layout(win)
    y = 1 if is_side else start_y
    try:
        win.addstr(y, col, "── Action Log ──", curses.color_pair(5) | curses.A_BOLD)
    except curses.error:
        return start_y
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
        try:
            win.addstr(row, col, entry[:max_w], attr)
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


def draw_chat(win, state, start_y, max_lines=8, scroll=0, player_name="", max_row=0):
    max_y, _ = win.getmaxyx()
    col, max_w, is_side = _panel_layout(win)
    if is_side:
        log = state.get("log", [])
        visible_log = log[-10:]
        base_y = 1 + 1 + len(visible_log)
    else:
        base_y = start_y
    # In non-side-panel mode, use max_row to cap rendering; 0 means no cap
    if max_row <= 0:
        max_row = max_y - 1
    try:
        win.addstr(base_y + 1, col, "── Chat ──", curses.color_pair(5) | curses.A_BOLD)
    except curses.error:
        return start_y
    chat = state.get("chat", [])
    total = len(chat)
    end = total - scroll
    start = max(0, end - max_lines)
    visible = list(chat[start:end])
    above = start
    below = total - end
    # Pre-calculate how many rendered rows each message takes, trim from the top
    def _msg_rows(entry):
        full = f"{entry['name']}: {entry['msg']}"
        return max(1, (len(full) + max_w - 1) // max_w)
    # Layout: title row, ↑ indicator row, messages, ↓ indicator row
    # All 4 chrome rows are always reserved so the message area stays constant
    chrome_rows = 4  # title + ↑ + ↓ + gap
    avail_rows = max_row - (base_y + chrome_rows)
    if avail_rows < 1:
        return base_y + chrome_rows
    # Trim visible messages from the top until they fit in avail_rows
    while visible:
        total_rows = sum(_msg_rows(e) for e in visible)
        if total_rows <= avail_rows:
            break
        visible.pop(0)
        above += 1
    if above > 0:
        try:
            win.addstr(base_y + 2, col, f"  ↑ {above} more", curses.color_pair(8) | curses.A_DIM)
        except curses.error:
            pass
    msg_start = base_y + 3
    row = msg_start
    msg_end = base_y + 3 + avail_rows  # hard limit for messages
    for entry in visible:
        name_str = f"{entry['name']}: "
        name_color = curses.color_pair(9) | curses.A_BOLD if entry['name'] == player_name else curses.color_pair(5) | curses.A_BOLD
        full_msg = name_str + entry['msg']
        lines = [full_msg[j:j+max_w] for j in range(0, len(full_msg), max_w)]
        for k, line in enumerate(lines):
            if row >= msg_end:
                break
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
            win.addstr(msg_end, col, f"  ↓ {below} more", curses.color_pair(8) | curses.A_DIM)
        except curses.error:
            pass
    try:
        win.addstr(msg_end + 1, col, "──────────", curses.color_pair(5) | curses.A_BOLD)
    except curses.error:
        pass
    if not is_side:
        return msg_end + 2
    return start_y


def draw_game_screen(win, state, role, game_id, cursor_idx=-1, message="", msg_color=None, chat_scroll=0, log_scroll=0, player_name="", status_line="", hint_line="", status_color=None):
    if msg_color is None:
        msg_color = curses.color_pair(3)
    show_key = (role == "spymaster")
    win.clear()
    role_label = "SPYMASTER" if role == "spymaster" else "GUESSER"
    players = state.get("players", {})
    player_info = "  |  ".join(f"{r.title()}: {n}" for r, n in players.items())
    win.addstr(0, 2, f"{role_label}  |  Game: {game_id}  |  {player_info}",
               curses.color_pair(1 if role == "spymaster" else 5) | curses.A_BOLD)
    after_board = draw_board(win, state, show_key=show_key, cursor_idx=cursor_idx, start_y=2)
    y = after_board + 1
    remaining = len([i for i in range(BOARD_SIZE) if state["key"][str(i)] == "TEAM" and i not in state["revealed"]])
    win.addstr(y, 2, f"Team words left: {remaining}  |  Guess rounds left: {state['guesses_left']}", curses.color_pair(5))
    y += 1
    if state["turn"] == "guesser" and state["clues"]:
        last = state["clues"][-1]
        win.addstr(y, 2, f"Current clue: {last['word']} : {last['number']}  |  Guesses this round: {state['clue_guesses_left']}", curses.color_pair(1) | curses.A_BOLD)
        y += 1
    if message:
        win.addstr(y, 2, message, msg_color)
        y += 1
    # Status and hint lines always appear right below board info
    if status_line:
        try:
            win.addstr(y, 2, status_line, (status_color if status_color else curses.color_pair(5) | curses.A_BOLD))
        except curses.error:
            pass
        y += 1
    if hint_line:
        try:
            win.addstr(y, 2, hint_line, curses.color_pair(8) | curses.A_DIM)
        except curses.error:
            pass
        y += 1
    _, max_x = win.getmaxyx()
    if max_x >= SIDE_PANEL_MIN_WIDTH:
        draw_log(win, state, scroll=log_scroll)
        draw_chat(win, state, y, scroll=chat_scroll, player_name=player_name)
    else:
        max_y, _ = win.getmaxyx()
        # Reserve rows at bottom for blank + chat-input
        bottom_reserve = 2
        panel_end = max_y - bottom_reserve
        # Give log half the remaining space, chat gets the rest
        panel_space = max(2, panel_end - y - 1)
        log_max = max(1, panel_space // 3)
        y = draw_log(win, state, start_y=y + 1, max_lines=log_max, scroll=log_scroll)
        y = draw_chat(win, state, start_y=y, scroll=chat_scroll, player_name=player_name, max_row=panel_end)
    return y


def text_input(win, y, x, prompt, max_len=30, wrap_width=0, reject_chars=""):
    curses.curs_set(1)
    win.addstr(y, x, prompt, curses.color_pair(5))
    win.refresh()
    if wrap_width <= 0:
        curses.echo()
        inp = win.getstr(y, x + len(prompt), max_len).decode("utf-8").strip()
        curses.noecho()
        curses.curs_set(0)
        return inp
    curses.noecho()
    buf = []
    start_x = x + len(prompt)
    line_w = wrap_width - start_x
    while True:
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
                pos = len(buf)
                cy = y + pos // line_w
                cx = start_x + pos % line_w
                try:
                    win.addch(cy, cx, ' ')
                except curses.error:
                    pass
        elif ch == 27:
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


def prompt_name(stdscr, y=9):
    while True:
        name = text_input(stdscr, y, 2, "Your name: ", 20)
        if name:
            return name
        stdscr.addstr(y + 1, 2, "Name cannot be empty.", curses.color_pair(2))
        stdscr.refresh()


def pick_role(stdscr, prompt, players=None):
    if players is None:
        players = {}
    stdscr.clear()
    stdscr.addstr(1, 2, prompt, curses.color_pair(5))
    roles = ["Spymaster", "Guesser"]
    role_keys = ["spymaster", "guesser"]
    available = [r not in players for r in role_keys]
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


def wait_for_quit(stdscr):
    while stdscr.getch() != ord('q'):
        pass


def send_chat(stdscr, game_id, name, y):
    max_y, max_x = stdscr.getmaxyx()
    chat_row = max_y - 1
    wrap_w = min(max_x, LOG_COL) if max_x >= SIDE_PANEL_MIN_WIDTH else max_x
    msg = text_input(stdscr, chat_row, 2, "Chat: ", 200, wrap_width=wrap_w)
    if msg:
        api("POST", f"/games/{game_id}/chat", {"name": name, "msg": msg})
    return 0


def clamp_scroll(state, scroll, max_lines=8):
    total = len(state.get("chat", []))
    max_scroll = max(0, total - max_lines)
    return max(0, min(scroll, max_scroll))


def clamp_log_scroll(state, scroll, max_lines=10):
    total = len(state.get("log", []))
    max_scroll = max(0, total - max_lines)
    return max(0, min(scroll, max_scroll))


def show_end_screen(stdscr, state, game_id, message, color):
    stdscr.clear()
    players = state.get("players", {})
    player_info = "  |  ".join(f"{r.title()}: {n}" for r, n in players.items())
    stdscr.addstr(0, 2, f"Game: {game_id}  |  {player_info}", color | curses.A_BOLD)
    draw_board(stdscr, state, show_key=True, cursor_idx=-1, start_y=2)
    y = 8
    _, max_x = stdscr.getmaxyx()
    if max_x >= SIDE_PANEL_MIN_WIDTH:
        draw_log(stdscr, state)
    else:
        stdscr.addstr(y, 2, message, color | curses.A_BOLD)
        y += 2
        y = draw_log(stdscr, state, start_y=y)
        stdscr.addstr(y + 1, 2, "Press 'q' to return to menu.", curses.color_pair(3))
        stdscr.refresh()
        wait_for_quit(stdscr)
        api("DELETE", f"/games/{game_id}")
        return
    stdscr.addstr(8, 2, message, color | curses.A_BOLD)
    stdscr.addstr(10, 2, "Press 'q' to return to menu.", curses.color_pair(3))
    stdscr.refresh()
    wait_for_quit(stdscr)
    api("DELETE", f"/games/{game_id}")


def fetch_state(game_id):
    status, data = api("GET", f"/games/{game_id}")
    if status != 200:
        return None
    return data


def settings_screen(stdscr):
    """Settings menu for auth token and server URL."""
    global AUTH_TOKEN, BASE_URL
    while True:
        stdscr.clear()
        stdscr.addstr(1, 2, "=== Settings ===", curses.color_pair(5) | curses.A_BOLD)
        token_display = AUTH_TOKEN if AUTH_TOKEN else "(not set)"
        url_display = BASE_URL if BASE_URL else "(not set)"
        options = [
            f"Set Auth Token  [{token_display}]",
            f"Set Server URL  [{url_display}]",
            "Back",
        ]
        selected = 0
        while True:
            for i, opt in enumerate(options):
                attr = curses.color_pair(4) | curses.A_BOLD if i == selected else curses.color_pair(3)
                stdscr.addstr(3 + i, 4, f"  {opt}  ", attr)
            stdscr.refresh()
            key = stdscr.getch()
            if key == curses.KEY_UP and selected > 0:
                selected -= 1
            elif key == curses.KEY_DOWN and selected < len(options) - 1:
                selected += 1
            elif key in (curses.KEY_ENTER, 10, 13):
                if selected == 0:
                    val = text_input(stdscr, 7, 2, "Auth Token: ", 40)
                    if val is not None:
                        AUTH_TOKEN = val
                    break
                elif selected == 1:
                    val = text_input(stdscr, 7, 2, "Server URL (e.g. http://host:5000): ", 50)
                    if val is not None:
                        BASE_URL = val.rstrip("/")
                    break
                else:
                    return


def menu_screen(stdscr):
    stdscr.clear()
    stdscr.addstr(1, 2, "=== COOPERATIVE CODENAMES ===", curses.color_pair(1) | curses.A_BOLD)
    options = ["Create New Game", "Join Game", "Settings", "Quit"]
    selected = 0

    while True:
        for i, opt in enumerate(options):
            attr = curses.color_pair(4) | curses.A_BOLD if i == selected else curses.color_pair(3)
            stdscr.addstr(3 + i, 4, f"  {opt}  ", attr)
        stdscr.addstr(8, 2, "Use ↑/↓ arrows and Enter to select", curses.color_pair(8) | curses.A_DIM)
        stdscr.refresh()

        key = stdscr.getch()
        if key == curses.KEY_UP and selected > 0:
            selected -= 1
        elif key == curses.KEY_DOWN and selected < len(options) - 1:
            selected += 1
        elif key in (curses.KEY_ENTER, 10, 13):
            if selected == 3:  # Quit
                return None
            if selected == 2:  # Settings
                settings_screen(stdscr)
                stdscr.clear()
                stdscr.addstr(1, 2, "=== COOPERATIVE CODENAMES ===", curses.color_pair(1) | curses.A_BOLD)
                continue

            if selected == 0:  # Create
                game_id = text_input(stdscr, 9, 2, "Game ID (blank for auto): ", 30)
                game_id = game_id if game_id else None
                status, data = api("POST", "/games", {"game_id": game_id} if game_id else {})
                if status != 201:
                    stdscr.addstr(11, 2, f"Error: {data.get('error', 'Unknown')}. Press any key.", curses.color_pair(2))
                    stdscr.refresh()
                    stdscr.getch()
                    stdscr.clear()
                    continue
                gid = data["id"]
                name = prompt_name(stdscr, 11)
                role = pick_role(stdscr, f"Game '{gid}' created. Join as:", {})
                status, resp = api("POST", f"/games/{gid}/join", {"name": name, "role": role})
                if status != 200:
                    stdscr.addstr(13, 2, f"Error: {resp.get('error', 'Unknown')}. Press any key.", curses.color_pair(2))
                    stdscr.refresh()
                    stdscr.getch()
                    stdscr.clear()
                    continue
                return (role, gid, name)

            else:  # Join / Resume
                game_id = text_input(stdscr, 9, 2, "Game ID: ", 30)
                if not game_id:
                    stdscr.clear()
                    continue
                state = fetch_state(game_id)
                if not state:
                    stdscr.addstr(11, 2, f"Game '{game_id}' not found! Press any key.", curses.color_pair(2))
                    stdscr.refresh()
                    stdscr.getch()
                    stdscr.clear()
                    continue
                name = prompt_name(stdscr, 11)
                players = state.get("players", {})
                # Check if resuming
                for r, n in players.items():
                    if n == name:
                        return (r, game_id, name)
                if len(players) >= 2:
                    stdscr.addstr(13, 2, "Game is full! Press any key.", curses.color_pair(2))
                    stdscr.refresh()
                    stdscr.getch()
                    stdscr.clear()
                    continue
                role = pick_role(stdscr, f"Joining game '{game_id}'. Play as:", players)
                status, resp = api("POST", f"/games/{game_id}/join", {"name": name, "role": role})
                if status != 200:
                    stdscr.addstr(13, 2, f"Error: {resp.get('error', 'Unknown')}. Press any key.", curses.color_pair(2))
                    stdscr.refresh()
                    stdscr.getch()
                    stdscr.clear()
                    continue
                return (role, game_id, name)


def spymaster_screen(stdscr, game_id, player_name):
    chat_scroll = 0
    log_scroll = 0
    while True:
        state = fetch_state(game_id)
        if not state:
            wait_for_quit(stdscr)
            return

        if state["status"] != "active":
            if "won" in state["status"]:
                show_end_screen(stdscr, state, game_id, "All team words found! You win!", curses.color_pair(1))
            else:
                show_end_screen(stdscr, state, game_id, f"Game over: {state['status']}", curses.color_pair(2))
            return

        SM_HINT = "'c' chat  '[' ']' chat scroll  '-' '=' log scroll  'q' quit"

        if state["turn"] == "spymaster":
            y = draw_game_screen(stdscr, state, "spymaster", game_id, chat_scroll=chat_scroll, log_scroll=log_scroll, player_name=player_name,
                                 status_line="YOUR TURN — press Enter to give a clue!", hint_line=SM_HINT)
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
                    chat_scroll = send_chat(stdscr, game_id, player_name, y + 1)
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
                new_state = fetch_state(game_id)
                if not new_state or new_state["status"] != "active":
                    break
                state = new_state
                y = draw_game_screen(stdscr, state, "spymaster", game_id, chat_scroll=chat_scroll, log_scroll=log_scroll, player_name=player_name,
                                     status_line="YOUR TURN — press Enter to give a clue!", hint_line=SM_HINT)
                stdscr.refresh()
            stdscr.timeout(-1)
            if not got_input:
                continue
            y += 1
            clue_word = text_input(stdscr, y, 2, "Clue word: ", 30, wrap_width=80, reject_chars="[]-=")
            if not clue_word:
                continue
            y += 1
            clue_num_str = text_input(stdscr, y, 2, "Number: ", 5, wrap_width=80)
            try:
                clue_num = int(clue_num_str)
            except (ValueError, TypeError):
                stdscr.addstr(y + 1, 2, "Invalid number. Press any key.", curses.color_pair(2))
                stdscr.refresh()
                stdscr.getch()
                continue
            status, resp = api("POST", f"/games/{game_id}/clue", {"word": clue_word, "number": clue_num})
            if status != 200:
                stdscr.addstr(y + 1, 2, f"{resp.get('error', 'Error')}. Press any key.", curses.color_pair(2))
                stdscr.refresh()
                stdscr.getch()
                continue
        else:
            wait_msg = f"Waiting for guesser... ({state['clue_guesses_left']} guess(es) left)"
            y = draw_game_screen(stdscr, state, "spymaster", game_id, chat_scroll=chat_scroll, log_scroll=log_scroll, player_name=player_name,
                                 status_line=wait_msg, hint_line=SM_HINT)
            stdscr.refresh()
            stdscr.timeout(1000)
            while True:
                k = stdscr.getch()
                if k == ord('q'):
                    stdscr.timeout(-1)
                    return
                if k in (ord('c'), ord('C')):
                    stdscr.timeout(-1)
                    chat_scroll = send_chat(stdscr, game_id, player_name, y + 2)
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
                new_state = fetch_state(game_id)
                if not new_state or new_state["turn"] == "spymaster" or new_state["status"] != "active":
                    break
                y = draw_game_screen(stdscr, new_state, "spymaster", game_id, chat_scroll=chat_scroll, log_scroll=log_scroll, player_name=player_name,
                                     status_line=f"Waiting for guesser... ({new_state['clue_guesses_left']} guess(es) left)", hint_line=SM_HINT)
                stdscr.refresh()
            stdscr.timeout(-1)


def guesser_screen(stdscr, game_id, player_name):
    cursor = 0
    chat_scroll = 0
    log_scroll = 0

    while True:
        state = fetch_state(game_id)
        if not state:
            wait_for_quit(stdscr)
            return

        if state["status"] != "active":
            if "won" in state["status"]:
                show_end_screen(stdscr, state, game_id, "All team words found! You win!", curses.color_pair(1))
            else:
                show_end_screen(stdscr, state, game_id, f"Game over: {state['status']}", curses.color_pair(2))
            return

        if state["turn"] != "guesser":
            GS_HINT = "'c' chat  '[' ']' chat scroll  '-' '=' log scroll  'q' quit"
            y = draw_game_screen(stdscr, state, "guesser", game_id, chat_scroll=chat_scroll, log_scroll=log_scroll, player_name=player_name,
                                 status_line="Waiting for spymaster to give a clue...", hint_line=GS_HINT)
            stdscr.refresh()
            stdscr.timeout(1000)
            while True:
                k = stdscr.getch()
                if k == ord('q'):
                    stdscr.timeout(-1)
                    return
                if k in (ord('c'), ord('C')):
                    stdscr.timeout(-1)
                    chat_scroll = send_chat(stdscr, game_id, player_name, y + 2)
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
                new_state = fetch_state(game_id)
                if not new_state or new_state["turn"] == "guesser" or new_state["status"] != "active":
                    break
                state = new_state
                y = draw_game_screen(stdscr, state, "guesser", game_id, chat_scroll=chat_scroll, log_scroll=log_scroll, player_name=player_name,
                                     status_line="Waiting for spymaster to give a clue...", hint_line=GS_HINT)
                stdscr.refresh()
            stdscr.timeout(-1)
            continue

        message = ""
        msg_color = curses.color_pair(3)

        while True:
            word = state["words"][cursor]
            GS_GUESS_HINT = "↑↓←→ move | Enter guess | P pass | C chat | [ ] chat | - = log | Q quit"
            y = draw_game_screen(stdscr, state, "guesser", game_id,
                                 cursor_idx=cursor, message=message, msg_color=msg_color, chat_scroll=chat_scroll, log_scroll=log_scroll, player_name=player_name,
                                 status_line=f"Selected: {word}", hint_line=GS_GUESS_HINT, status_color=curses.color_pair(4) | curses.A_BOLD)
            stdscr.refresh()

            key = stdscr.getch()
            message = ""

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
                status, resp = api("POST", f"/games/{game_id}/guess", {"word": word})
                state = fetch_state(game_id)
                if not state:
                    return
                if state["status"] != "active":
                    msg = "All team words found! You win!" if "won" in state["status"] else f"Game over: {state['status']}"
                    clr = curses.color_pair(1) if "won" in state["status"] else curses.color_pair(2)
                    show_end_screen(stdscr, state, game_id, msg, clr)
                    return
                result = resp.get("result", "")
                if result == "team":
                    message = f"'{word}' is a TEAM word!"
                    msg_color = curses.color_pair(1) | curses.A_BOLD
                    if state["turn"] != "guesser":
                        break
                elif result == "bystander":
                    break

            elif key in (ord('p'), ord('P')):
                api("POST", f"/games/{game_id}/pass")
                state = fetch_state(game_id)
                if not state or state["status"] != "active":
                    if state:
                        show_end_screen(stdscr, state, game_id, "No guess rounds left. Game over.", curses.color_pair(2))
                    return
                break

            elif key in (ord('q'), ord('Q')):
                return

            elif key in (ord('c'), ord('C')):
                chat_scroll = send_chat(stdscr, game_id, player_name, y + 1)
                state = fetch_state(game_id) or state

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
        if role == "spymaster":
            spymaster_screen(stdscr, game_id, name)
        else:
            guesser_screen(stdscr, game_id, name)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 client.py <host>:<port>")
        print("Example: python3 client.py localhost:5000")
        sys.exit(1)
    BASE_URL = f"http://{sys.argv[1]}"
    curses.wrapper(main)
