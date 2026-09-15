# CS2 Media Controller

Windows-only single-file Python GUI app. Listens on `127.0.0.1:3000` for Counter-Strike 2 Game State Integration (GSI) POSTs and toggles media play/pause by synthesizing the `VK_MEDIA_PLAY_PAUSE` (0xB3) key via `ctypes.windll.user32.keybd_event`.

## Layout

- `cs2_media_control.py` — entire app: `tkinter` GUI + embedded `Flask` server in a daemon thread.
- `gamestate_integration_media.cfg` — CS2 GSI config. `uri` must stay `http://127.0.0.1:3000/` to match the Flask server.
- `build_exe.ps1` — build flow.
- `install_config.ps1` — installs the `.cfg` into CS2.
- `requirements.txt` — only `flask` + SMTC winrt pkgs (no `pyinstaller`; the build script installs it itself).
- `assets/` — bundled data files (GitHub mark for the footer link); baked into the EXE via `--add-data`, resolved at runtime with `resource_path()` (`sys._MEIPASS` under PyInstaller).
- `version.txt` — release source of truth (semver). Bumping it + pushing to `main` triggers CI, and once CI passes the release workflow runs: Windows EXE build, `v<version>` git tag, GitHub Release with the EXE attached. Pushes without a bump skip.
- `poc/` — throwaway POC scripts (each with a header docstring); not shipped in the EXE.
- `.github/workflows/` — `ci.yml` (runs the same pre-commit hooks as `make lint`), `release.yml` (version-gated build + release).

Tooling: `pre-commit` (ruff lint + ruff-format + mdformat + whitespace hygiene) via `.pre-commit-config.yaml`; ruff config in `pyproject.toml` (E501 off — formatter owns line width). Python pinned in `.python-version` (3.11.9); dev-only dep (`pre-commit`) in `requirements-dev.txt`. No tests, type-checker exist. Don't invent them.

## Setup / run

- Dev: `pip install -r requirements.txt && python cs2_media_control.py`.
- Build EXE: run `build_exe.ps1` (PowerShell). It creates `venv/`, installs `flask` + `pyinstaller`, runs `pyinstaller --noconsole --onefile --name CS2MediaControl --collect-submodules winrt --add-data "assets;assets" cs2_media_control.py` (`--collect-submodules` is required: the `winrt` shims are PEP-420 namespaces the static graph misses; verified via `pyi-archive_viewer` that `PYZ.pyz` contains them), copies `dist\CS2MediaControl.exe` to repo root, then deletes `build/`, `dist/`, and the `.spec` file. The root `CS2MediaControl.exe` is gitignored; the one currently committed is stale.
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
- **The resume path is delayed by `RESUME_DELAY_MS` (2000ms), the pause path is instant.** When the player dies or the round ends (`should_play` → True), the key press and the auto-focus switch both fire 2s later via a `root.after()` job. The state machine updates `media_is_playing` immediately so subsequent payloads see a consistent state. A new transition (e.g., respawn within the 2s window) calls `after_cancel` on the pending job and pauses immediately. Toggling the `is_enabled` checkbox off also cancels any pending resume. The label shows "RESUMING IN 2s" (orange) during the delay, then "PLAYING" (green).
- `is_enabled` (`tk.BooleanVar`) gates GUI updates and logging only — it does **not** stop the Flask server. Webhook traffic still arrives and `process_payload` still runs.

## Editing tips

- Keep the Flask `uri` in `gamestate_integration_media.cfg` and `PORT`/`HOST` in `cs2_media_control.py` in sync; both are `127.0.0.1:3000`.
- `build_exe.ps1` expects to be run from the repo root (uses relative `venv\`, `dist\`, etc.).
- The committed `CS2MediaControl.exe` should not be edited by hand — rebuild via the script.
- Use `.venv\Scripts\python.exe` (not the system Python) for any local check — the project venv is at `.venv/`.

## Auto-focus feature (added)

GUI exposes a second checkbox ("Auto-focus between CS2 and the selected media window") and a custom `WindowPicker` dropdown. When enabled, on every media-state transition the app also calls `SetForegroundWindow`:

- `should_play == True` (dead / round over) → focus the selected media window.
- `should_play == False` (alive) → focus CS2 (matched by window title containing `"Counter-Strike"`).

**Selection identity is the executable path, not the hwnd or title.** Rationale: YouTube/browser tabs change their window title on every video, which would break a title-keyed identity, and hwnds are reused when an app restarts. Each window is stored as `(hwnd, title, exe_path, photoimage)`. On `refresh()` the picker keeps the same hwnd if it's still in the list, otherwise falls back to the first enumerated window of the same exe (topmost in z-order), otherwise marks the selection **stale** — the picker button shows `(stale: <exe> closed - pick again)` and `_apply_focus` skips the focus call.

A periodic 5-second `refresh()` runs while auto-focus is enabled, so the stale state surfaces within a few seconds of the user closing the media app. `GetForegroundWindow` is called with the `AttachThreadInput` trick to bypass the Windows foreground lock; this still fails on some systems without admin — logged, not raised.

## Icon extraction gotcha

`hicon_to_photoimage` uses `CreateDIBSection` (a real 32bpp DIB) rather than `CreateCompatibleBitmap` (a DDB). `DrawIconEx` + `GetDIBits` on a DDB returns zeroed alpha, which composites to solid white and makes icons appear blank. The DIB section is read directly via `ctypes.c_ubyte * nbytes.from_address(bits_ptr)` and written to the `tk.PhotoImage` with one `img.put(...)` per pixel (the brace-row `data=` string format is rejected by this Tk build).

## Multi-source media control (SMTC)

Optional path toggled by the `Media Sources` checkbox (nested in `Controls`, above `Auto-Focus`). When on, pause/resume goes through per-session `TryPauseAsync`/`TryPlayAsync` instead of `press_media_key` (never both). Selection lives in `MediaSourcePicker.checked`, keyed by AUMID (opt-in: new sources start unchecked); pause snapshots `PLAYING`-among-checked into `_paused_snapshot`, the delayed resume job carries `(use_smtc, snapshot)` and replays only that set. Stale AUMIDs yield `GONE (no live session)` log lines, per-source `ERR`s are logged not raised. `winrt` import is lazy (`_SMTC_AVAILABLE` flag) so the app still runs legacy without the pkgs. SMTC status reads lag ~2s behind the `Try*` bool -- never assert on an immediate re-read. Empty checked set falls back to the media key; disabling multi cancels a pending resume; enabling syncs `media_is_playing` from live checked sessions when determinable.
