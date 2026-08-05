"""Loads and validates bot configuration from .env and commands.yaml."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv


@dataclass
class ScriptEntry:
    name: str
    description: str
    start: str
    stop: str | None = None
    aliases: list[str] = field(default_factory=list)
    args: list[str] = field(default_factory=list)
    cwd: str | None = None


@dataclass
class BotConfig:
    token: str
    guild_id: int | None
    channel_id: int
    log_dir: Path
    scripts: dict[str, ScriptEntry]

    def resolve(self, key: str) -> ScriptEntry | None:
        """Look up a script by its canonical name or one of its aliases (case-insensitive)."""
        key = key.lower()
        if key in self.scripts:
            return self.scripts[key]
        for entry in self.scripts.values():
            if key in entry.aliases:
                return entry
        return None


def load_config(env_path: str = ".env", commands_path: str = "commands.yaml") -> BotConfig:
    load_dotenv(env_path)

    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN is not set (check your .env file)")

    channel_id_raw = os.environ.get("CHANNEL_ID")
    if not channel_id_raw:
        raise RuntimeError("CHANNEL_ID is not set (check your .env file)")
    channel_id = int(channel_id_raw)

    guild_id_raw = os.environ.get("GUILD_ID")
    guild_id = int(guild_id_raw) if guild_id_raw else None

    log_dir = Path(os.environ.get("LOG_DIR", "./logs"))

    commands_file = Path(commands_path)
    if not commands_file.exists():
        raise RuntimeError(
            f"{commands_path} not found. Copy commands.example.yaml to {commands_path} "
            "and fill in your real script paths for this machine."
        )

    with commands_file.open() as f:
        raw = yaml.safe_load(f) or {}

    scripts: dict[str, ScriptEntry] = {}
    for name, spec in (raw.get("scripts") or {}).items():
        if not spec or "start" not in spec:
            raise RuntimeError(f"scripts.{name} is missing a required 'start' path in {commands_path}")
        lname = name.lower()
        scripts[lname] = ScriptEntry(
            name=lname,
            description=spec.get("description", name),
            start=spec["start"],
            stop=spec.get("stop"),
            aliases=[a.lower() for a in spec.get("aliases", [])],
            args=[str(a) for a in spec.get("args", [])],
            cwd=spec.get("cwd"),
        )

    if not scripts:
        raise RuntimeError(f"No scripts defined under 'scripts:' in {commands_path}")

    return BotConfig(
        token=token,
        guild_id=guild_id,
        channel_id=channel_id,
        log_dir=log_dir,
        scripts=scripts,
    )
