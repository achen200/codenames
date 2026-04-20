#!/usr/bin/env python3
"""Codenames CLI client."""

import sys
import argparse
import httpx

from config import CLIConfig, CONFIG_PATH, load_config, reset_config, save_config
from display import (
    render_board, print_status, print_clues,
    print_error, print_success, print_warning
)
from common.types import Role, Clue

##### HTTP #####

def make_client(config: CLIConfig) -> httpx.Client:
    headers = {}
    if config.token:
        headers["Authorization"] = f"Bearer {config.token}"
    return httpx.Client(base_url=f"http://{config.host}", headers=headers)

def api_call(client: httpx.Client, method: str, path: str, **kwargs) -> dict:
    try:
        response = client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        detail = e.response.json().get("detail", str(e))
        print_error(detail)
        sys.exit(1)
    except httpx.ConnectError:
        print_error(f"Could not connect to server. Is it running?")
        sys.exit(1)

##### Commands #####

def cmd_configure(args: argparse.Namespace) -> None:
    config = CLIConfig(host=args.host, token=args.token)
    save_config(config)
    print_success(f"Config saved to {CONFIG_PATH}")

def cmd_new(args: argparse.Namespace) -> None:
    config = load_config()
    with make_client(config) as client:
        data = api_call(client, "POST", "/games", json={"game_id": args.game_id})
    print_success(f"New game created! ID: {data['id']}")

def cmd_join(args: argparse.Namespace) -> None:
    config = load_config()
    with make_client(config) as client:
        data = api_call(client, "POST", f"/games/{args.game_id}/join", json={
            "name": args.name,
            "role": args.role,
        })
    if data["resumed"]:
        print_success(f"Welcome back! Resumed as {data['role']}")
    else:
        print_success(f"Joined game {args.game_id} as {data['role']}")

    config.game_id = args.game_id
    config.name = args.name
    config.role = data["role"]
    save_config(config)

def cmd_spymaster(args: argparse.Namespace) -> None:
    config = load_config()
    with make_client(config) as client:
        game = api_call(client, "GET", f"/games/{config.game_id}")
        render_board(game["board"], Role.SPYMASTER)
        print_status(game, Role.SPYMASTER)
        print_clues(game)

        if args.word and args.number is not None:
            api_call(client, "POST", f"/games/{config.game_id}/clue", json={
                "word": args.word,
                "number": args.number,
            })
            print_success(f"Clue given: {args.word} : {args.number}")
        else:
            if game["turn"] == Role.SPYMASTER:
                print_warning("Your turn! Give a clue: codenames spymaster <word> <number>")
            else:
                print_warning(f"Waiting for guesser ({game['guesses_remaining']} guess(es) remaining)")

def cmd_guesser(args: argparse.Namespace) -> None:
    config = load_config()
    with make_client(config) as client:
        game = api_call(client, "GET", f"/games/{config.game_id}")
        render_board(game["board"], Role.GUESSER)
        print_status(game, Role.GUESSER)

        if game["turn"] != Role.GUESSER:
            print_warning("Waiting for spymaster to give a clue.")
            return

        if args.word:
            if args.word.upper() == "PASS":
                api_call(client, "POST", f"/games/{config.game_id}/pass")
                print_success("Passed.")
            else:
                result = api_call(client, "POST", f"/games/{config.game_id}/guess", json={
                    "word": args.word,
                })
                print_success(f"'{args.word}' is a {result['category']} word.")
                if result["status"] is not None:
                    game = api_call(client, "GET", f"/games/{config.game_id}")
                    render_board(game["board"], Role.GUESSER)
                    print_status(game, Role.GUESSER)
        else:
            print_warning("To guess: codenames guesser <word>")
            print_warning("To pass:  codenames guesser pass")

def cmd_delete(args: argparse.Namespace) -> None:
    config = load_config()
    with make_client(config) as client:
        api_call(client, "DELETE", f"/games/{config.game_id}")
    print_success(f"Game {config.game_id} deleted.")
    config.game_id = None
    config.name = None
    config.role = None
    save_config(config)

def cmd_reset(args: argparse.Namespace) -> None:
    reset_config()
    print_success("Config cleared.")

##### Argument Parsing #####

def main():
    parser = argparse.ArgumentParser(description="Codenames CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    # configure
    p = sub.add_parser("configure", help="Set server host and token")
    p.add_argument("--host", required=True)
    p.add_argument("--token", default="")

    # new
    p = sub.add_parser("new", help="Create a new game")
    p.add_argument("game_id", nargs="?", default=None)

    # join
    p = sub.add_parser("join", help="Join a game")
    p.add_argument("game_id")
    p.add_argument("--name", required=True)
    p.add_argument("--role", required=True, choices=[r.value for r in Role])

    # spymaster
    p = sub.add_parser("spymaster", help="Spymaster view / give clue")
    p.add_argument("word", nargs="?", default=None)
    p.add_argument("number", nargs="?", type=int, default=None)

    # guesser
    p = sub.add_parser("guesser", help="Guesser view / make guess")
    p.add_argument("word", nargs="?", default=None)

    # delete
    sub.add_parser("delete", help="Delete current game")

    sub.add_parser("reset", help="Clear saved config")

    args = parser.parse_args()
    commands = {
        "configure": cmd_configure,
        "new": cmd_new,
        "join": cmd_join,
        "spymaster": cmd_spymaster,
        "guesser": cmd_guesser,
        "delete": cmd_delete,
        "reset": cmd_reset,
    }
    commands[args.command](args)

if __name__ == "__main__":
    main()