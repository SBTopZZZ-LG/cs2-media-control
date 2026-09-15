"""SMTC multi-source pause/resume POC.

Proves the building block behind the main app's "Media Sources" mode: enumerate
every Windows System Media Transport Controls (SMTC) session, pause each PLAYING
one individually via TryPauseAsync (keyed by AUMID), and later resume only that
snapshot via TryPlayAsync — no media-key toggle, so no toggle-desync.

Standalone throwaway GUI (session table + pause/resume toggle + log). Run with
the project venv on Windows: .venv\\Scripts\\python.exe poc\\poc_smtc_pause.py
"""
import asyncio
import tkinter as tk
from tkinter import ttk, scrolledtext

from winrt.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as SessionManager,
    GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
)

STATUS_NAMES = {0: "CLOSED", 1: "OPENED", 2: "CHANGING", 3: "STOPPED", 4: "PLAYING", 5: "PAUSED"}


def run_async(coro):
    """Run an awaitable to completion (POC: blocks UI briefly, fine)."""
    async def _wrapper():
        return await coro
    return asyncio.run(_wrapper())


async def fetch_sessions():
    """Return [(aumid, status_int, title), ...] for all SMTC sessions right now."""
    mgr = await SessionManager.request_async()
    out = []
    for s in mgr.get_sessions():
        try:
            aumid = s.source_app_user_model_id or "?"
        except Exception:
            aumid = "?"
        try:
            status = int(s.get_playback_info().playback_status)
        except Exception:
            status = -1
        title = ""
        try:
            props = await s.try_get_media_properties_async()
            title = (props.title or "").strip()
        except Exception:
            pass
        out.append((aumid, status, title))
    return out


async def pause_aumids(aumids):
    """Pause sessions whose AUMID is in the set. Returns {aumid: ok}."""
    mgr = await SessionManager.request_async()
    res = {}
    for s in mgr.get_sessions():
        try:
            aumid = s.source_app_user_model_id or ""
        except Exception:
            continue
        if aumid in aumids:
            try:
                res[aumid] = bool(await s.try_pause_async())
            except Exception as e:
                res[aumid] = f"ERR {e}"
    return res


async def resume_aumids(aumids):
    mgr = await SessionManager.request_async()
    live = {}
    for s in mgr.get_sessions():
        try:
            live.setdefault(s.source_app_user_model_id or "", []).append(s)
        except Exception:
            continue
    res = {}
    for aumid in aumids:
        for s in live.get(aumid, []):
            try:
                res[aumid] = bool(await s.try_play_async())
            except Exception as e:
                res[aumid] = f"ERR {e}"
        if aumid not in res:
            res[aumid] = "GONE (no live session)"
    return res


class PocApp:
    def __init__(self, root):
        self.root = root
        root.title("SMTC multi-pause POC (temp)")
        root.geometry("620x420")
        self.paused_by_us = []  # snapshot of AUMIDs we paused

        top = ttk.Frame(root)
        top.pack(fill="x", padx=10, pady=8)
        self.toggle_btn = ttk.Button(top, text="Pause all playing", command=self.on_toggle)
        self.toggle_btn.pack(side="left")
        ttk.Button(top, text="Refresh", command=self.refresh).pack(side="left", padx=6)
        self.state_lbl = ttk.Label(top, text="state: PLAYING (nothing paused by us)")
        self.state_lbl.pack(side="left", padx=10)

        cols = ("app", "status", "title")
        self.tree = ttk.Treeview(root, columns=cols, show="headings", height=8)
        for c, w in (("app", 220), ("status", 100), ("title", 260)):
            self.tree.heading(c, text=c)
            self.tree.column(c, width=w)
        self.tree.pack(fill="both", expand=True, padx=10)

        logf = ttk.LabelFrame(root, text="Log")
        logf.pack(fill="both", expand=True, padx=10, pady=8)
        self.log_area = scrolledtext.ScrolledText(logf, height=6, state="disabled")
        self.log_area.pack(fill="both", expand=True)

        self.refresh()

    def log(self, msg):
        self.log_area.config(state="normal")
        self.log_area.insert("1.0", msg + "\n")
        self.log_area.config(state="disabled")

    def refresh(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        try:
            sessions = run_async(fetch_sessions())
        except Exception as e:
            self.log(f"Refresh FAILED: {e}")
            return
        if not sessions:
            self.log("Refresh: no SMTC sessions (start Spotify/YouTube).")
        for aumid, st, title in sessions:
            self.tree.insert("", "end", values=(aumid, STATUS_NAMES.get(st, st), title))
        n_playing = sum(1 for _, st, _ in sessions if st == int(PlaybackStatus.PLAYING))
        if not self.paused_by_us:
            self.toggle_btn.config(text=f"Pause all playing ({n_playing})")
            self.state_lbl.config(text="state: PLAYING (nothing paused by us)")

    def on_toggle(self):
        if not self.paused_by_us:
            # Pause path: snapshot what is PLAYING right now, pause only those.
            try:
                sessions = run_async(fetch_sessions())
            except Exception as e:
                self.log(f"Pause FAILED: {e}")
                return
            targets = sorted({a for a, st, _ in sessions if st == int(PlaybackStatus.PLAYING)})
            if not targets:
                self.log("Pause: nothing is PLAYING right now.")
                self.refresh()
                return
            self.log(f"Pausing: {targets}")
            try:
                res = run_async(pause_aumids(set(targets)))
            except Exception as e:
                self.log(f"Pause FAILED: {e}")
                return
            self.log(f"Pause result: {res}")
            self.paused_by_us = targets
            self.toggle_btn.config(text=f"Resume paused ({len(targets)})")
            self.state_lbl.config(text=f"state: PAUSED-BY-US {targets}")
            self.refresh()
        else:
            # Resume path: play back only the snapshot, not everything.
            targets = self.paused_by_us
            self.log(f"Resuming: {targets}")
            try:
                res = run_async(resume_aumids(targets))
            except Exception as e:
                self.log(f"Resume FAILED: {e}")
                return
            self.log(f"Resume result: {res}")
            self.paused_by_us = []
            self.toggle_btn.config(text="Pause all playing")
            self.state_lbl.config(text="state: PLAYING (nothing paused by us)")
            self.refresh()


if __name__ == "__main__":
    root = tk.Tk()
    PocApp(root)
    root.mainloop()
