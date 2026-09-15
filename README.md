# CS2 Media Controller

Automatically pauses your music while you're alive in Counter-Strike 2 and brings it back when you die or the round ends. It's a small Windows GUI app that listens for CS2 Game State Integration (GSI) events on `127.0.0.1:3000` and toggles playback for you.

## Behavior

- When you spawn into a live round, your media pauses right away.
- When you die, end up spectating, or the round finishes, it resumes after about 2 seconds. If you respawn inside that window, the pending resume is cancelled and it pauses instead.
- Freezetime while you're alive counts as paused. During the delay the status label reads `RESUMING IN 2s` in orange, then flips to `PLAYING` or `PAUSED`.
- It only acts when the state actually changes, using either the media key or per-app SMTC control (see Controls).

## Requirements

- Windows. The app drives the `user32` media key and focus APIs, so there's no macOS/Linux support.
- Counter-Strike 2, restarted once after you install the GSI config below.
- Something playing audio (Spotify, a browser tab, etc.).
- You may need to run as admin. Windows can block synthetic media keys and window focus changes while CS2 has focus.

## Quick start

1. Build the app: right-click `build_exe.ps1` and choose Run with PowerShell. That gives you `CS2MediaControl.exe`. If you'd rather run from source: `pip install -r requirements.txt && python cs2_media_control.py`.
1. Install the GSI config: right-click `install_config.ps1` and choose Run with PowerShell. It copies `gamestate_integration_media.cfg` into `<cs2>\game\csgo\cfg`. Restart CS2 afterwards.
1. Start your music, launch the app (or EXE), then launch CS2.
1. Sync up once. The app can't ask your player whether it's playing, so it assumes media starts out **playing**. If it shows PLAYING while you're actually paused, just tap Play/Pause once and you're aligned.

## Controls

- **Enable Auto-Resume/Pause.** The master switch. Turning it off greys out the boxes below and cancels any pending resume. GSI events still arrive in the background, but the GUI stops reacting to them.
- **Media Sources: Control multiple media sources.** Pauses and resumes each checked app individually through Windows SMTC (`TryPause`/`TryPlayAsync`) instead of the single media-key toggle. Sources are opt-in by AUMID and new ones start unchecked. Pausing snapshots whatever is PLAYING among your checked sources, and the delayed resume replays that set. With nothing checked, or without the `winrt` packages installed, it falls back to the media key and says so in the log.
- **Auto-Focus: Auto-focus between CS2 and the selected media window.** Jumps focus back to CS2 when you go alive and over to your media window when you die. Pick the window from the dropdown. It tracks the app by exe path, so it survives tab switches, title changes, and restarts, and flags the pick as `stale` if you close the app. This one can also need admin rights (`SetForegroundWindow` gets blocked otherwise, which is logged rather than raised).

## Troubleshooting

- **Pause/play feels inverted**: tap Play/Pause once to resync. The app assumes "playing" at startup.
- **Keys or focus do nothing in-game**: try running as Administrator.
- **No game data coming in**: confirm the `.cfg` sits in `<cs2>\game\csgo\cfg`, that you restarted CS2 after installing it, and that the app log shows `Server started on 127.0.0.1:3000`.
- **Multi-source won't engage**: run `pip install -r requirements.txt` for the `winrt` packages, and make sure your sources are actually checked.
- **Media window shows stale**: just re-pick it in the dropdown after closing or restarting that app.

## Dev notes

- Everything lives in `cs2_media_control.py`: a tkinter GUI with the Flask server on a daemon thread.
- Keep `gamestate_integration_media.cfg` (`uri http://127.0.0.1:3000/`) in sync with `HOST`/`PORT` in the script.
- Rebuild the EXE with `build_exe.ps1` from the repo root. Don't hand-edit the built binary.
- `poc/` holds throwaway experiments (like the SMTC multi-pause prototype). They aren't part of the app.
- Dev setup: Python 3.11.9 (pinned in `.python-version`), `pip install -r requirements-dev.txt`, hooks run automatically on commit via `pre-commit`.

## Releases

Each release ships a `CS2MediaControl-v<version>.zip` as a GitHub Release download, containing the built EXE, `install_config.ps1`, and the GSI `.cfg` (everything the tool needs to run). The version lives in `version.txt` at the repo root, and CI handles everything else: pushing a bumped `version.txt` to `main` runs CI, and once that passes builds the EXE on Windows, bundles the ZIP, creates the `v<version>` git tag, and publishes the release with a commit log. Pushing without a version bump, or with failing CI, skips the release.

### Antivirus false positives

The release EXE is an unsigned PyInstaller onefile build. That packaging self-extracts to a temp folder and launches from there, which heuristic engines dislike: expect generic or ML-based flags such as `Trojan:Win32/Wacatac.B!ml` from Defender, or a handful of similar VirusTotal verdicts. Those fire on the packager's bootloader, not on anything this app does. All the app does is listen on `127.0.0.1:3000` for CS2 game-state posts, read local media sessions, and synthesize a media key. It contacts no servers and writes nothing outside its own temp folder.

If you would rather not trust a downloaded binary, you have two good options. The whole app is one readable Python file, so paste `cs2_media_control.py` into any AI assistant and ask it to audit what it does. Or skip the download entirely and build the EXE yourself with `build_exe.ps1`. Your machine, your call.

## License

MIT, see [LICENSE](LICENSE).
