"""LaunchBot: a Discord bot that runs shell scripts in response to slash
commands, restricted to a single channel.

Usage: /run minecraft   -> launches the configured `start` script
       /stop minecraft  -> runs the configured `stop` script, or SIGTERMs
                            the tracked process if no `stop` is configured
       /list             -> shows configured scripts and whether they're running

Configuration lives in .env (secrets/IDs) and commands.yaml (script mapping).
See README.md for setup.
"""

from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands

from launchbot.config import load_config
from launchbot.process_manager import ProcessManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("launchbot")

config = load_config()
process_manager = ProcessManager(config.log_dir)

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


def _wrong_channel_message() -> str:
    return f"This bot only works in <#{config.channel_id}>."


async def script_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    current = current.lower()
    choices = []
    for entry in config.scripts.values():
        haystack = [entry.name, *entry.aliases]
        if any(current in h for h in haystack):
            choices.append(app_commands.Choice(name=f"{entry.name} — {entry.description}", value=entry.name))
    return choices[:25]


@tree.command(name="run", description="Launch a script")
@app_commands.describe(script="Which script to run")
@app_commands.autocomplete(script=script_autocomplete)
async def run_command(interaction: discord.Interaction, script: str) -> None:
    if interaction.channel_id != config.channel_id:
        await interaction.response.send_message(_wrong_channel_message(), ephemeral=True)
        return

    entry = config.resolve(script)
    if entry is None:
        await interaction.response.send_message(f"Unknown script `{script}`.", ephemeral=True)
        return

    if process_manager.is_running(entry.name):
        running = process_manager.status(entry.name)
        await interaction.response.send_message(
            f"⚠️ **{entry.name}** is already running (PID {running.pid}).", ephemeral=True
        )
        return

    await interaction.response.defer(thinking=True)
    try:
        command = [entry.start, *entry.args]
        running = await asyncio.to_thread(process_manager.launch, entry.name, command, entry.cwd)
    except Exception as exc:
        logger.exception("Failed to launch %s", entry.name)
        await interaction.followup.send(f"❌ Failed to launch **{entry.name}**: {exc}")
        return

    await interaction.followup.send(
        f"🚀 Launched **{entry.name}** (PID {running.pid}) — requested by {interaction.user.mention}\n"
        f"Log: `{running.log_path}`"
    )


@tree.command(name="stop", description="Stop a running script")
@app_commands.describe(script="Which script to stop")
@app_commands.autocomplete(script=script_autocomplete)
async def stop_command(interaction: discord.Interaction, script: str) -> None:
    if interaction.channel_id != config.channel_id:
        await interaction.response.send_message(_wrong_channel_message(), ephemeral=True)
        return

    entry = config.resolve(script)
    if entry is None:
        await interaction.response.send_message(f"Unknown script `{script}`.", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)

    if entry.stop:
        try:
            running = await asyncio.to_thread(
                process_manager.launch, f"{entry.name}-stop", [entry.stop], entry.cwd
            )
        except Exception as exc:
            logger.exception("Failed to run stop script for %s", entry.name)
            await interaction.followup.send(f"❌ Failed to stop **{entry.name}**: {exc}")
            return
        await interaction.followup.send(
            f"🛑 Ran stop script for **{entry.name}** (PID {running.pid}) — requested by {interaction.user.mention}"
        )
        return

    stopped = await asyncio.to_thread(process_manager.stop, entry.name)
    if stopped:
        await interaction.followup.send(f"🛑 Stopped **{entry.name}** — requested by {interaction.user.mention}")
    else:
        await interaction.followup.send(f"**{entry.name}** doesn't look like it's running.")


@tree.command(name="list", description="List available scripts and their status")
async def list_command(interaction: discord.Interaction) -> None:
    if interaction.channel_id != config.channel_id:
        await interaction.response.send_message(_wrong_channel_message(), ephemeral=True)
        return

    lines = []
    for entry in config.scripts.values():
        status = "🟢 running" if process_manager.is_running(entry.name) else "⚪ stopped"
        alias_str = f" (aliases: {', '.join(entry.aliases)})" if entry.aliases else ""
        lines.append(f"**{entry.name}**{alias_str} — {entry.description} — {status}")

    await interaction.response.send_message("\n".join(lines) or "No scripts configured.")


@client.event
async def on_ready() -> None:
    if config.guild_id:
        guild = discord.Object(id=config.guild_id)
        tree.copy_global_to(guild=guild)
        await tree.sync(guild=guild)
        logger.info("Synced commands to guild %s (instant)", config.guild_id)
    else:
        await tree.sync()
        logger.info("Synced global commands (can take up to an hour to propagate)")

    logger.info("Logged in as %s (id=%s)", client.user, client.user.id)


def main() -> None:
    client.run(config.token)


if __name__ == "__main__":
    main()
