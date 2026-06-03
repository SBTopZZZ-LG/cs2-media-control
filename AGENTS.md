# CS2 Media Controller

Windows-only single-file Python GUI app. Listens on `127.0.0.1:3000` for Counter-Strike 2 Game State Integration (GSI) POSTs and toggles media play/pause by synthesizing the `VK_MEDIA_PLAY_PAUSE` (0xB3) key via `ctypes.windll.user32.keybd_event`.

## Layout

- `cs2_media_control.py` — entire app: `tkinter` GUI + embedded `Flask` server in a daemon thread.
- `gamestate_integration_media.cfg` — CS2 GSI config. `uri` must stay `http://127.0.0.1:3000/` to match the Flask server.
- `build_exe.ps1` — build flow.
- `install_config.ps1` — installs the `.cfg` into CS2.
- `requirements.txt` — only `flask` (no `pyinstaller`; the build script installs it itself).

No tests, linter, formatter, type-checker, CI, or pre-commit hooks exist. Don't invent them.

## Setup / run

- Dev: `pip install -r requirements.txt && python cs2_media_control.py`.
- Build EXE: run `build_exe.ps1` (PowerShell). It creates `venv/`, installs `flask` + `pyinstaller`, runs `pyinstaller --noconsole --onefile --name CS2MediaControl cs2_media_control.py`, copies `dist\CS2MediaControl.exe` to repo root, then deletes `build/`, `dist/`, and the `.spec` file. The root `CS2MediaControl.exe` is gitignored; the one currently committed is stale.
- Install GSI config: run `install_config.ps1`. It reads the install path from `HKLM:\SOFTWARE\WOW6432Node\Valve\cs2` and copies the `.cfg` to `<cs2>\game\csgo\cfg`. Fails without admin or if CS2 isn't installed at the standard registry path. CS2 must be restarted after install.

## Platform constraints

- Windows only. `ctypes.windll.user32` is required for media key simulation. There is no fallback for macOS/Linux.
- The app is purely user-space — no installer, no service. The user runs the EXE or script manually.
- Per `README.md`, the EXE/script sometimes needs to run as Administrator for the synthesized media key to reach the player while CS2 has focus.
- Flask binds to `127.0.0.1` only; Windows Firewall is not a real concern.

## Architecture notes

- One process. GUI on main thread, Flask server on a daemon thread started in `CS2MediaApp.start_server`. `werkzeug` logging is silenced (`logging.ERROR`).
- State machine in `process_payload`:
  - `media_is_playing` — last assumed media state; drives whether a key press is sent.
  - `current_score` (sum of CT+T scores) — detects a new round; resets `has_died_this_round`.
  - `has_died_this_round` — sticky "dead this round" flag. Once true, the app keeps media playing through spectating-of-others states for the rest of the round.
  - Spectating detection: `provider.steamid != player.steamid`. Local account is `provider`.
  - Round-phase handling: `over` → resume; `freezetime` (alive) → pause; `live` → driven by death/spectate. There is an explicit `should_play = True` override for `round_phase == 'over'` after the live branch — don't remove it.
- Key press only fires on a `should_play != media_is_playing` transition. Press always goes through `press_media_key`; the app has no way to query Spotify/YouTube, so initial state assumes "playing". If the player and app get out of sync, the user must press Play/Pause once to realign (documented in README).
- `is_enabled` (`tk.BooleanVar`) gates GUI updates and logging only — it does **not** stop the Flask server. Webhook traffic still arrives and `process_payload` still runs.

## Editing tips

- Keep the Flask `uri` in `gamestate_integration_media.cfg` and `PORT`/`HOST` in `cs2_media_control.py` in sync; both are `127.0.0.1:3000`.
- `build_exe.ps1` expects to be run from the repo root (uses relative `venv\`, `dist\`, etc.).
- The committed `CS2MediaControl.exe` should not be edited by hand — rebuild via the script.
