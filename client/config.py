from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from common.types import Role

CONFIG_PATH = Path.home() / ".config" / "codenames" / "config.json"

@dataclass
class CLIConfig:
    host: str
    token: str
    game_id: Optional[str] = None
    name: Optional[str] = None
    role: Optional[Role] = None

    def to_dict(self) -> dict:
        return {
            "host": self.host,
            "token": self.token,
            "game_id": self.game_id,
            "name": self.name,
            "role": self.role.value if self.role else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> CLIConfig:
        role = Role(data["role"]) if data.get("role") else None
        return cls(
            host=data["host"],
            token=data["token"],
            game_id=data.get("game_id"),
            name=data.get("name"),
            role=role,
        )

def load_config() -> CLIConfig:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            "No config found. Run: codenames configure --host <host> --token <token>"
        )
    data = json.loads(CONFIG_PATH.read_text())
    return CLIConfig.from_dict(data)

def save_config(config: CLIConfig) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config.to_dict(), indent=2))

def reset_config() -> None:
    if CONFIG_PATH.exists():
        CONFIG_PATH.unlink()