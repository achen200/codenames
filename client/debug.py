# debug.py
from client.config import load_config
from client.tui import CodenamesClient

config = load_config()
api = CodenamesClient(config)
print(api.get_game())