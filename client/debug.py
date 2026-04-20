# debug.py
from config import load_config
from tui import CodenamesClient

config = load_config()
api = CodenamesClient(config)
print(api.get_game())