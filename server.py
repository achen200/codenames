#!/usr/bin/env python3
"""Codenames HTTP server — exposes game engine over REST API on port 5000."""

import json
import sys
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from codenames import (
    new_game, load_game, save_game, team_words_remaining,
    end_guesser_turn, GameNotFound, BOARD_SIZE, GAMES_DIR, delete_game,
)

CLIENT_PATH = Path(__file__).parent / "client.py"
SERVER_HOST = ""  # set at startup
AUTH_TOKEN = ""   # set at startup


class GameHandler(BaseHTTPRequestHandler):
    def _json_response(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _text_response(self, text, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(text.encode())

    def _check_auth(self):
        """Check Authorization header. Returns True if valid."""
        if not AUTH_TOKEN:
            return True
        token = self.headers.get("Authorization", "").replace("Bearer ", "")
        if token == AUTH_TOKEN:
            return True
        self._json_response({"error": "Unauthorized"}, 401)
        return False

    def _get_query_param(self, key):
        """Extract a query parameter from the URL."""
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        vals = params.get(key, [])
        return vals[0] if vals else None

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def do_GET(self):
        from urllib.parse import urlparse
        path_only = urlparse(self.path).path
        parts = path_only.strip("/").split("/")

        # GET /?token=XXX — install script (token via query param)
        if path_only == "/" or parts == [""]:
            if AUTH_TOKEN:
                token = self._get_query_param("token")
                if token != AUTH_TOKEN:
                    return self._text_response("echo 'Unauthorized. Usage: curl <host>:<port>?token=<token> | bash'\nexit 1\n", 401)
            install_script = f"""#!/bin/bash
set -e
echo "Installing Codenames CLI..."
INSTALL_DIR="$HOME/.local/bin"
mkdir -p "$INSTALL_DIR"
curl -sS -H "Authorization: Bearer {AUTH_TOKEN}" http://{SERVER_HOST}/client -o "$INSTALL_DIR/codenames"
chmod +x "$INSTALL_DIR/codenames"
# Ensure ~/.local/bin is in PATH
if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
    SHELL_NAME=$(basename "$SHELL")
    if [ "$SHELL_NAME" = "zsh" ]; then
        RC="$HOME/.zshrc"
    else
        RC="$HOME/.bashrc"
    fi
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$RC"
    export PATH="$INSTALL_DIR:$PATH"
    echo "Added $INSTALL_DIR to PATH (restart shell or run: source $RC)"
fi
echo "Done! Run: codenames"
"""
            return self._text_response(install_script)

        # GET /client — serve the client script with server address + token baked in
        if parts == ["client"]:
            if not self._check_auth():
                return
            client_src = CLIENT_PATH.read_text()
            patched = client_src.replace(
                'BASE_URL = ""',
                f'BASE_URL = "http://{SERVER_HOST}"',
            )
            patched = patched.replace(
                'AUTH_TOKEN = ""',
                f'AUTH_TOKEN = "{AUTH_TOKEN}"',
            )
            patched = patched.replace(
                """if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 client.py <host>:<port>")
        print("Example: python3 client.py localhost:5000")
        sys.exit(1)
    BASE_URL = f"http://{sys.argv[1]}"
    curses.wrapper(main)""",
                """if __name__ == "__main__":
    if len(sys.argv) >= 2:
        BASE_URL = f"http://{sys.argv[1]}"
    curses.wrapper(main)""",
            )
            return self._text_response(patched)

        # All remaining GET endpoints require auth
        if not self._check_auth():
            return

        # GET /games — list all games
        if parts == ["games"]:
            if not GAMES_DIR.exists():
                return self._json_response([])
            games = []
            for f in sorted(GAMES_DIR.glob("*.json")):
                s = json.loads(f.read_text())
                games.append({
                    "id": s["id"], "status": s["status"],
                    "team_left": len(team_words_remaining(s)),
                    "guesses_left": s["guesses_left"],
                    "players": s.get("players", {}),
                })
            return self._json_response(games)

        # GET /games/<id> — get game state
        if len(parts) == 2 and parts[0] == "games":
            try:
                state = load_game(parts[1])
            except GameNotFound:
                return self._json_response({"error": "Game not found"}, 404)
            return self._json_response(state)

        self._json_response({"error": "Not found"}, 404)

    def do_POST(self):
        if not self._check_auth():
            return
        parts = self.path.strip("/").split("/")
        body = self._read_body()

        # POST /games — create new game
        if parts == ["games"]:
            custom_id = body.get("game_id")
            if custom_id and (GAMES_DIR / f"{custom_id}.json").exists():
                return self._json_response({"error": "Game already exists"}, 409)
            state = new_game(custom_id)
            return self._json_response(state, 201)

        # POST /games/<id>/join — join a game
        if len(parts) == 3 and parts[0] == "games" and parts[2] == "join":
            try:
                state = load_game(parts[1])
            except GameNotFound:
                return self._json_response({"error": "Game not found"}, 404)
            name = body.get("name", "").strip()
            role = body.get("role", "").strip()
            if not name:
                return self._json_response({"error": "Name required"}, 400)
            players = state.get("players", {})
            # Check if resuming
            for r, n in players.items():
                if n == name:
                    return self._json_response({"role": r, "resumed": True})
            if len(players) >= 2:
                return self._json_response({"error": "Game is full"}, 409)
            if role not in ("spymaster", "guesser"):
                return self._json_response({"error": "Role must be 'spymaster' or 'guesser'"}, 400)
            if role in players:
                return self._json_response({"error": f"{role} already taken by {players[role]}"}, 409)
            state.setdefault("roles_taken", []).append(role)
            state.setdefault("players", {})[role] = name
            save_game(state)
            return self._json_response({"role": role, "resumed": False})

        # POST /games/<id>/clue — spymaster gives a clue
        if len(parts) == 3 and parts[0] == "games" and parts[2] == "clue":
            try:
                state = load_game(parts[1])
            except GameNotFound:
                return self._json_response({"error": "Game not found"}, 404)
            if state["status"] != "active":
                return self._json_response({"error": f"Game over: {state['status']}"}, 400)
            if state["turn"] != "spymaster":
                return self._json_response({"error": "Not spymaster's turn"}, 400)
            word = body.get("word", "").strip().upper()
            number = body.get("number")
            if not word or number is None:
                return self._json_response({"error": "word and number required"}, 400)
            if ' ' in word:
                return self._json_response({"error": "Clue must be a single word"}, 400)
            try:
                number = int(number)
                if number < 0:
                    raise ValueError
            except (ValueError, TypeError):
                return self._json_response({"error": "Number must be a non-negative integer"}, 400)
            visible = [state["words"][i].upper() for i in range(BOARD_SIZE) if i not in state["revealed"]]
            if word in visible:
                return self._json_response({"error": f"'{word}' is on the board"}, 400)
            for v in visible:
                if word in v.split() or v in word.split():
                    return self._json_response({"error": f"'{word}' overlaps with '{v}'"}, 400)
            spy_name = state.get("players", {}).get("spymaster", "Spymaster")
            state.setdefault("log", []).append(f"[CLUE] {spy_name}: {word} : {number}")
            state["clues"].append({"word": word, "number": number})
            state["turn"] = "guesser"
            state["clue_guesses_left"] = number + 1
            save_game(state)
            return self._json_response({"ok": True, "clue": word, "number": number})

        # POST /games/<id>/guess — guesser guesses a word
        if len(parts) == 3 and parts[0] == "games" and parts[2] == "guess":
            try:
                state = load_game(parts[1])
            except GameNotFound:
                return self._json_response({"error": "Game not found"}, 404)
            if state["status"] != "active":
                return self._json_response({"error": f"Game over: {state['status']}"}, 400)
            if state["turn"] != "guesser":
                return self._json_response({"error": "Not guesser's turn"}, 400)
            guess = body.get("word", "").strip().upper()
            if not guess:
                return self._json_response({"error": "word required"}, 400)
            idx = None
            for i, w in enumerate(state["words"]):
                if w.upper() == guess:
                    idx = i
                    break
            if idx is None:
                return self._json_response({"error": f"'{guess}' not on the board"}, 400)
            if idx in state["revealed"]:
                return self._json_response({"error": "Already revealed"}, 400)

            guesser_name = state.get("players", {}).get("guesser", "Guesser")
            state["revealed"].append(idx)
            role = state["key"][str(idx)]

            if role == "ASSASSIN":
                state.setdefault("log", []).append(f"[GUESS] {guesser_name}: {guess} → ASSASSIN!")
                state["status"] = "lost — assassin"
                save_game(state)
                return self._json_response({"result": "assassin", "word": guess})

            if role == "TEAM":
                state.setdefault("log", []).append(f"[GUESS] {guesser_name}: {guess} → TEAM ✓")
                if not team_words_remaining(state):
                    state["status"] = "won"
                    save_game(state)
                    return self._json_response({"result": "team", "word": guess, "won": True})
                state["clue_guesses_left"] -= 1
                if state["clue_guesses_left"] <= 0:
                    state.setdefault("log", []).append("[TURN] Round over — no guesses left")
                    end_guesser_turn(state)
                save_game(state)
                return self._json_response({"result": "team", "word": guess, "won": False, "status": state["status"]})

            # Bystander
            state.setdefault("log", []).append(f"[GUESS] {guesser_name}: {guess} → bystander")
            state.setdefault("log", []).append("[TURN] Bystander hit — turn ends")
            end_guesser_turn(state)
            save_game(state)
            return self._json_response({"result": "bystander", "word": guess, "status": state["status"]})

        # POST /games/<id>/pass — guesser passes
        if len(parts) == 3 and parts[0] == "games" and parts[2] == "pass":
            try:
                state = load_game(parts[1])
            except GameNotFound:
                return self._json_response({"error": "Game not found"}, 404)
            if state["status"] != "active":
                return self._json_response({"error": f"Game over: {state['status']}"}, 400)
            if state["turn"] != "guesser":
                return self._json_response({"error": "Not guesser's turn"}, 400)
            guesser_name = state.get("players", {}).get("guesser", "Guesser")
            state.setdefault("log", []).append(f"[PASS] {guesser_name} passed")
            end_guesser_turn(state)
            save_game(state)
            return self._json_response({"ok": True, "status": state["status"]})

        # POST /games/<id>/chat — send a chat message
        if len(parts) == 3 and parts[0] == "games" and parts[2] == "chat":
            try:
                state = load_game(parts[1])
            except GameNotFound:
                return self._json_response({"error": "Game not found"}, 404)
            name = body.get("name", "").strip()
            msg = body.get("msg", "").strip()
            if not name or not msg:
                return self._json_response({"error": "name and msg required"}, 400)
            state.setdefault("chat", []).append({"name": name, "msg": msg})
            save_game(state)
            return self._json_response({"ok": True})

        self._json_response({"error": "Not found"}, 404)

    def do_DELETE(self):
        if not self._check_auth():
            return
        parts = self.path.strip("/").split("/")
        if len(parts) == 2 and parts[0] == "games":
            try:
                load_game(parts[1])
            except GameNotFound:
                return self._json_response({"error": "Game not found"}, 404)
            delete_game(parts[1])
            return self._json_response({"ok": True})
        self._json_response({"error": "Not found"}, 404)

    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {format % args}")


def main():
    global SERVER_HOST, AUTH_TOKEN
    import argparse
    parser = argparse.ArgumentParser(description="Codenames server")
    parser.add_argument("port", nargs="?", type=int, default=5000)
    parser.add_argument("--host", default=None, help="Public hostname/IP")
    parser.add_argument("--token", default=None, help="Auth token (auto-generated if not set)")
    parser.add_argument("--no-auth", action="store_true", help="Disable auth")
    args = parser.parse_args()

    host = args.host
    if not host:
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            host = s.getsockname()[0]
            s.close()
        except Exception:
            host = "localhost"

    if args.no_auth:
        AUTH_TOKEN = ""
    else:
        import secrets
        AUTH_TOKEN = args.token or secrets.token_urlsafe(16)

    SERVER_HOST = f"{host}:{args.port}"
    server = HTTPServer(("0.0.0.0", args.port), GameHandler)
    print(f"Codenames server running on port {args.port}")
    if AUTH_TOKEN:
        print(f"Auth token: {AUTH_TOKEN}")
        print(f"Players install with: curl '{SERVER_HOST}?token={AUTH_TOKEN}' | bash")
    else:
        print(f"Players install with: curl {SERVER_HOST} | bash")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
