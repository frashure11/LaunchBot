# LaunchBot

A Discord bot that launches (and stops) shell scripts on your machine via
slash commands, restricted to one channel. Built for things like:

```
/run minecraft   -> runs /home/youruser/scripts/start-mc.sh
/stop minecraft  -> runs /home/youruser/scripts/stop-mc.sh (or kills the process if no stop script)
/list            -> shows configured scripts and whether they're currently running
```

## How it works

- `bot.py` — entry point; registers the `/run`, `/stop`, `/list` slash commands.
- `launchbot/config.py` — loads `.env` (secrets/IDs) and `commands.yaml` (script mapping), validates both.
- `launchbot/process_manager.py` — launches scripts as detached background processes, tracks PIDs so you can't double-launch the same thing, writes stdout/stderr to `logs/`.

Scripts are launched with `start_new_session=True`, so they keep running
even if the bot itself restarts — a bot crash or update won't kill your
Minecraft server. The tradeoff: if the bot restarts, it forgets the PID it
was tracking until you interact with that script again.

## Setup

1. **Create the Discord application & bot**
   - https://discord.com/developers/applications -> New Application
   - Bot tab -> Reset Token, copy it (you'll need it for `.env`)
   - Bot tab -> no privileged intents are required (slash commands don't need Message Content)
   - OAuth2 -> URL Generator -> scopes: `bot`, `applications.commands`
     -> bot permissions: `Send Messages`, `Use Slash Commands` (add `Embed Links` if you want to fancy up replies later)
   - Open the generated URL, invite it to your server

2. **Get the IDs you need** (enable Developer Mode in Discord: User Settings -> Advanced)
   - Right-click your server -> Copy Server ID -> `GUILD_ID`
   - Right-click the channel you want the bot restricted to -> Copy Channel ID -> `CHANNEL_ID`

3. **Install dependencies**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

4. **Configure**
   ```bash
   cp .env.example .env
   cp commands.example.yaml commands.yaml
   ```
   Fill in `.env` (token, guild ID, channel ID) and edit `commands.yaml` with
   real script paths **for whichever machine you run the bot on**. On this
   laptop that'll likely be fake/local test scripts; on the server it should
   point at `/home/youruser/scripts/...`.

   Make sure each `start`/`stop` script is executable: `chmod +x /path/to/script.sh`.

5. **Run it**
   ```bash
   python bot.py
   ```
   With `GUILD_ID` set, slash commands show up in that server within seconds.
   Without it, commands sync globally and can take up to an hour to appear.

## Testing locally before moving to the server

Since the real scripts live on the server, point `commands.yaml` at
throwaway test scripts while developing here, e.g.:

```yaml
scripts:
  test:
    description: Quick sanity check
    start: /bin/echo
    args: ["hello from LaunchBot"]
```

Then `/run test` in Discord and confirm you get a launch confirmation and a
log file under `logs/`.

## Deploying to the server

Run it under systemd so it survives reboots and restarts on crash. A
template unit file is at `launchbot.service.example` — copy it and fill in
your real username (same pattern as `.env.example`/`commands.example.yaml`):

```bash
sudo cp launchbot.service.example /etc/systemd/system/launchbot.service
sudo nano /etc/systemd/system/launchbot.service   # fix youruser -> your real username
sudo systemctl daemon-reload
sudo systemctl enable --now launchbot
journalctl -u launchbot -f   # tail logs
```

`enable` is what makes it come back up automatically after a reboot;
`--now` also starts it immediately. `Restart=on-failure` handles it crashing
mid-session.

## Security notes

- **Anyone who can post in the configured channel can launch/stop any
  configured script.** There's no per-user permission check by design (per
  your call) — keep that channel restricted to people you trust, since this
  is arbitrary-ish command execution on your server.
- `.env` and `commands.yaml` are gitignored — don't commit your token or
  real script paths/server layout.
- The bot only ever runs the exact paths listed in `commands.yaml` — it
  doesn't accept freeform shell input from Discord, so there's no shell
  injection surface from user-typed text (the `/run` argument is matched
  against configured script names/aliases only, never passed to a shell).
