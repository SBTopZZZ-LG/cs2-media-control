import tkinter as tk
from tkinter import ttk, scrolledtext
import threading
from flask import Flask, request
import logging
import ctypes
import struct
import time
from ctypes import wintypes

# Configuration
PORT = 3000
HOST = '127.0.0.1'
# Delay (ms) between detecting a "resume media" state (player dead / round over) and actually
# pressing the play key + switching focus. Gives the player a moment after dying before media
# kicks back in. The pause path (respawn) is instant.
RESUME_DELAY_MS = 2000

def press_media_key():
    # VK_MEDIA_PLAY_PAUSE = 0xB3
    try:
        ctypes.windll.user32.keybd_event(0xB3, 0, 0, 0) # Key Down
        ctypes.windll.user32.keybd_event(0xB3, 0, 2, 0) # Key Up
    except Exception as e:
        print(f"Failed to press media key: {e}")


# --- Window enumeration / focus helpers (auto-focus feature) ---

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
WM_GETICON = 0x7F
ICON_SMALL = 0
ICON_BIG = 1
GCL_HICON = -14
GCL_HICONSM = -34
SW_RESTORE = 9
CS2_TITLE_SUBSTRING = "Counter-Strike"
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# GetClassLongPtrW returns LONG_PTR (pointer-sized); ctypes default is c_int (32-bit),
# which would truncate the HICON on 64-bit Windows.
try:
    ctypes.windll.user32.GetClassLongPtrW.restype = ctypes.c_void_p
    ctypes.windll.user32.GetClassLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
except AttributeError:
    pass


def _is_window_alive(hwnd):
    try:
        return bool(ctypes.windll.user32.IsWindow(hwnd))
    except Exception:
        return False


def _get_process_exe(pid):
    """Return the full executable path for a PID, or '' on failure."""
    if not pid:
        return ""
    kernel32 = ctypes.windll.kernel32
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        buff = ctypes.create_unicode_buffer(1024)
        n = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(h, 0, buff, ctypes.byref(n)):
            return buff.value
        return ""
    finally:
        kernel32.CloseHandle(h)


def list_visible_windows():
    """Return [(hwnd, title, exe_path), ...] for every visible top-level window with a non-empty title."""
    results = []
    pid = wintypes.DWORD()

    @WNDENUMPROC
    def callback(hwnd, _lParam):
        try:
            if not ctypes.windll.user32.IsWindowVisible(hwnd):
                return True
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buff = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value.strip()
            if not title:
                return True
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            exe = _get_process_exe(pid.value)
            results.append((hwnd, title, exe))
        except Exception:
            pass
        return True

    ctypes.windll.user32.EnumWindows(callback, 0)
    return results


def get_window_icon_handle(hwnd):
    """Return an HICON for the window, trying several sources. None if unavailable."""
    if not _is_window_alive(hwnd):
        return None
    user32 = ctypes.windll.user32
    hicon = user32.SendMessageW(hwnd, WM_GETICON, ICON_SMALL, 0)
    if hicon:
        return hicon
    try:
        hicon = user32.GetClassLongPtrW(hwnd, GCL_HICONSM)
    except Exception:
        hicon = 0
    if hicon:
        return hicon
    hicon = user32.SendMessageW(hwnd, WM_GETICON, ICON_BIG, 0)
    if hicon:
        return hicon
    try:
        hicon = user32.GetClassLongPtrW(hwnd, GCL_HICON)
    except Exception:
        hicon = 0
    return hicon or None


def hicon_to_photoimage(hicon, size=16):
    """Render an HICON into a tk.PhotoImage of the given size. Alpha is composited on white.

    Uses CreateDIBSection (a real 32bpp DIB) instead of CreateCompatibleBitmap (a DDB) so the
    alpha channel survives the round-trip through DrawIconEx. With a DDB, GetDIBits returns
    all-zero alpha, which composites to solid white and makes the icon look blank.
    """
    if not hicon:
        return None
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    hdc = mem_dc = dst_bmp = old_bmp = None
    bits_ptr = ctypes.c_void_p()
    try:
        hdc = user32.GetDC(0)
        mem_dc = gdi32.CreateCompatibleDC(hdc)

        bmi = ctypes.create_string_buffer(40)
        struct.pack_into('IiiHHIIiiII', bmi, 0,
                         40, size, -size, 1, 32, 0,
                         size * size * 4, 0, 0, 0, 0)
        dst_bmp = gdi32.CreateDIBSection(mem_dc, bmi, 0, ctypes.byref(bits_ptr), 0, 0)
        if not dst_bmp or not bits_ptr.value:
            return None

        old_bmp = gdi32.SelectObject(mem_dc, dst_bmp)
        # DI_NORMAL = 0x0003
        if not user32.DrawIconEx(mem_dc, 0, 0, hicon, size, size, 0, 0, 0x0003):
            return None

        # Read pixels directly out of the DIB section's bits (BGRA, top-down)
        nbytes = size * size * 4
        raw = (ctypes.c_ubyte * nbytes).from_address(bits_ptr.value)
        img = tk.PhotoImage(width=size, height=size)
        for y in range(size):
            for x in range(size):
                off = (y * size + x) * 4
                b, g, r, a = raw[off], raw[off + 1], raw[off + 2], raw[off + 3]
                if a < 255:
                    alpha = a / 255.0
                    r = int(r * alpha + 255 * (1 - alpha))
                    g = int(g * alpha + 255 * (1 - alpha))
                    b = int(b * alpha + 255 * (1 - alpha))
                img.put(f"#{r:02x}{g:02x}{b:02x}", (x, y))
        return img
    except Exception as e:
        print(f"hicon_to_photoimage error: {e}")
        return None
    finally:
        if old_bmp and mem_dc:
            try: gdi32.SelectObject(mem_dc, old_bmp)
            except Exception: pass
        if dst_bmp:
            try: gdi32.DeleteObject(dst_bmp)
            except Exception: pass
        if mem_dc:
            try: gdi32.DeleteDC(mem_dc)
            except Exception: pass
        if hdc:
            try: user32.ReleaseDC(0, hdc)
            except Exception: pass


def find_cs2_window():
    """Return (hwnd, title) of the first visible window whose title contains 'Counter-Strike'."""
    for hwnd, title, _exe in list_visible_windows():
        if CS2_TITLE_SUBSTRING in title:
            return hwnd, title
    return None, None


def focus_window(hwnd):
    """Bring the window to the foreground. Uses AttachThreadInput to bypass foreground lock. Best-effort."""
    if not hwnd or not _is_window_alive(hwnd):
        return False
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    foreground_hwnd = user32.GetForegroundWindow()
    foreground_thread = user32.GetWindowThreadProcessId(foreground_hwnd, 0)
    current_thread = kernel32.GetCurrentThreadId()
    attached = False
    if foreground_thread and foreground_thread != current_thread:
        try:
            user32.AttachThreadInput(foreground_thread, current_thread, True)
            attached = True
        except Exception:
            attached = False
    try:
        return bool(user32.SetForegroundWindow(hwnd))
    finally:
        if attached:
            try:
                user32.AttachThreadInput(foreground_thread, current_thread, False)
            except Exception:
                pass


class WindowPicker(tk.Frame):
    """Button + pop-up list that lets the user pick from currently visible top-level windows.

    Selection is keyed by the window's executable path, not its hwnd or title, so it survives
    a YouTube video change (title mutates), a browser tab switch, or a full app restart
    (hwnd is reused and lost). When the selected exe no longer has any visible window, the
    picker enters a 'stale' state and the button shows a warning.
    """

    def __init__(self, parent, on_select=None, on_stale=None, button_width=38, **kwargs):
        super().__init__(parent, **kwargs)
        self.on_select = on_select
        self.on_stale = on_stale
        self.windows = []  # list of (hwnd, title, exe, photoimage_or_none)
        self.selected_exe = None  # identity (case-insensitive compare)
        self.selected_hwnd = None  # current live hwnd for the selected exe
        self.is_stale = False
        self.dropdown = None
        self._click_bind_id = None

        self.button = ttk.Button(self, text="(Select window...)", width=button_width,
                                 command=self.toggle_dropdown, compound="left")
        self.button.pack(side="left", padx=(0, 5))
        self.refresh_btn = ttk.Button(self, text="Refresh", width=8, command=self.refresh)
        self.refresh_btn.pack(side="left")

    def set_enabled(self, enabled):
        state = "normal" if enabled else "disabled"
        self.button.config(state=state)
        self.refresh_btn.config(state=state)
        if not enabled:
            self.hide_dropdown()

    def refresh(self):
        new = []
        for hwnd, title, exe in list_visible_windows():
            hicon = get_window_icon_handle(hwnd)
            icon = hicon_to_photoimage(hicon, size=16) if hicon else None
            new.append((hwnd, title, exe, icon))
        self.windows = new

        if self.selected_exe:
            target = self.selected_exe.lower()
            # Prefer the same hwnd if it still exists (preserves identity through title changes)
            if self.selected_hwnd and any(h == self.selected_hwnd for h, _, _, _ in self.windows):
                self.is_stale = False
            else:
                # Fall back to any window of the same exe (z-order: first enumerated = topmost)
                new_hwnd = None
                for hwnd, _, exe, _ in self.windows:
                    if exe and exe.lower() == target:
                        new_hwnd = hwnd
                        break
                if new_hwnd:
                    self.selected_hwnd = new_hwnd
                    self.is_stale = False
                else:
                    self.selected_hwnd = None
                    was_stale = self.is_stale
                    self.is_stale = True
                    if not was_stale and self.on_stale:
                        self.on_stale()
        else:
            self.selected_hwnd = None
            self.is_stale = False

        self._update_button_text()

    def _update_button_text(self):
        if self.is_stale:
            exe_name = self.selected_exe.rsplit("\\", 1)[-1] if self.selected_exe else "window"
            self.button.config(text=f"(stale: {exe_name} closed - pick again)",
                               image="", compound="none")
            return
        for hwnd, title, _exe, icon in self.windows:
            if hwnd == self.selected_hwnd:
                t = title if len(title) <= 60 else title[:57] + "..."
                self.button.config(text=t, image=icon, compound="left")
                return
        self.button.config(text="(Select window...)", image="", compound="none")

    def get_selected(self):
        """Return (hwnd, exe). hwnd is None if there is no live window for the selected exe."""
        return self.selected_hwnd, self.selected_exe

    def select(self, hwnd):
        for w_hwnd, _title, exe, _icon in self.windows:
            if w_hwnd == hwnd:
                self.selected_hwnd = hwnd
                self.selected_exe = exe
                self.is_stale = False
                break
        self._update_button_text()
        if self.on_select:
            self.on_select(hwnd, self.selected_exe or "")
        self.hide_dropdown()

    def toggle_dropdown(self):
        if self.dropdown and self.dropdown.winfo_exists():
            self.hide_dropdown()
        else:
            self.show_dropdown()

    def show_dropdown(self):
        if not self.windows:
            self.refresh()
        self.dropdown = tk.Toplevel(self)
        self.dropdown.wm_overrideredirect(True)
        x = self.button.winfo_rootx()
        y = self.button.winfo_rooty() + self.button.winfo_height() + 2
        self.dropdown.wm_geometry(f"+{x}+{y}")

        outer = ttk.Frame(self.dropdown, relief="solid", borderwidth=1)
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, width=420, height=320, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win_id, width=e.width))
        canvas.configure(yscrollcommand=scrollbar.set)

        if not self.windows:
            ttk.Label(inner, text="(no visible windows)").pack(padx=10, pady=10)
        else:
            for hwnd, title, exe, icon in self.windows:
                row = ttk.Frame(inner)
                row.pack(fill="x")
                if icon is not None:
                    lbl_icon = ttk.Label(row, image=icon)
                else:
                    lbl_icon = ttk.Label(row, text="  ", width=2)
                lbl_icon.pack(side="left", padx=(4, 2), pady=3)
                exe_name = exe.rsplit("\\", 1)[-1] if exe else ""
                label = title if not exe_name else f"{title}  [{exe_name}]"
                lbl_text = ttk.Label(row, text=label, anchor="w")
                lbl_text.pack(side="left", fill="x", expand=True, padx=(2, 8), pady=3)
                for w in (row, lbl_icon, lbl_text):
                    w.bind("<Button-1>", lambda _e, h=hwnd: self.select(h))

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.dropdown.bind("<Escape>", lambda _e: self.hide_dropdown())

        top = self.winfo_toplevel()
        self._click_bind_id = top.bind("<Button-1>", self._on_global_click, add="+")

    def _on_global_click(self, event):
        if not self.dropdown or not self.dropdown.winfo_exists():
            return
        for w in (self.dropdown, self.button):
            try:
                wx, wy = w.winfo_rootx(), w.winfo_rooty()
                ww, wh = w.winfo_width(), w.winfo_height()
            except Exception:
                continue
            if wx <= event.x_root <= wx + ww and wy <= event.y_root <= wy + wh:
                return
        self.after(50, self.hide_dropdown)

    def hide_dropdown(self):
        if self.dropdown and self.dropdown.winfo_exists():
            self.dropdown.destroy()
        self.dropdown = None
        if self._click_bind_id:
            try:
                self.winfo_toplevel().unbind("<Button-1>", self._click_bind_id)
            except Exception:
                pass
            self._click_bind_id = None

class CS2MediaApp:
    def __init__(self, root):
        self.root = root
        self.root.title("CS2 Media Controller")
        self.root.geometry("600x400")
        
        # Application State
        self.media_is_playing = True # assume media is playing initially or let user toggle
        self.is_running = True
        self.is_enabled = tk.BooleanVar(value=True)
        self.current_score = -1
        self.has_died_this_round = False
        self.round_in_progress = False

        # Auto-focus state
        self.auto_focus_enabled = tk.BooleanVar(value=False)
        self.last_focus_hwnd = None
        self._refresh_job = None
        self._pending_resume_job = None

        # Controls
        control_frame = ttk.LabelFrame(root, text="Controls")
        control_frame.pack(fill="x", padx=10, pady=5)
        ttk.Checkbutton(control_frame, text="Enable Auto-Resume/Pause", variable=self.is_enabled, command=self.on_enable_toggle).pack(anchor="w", padx=5, pady=5)

        # Auto-Focus controls
        focus_frame = ttk.LabelFrame(root, text="Auto-Focus")
        focus_frame.pack(fill="x", padx=10, pady=5)
        ttk.Checkbutton(
            focus_frame,
            text="Auto-focus between CS2 and the selected media window",
            variable=self.auto_focus_enabled,
            command=self.on_auto_focus_toggle,
        ).pack(anchor="w", padx=5, pady=(5, 2))
        picker_row = ttk.Frame(focus_frame)
        picker_row.pack(fill="x", padx=5, pady=(0, 5))
        ttk.Label(picker_row, text="Media window:").pack(side="left", padx=(0, 5))
        self.window_picker = WindowPicker(picker_row, on_select=self.on_window_selected,
                                          on_stale=self.on_window_stale, button_width=42)
        self.window_picker.pack(side="left", fill="x", expand=True)
        self.window_picker.refresh()
        self.window_picker.set_enabled(False)
        
        # User Instructions
        instruction_frame = ttk.LabelFrame(root, text="Instructions")
        instruction_frame.pack(fill="x", padx=10, pady=5)
        ttk.Label(instruction_frame, text="1. Copy the .cfg file to your CS2 cfg folder.").pack(anchor="w")
        ttk.Label(instruction_frame, text="2. Start your music player.").pack(anchor="w")
        ttk.Label(instruction_frame, text="3. Ensure music matches the 'Current Expected State'.").pack(anchor="w")

        # Status Display
        status_frame = ttk.LabelFrame(root, text="Status")
        status_frame.pack(fill="x", padx=10, pady=5)
        
        self.game_state_label = ttk.Label(status_frame, text="Game State: Waiting for data...", foreground="gray")
        self.game_state_label.pack(anchor="w", padx=5)
        
        self.media_state_label = ttk.Label(status_frame, text="Media Control: IDLE", foreground="blue")
        self.media_state_label.pack(anchor="w", padx=5)

        # Log
        log_frame = ttk.LabelFrame(root, text="Event Log (Newest Top)")
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.log_area = scrolledtext.ScrolledText(log_frame, height=10, state='disabled')
        self.log_area.pack(fill="both", expand=True)

        # Start Server
        self.start_server()

    def on_enable_toggle(self):
        status = "Enabled" if self.is_enabled.get() else "Disabled"
        self.log(f"Application {status} by user.")
        if not self.is_enabled.get():
             self.media_state_label.config(text="Media Control: DISABLED", foreground="gray")
             # Cancel any pending delayed resume so it doesn't fire while disabled
             if self._pending_resume_job:
                 self.root.after_cancel(self._pending_resume_job)
                 self._pending_resume_job = None

    def on_auto_focus_toggle(self):
        enabled = self.auto_focus_enabled.get()
        self.window_picker.set_enabled(enabled)
        if enabled:
            self.log("Auto-focus enabled.")
            self.last_focus_hwnd = None
            self._apply_focus(self.media_is_playing)
            self._schedule_refresh()
        else:
            self.log("Auto-focus disabled.")
            self.last_focus_hwnd = None
            if self._refresh_job:
                self.root.after_cancel(self._refresh_job)
                self._refresh_job = None

    def on_window_selected(self, hwnd, exe):
        exe_name = exe.rsplit("\\", 1)[-1] if exe else "?"
        for w_hwnd, title, w_exe, _ in self.window_picker.windows:
            if w_hwnd == hwnd:
                self.log(f"Auto-focus media window set to: {title} ({exe_name})")
                break
        # Force a focus switch on the next state transition rather than immediately
        self.last_focus_hwnd = None

    def on_window_stale(self):
        exe_name = self.window_picker.selected_exe.rsplit("\\", 1)[-1] \
            if self.window_picker.selected_exe else "selected window"
        self.log(f"Auto-focus WARNING: {exe_name} is no longer running. Pick a new window.")

    def _schedule_refresh(self):
        if not self.auto_focus_enabled.get():
            return
        # Don't disrupt the user if the dropdown is open
        dd = self.window_picker.dropdown
        if not (dd and dd.winfo_exists()):
            self.window_picker.refresh()
        self._refresh_job = self.root.after(5000, self._schedule_refresh)

    def _apply_focus(self, should_play):
        if not self.auto_focus_enabled.get():
            return
        target_hwnd = None
        target_name = ""
        if should_play:
            target_hwnd, _target_exe = self.window_picker.get_selected()
            if not target_hwnd:
                # Either nothing selected, or the selected exe has no live window
                # (the picker is already showing the stale-state warning).
                return
            for hwnd, title, _exe, _ in self.window_picker.windows:
                if hwnd == target_hwnd:
                    target_name = title
                    break
            if not target_name:
                target_name = "media window"
        else:
            cs2_hwnd, cs2_title = find_cs2_window()
            if not cs2_hwnd:
                self.log("Auto-focus: CS2 window not found. Skipping focus.")
                return
            target_hwnd = cs2_hwnd
            target_name = cs2_title or "Counter-Strike 2"

        if target_hwnd == self.last_focus_hwnd:
            return
        if focus_window(target_hwnd):
            self.log(f"Auto-focus: switched to '{target_name}'")
            self.last_focus_hwnd = target_hwnd
        else:
            self.log(f"Auto-focus: SetForegroundWindow blocked for '{target_name}' (try running as Administrator).")

    def log(self, message):
        self.log_area.config(state='normal')
        self.log_area.insert('1.0', f"{time.strftime('%H:%M:%S')} - {message}\n")
        self.log_area.config(state='disabled')

    def start_server(self):
        self.server = Flask(__name__)
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR) # Silence Flask output

        @self.server.route('/', methods=['POST'])
        def handle_post():
            if not self.is_running:
                return '', 500
            try:
                data = request.json
                self.process_payload(data)
            except Exception as e:
                print(f"Error processing payload: {e}")
            return '', 200

        self.server_thread = threading.Thread(target=lambda: self.server.run(host=HOST, port=PORT, threaded=True), daemon=True)
        self.server_thread.start()
        self.log(f"Server started on {HOST}:{PORT}")

    def process_payload(self, data):
        # Extract relevant data
        player = data.get('player', {})
        provider = data.get('provider', {})
        match_stats = data.get('map', {}) # map info usually contains phase
        round_info = data.get('round', {})
        
        # Steam IDs to detect spectating
        # provider.steamid is the local account
        # player.steamid is the player being watched
        provider_steamid = provider.get('steamid')
        player_steamid = player.get('steamid')

        # Scores
        try:
            ct_score = int(match_stats.get('team_ct', {}).get('score', 0))
            t_score = int(match_stats.get('team_t', {}).get('score', 0))
            total_score = ct_score + t_score
        except:
             total_score = 0

        # Default safe values
        health = player.get('state', {}).get('health', 100)
        round_phase = round_info.get('phase', '') # 'live', 'freezetime', 'over'

        # Debug info for log
        debug_vals = f"[H:{health}, Ph:{round_phase}, Score:{total_score}]"

        # Logic
        should_play = False
        reason = ""

        # Score change detection (Round Reset)
        if total_score > self.current_score:
            self.current_score = total_score
            self.has_died_this_round = False
            self.log(f"New Round detected (Score: {total_score}). Resetting death state.")

        # Determine Playing State
        
        # 1. Round Over / Freezetime -> Resume
        if round_phase == 'over' or round_phase == 'freezetime':
             # Note: Freezetime usually happens at start of round, but score update happens then too.
             # We want to pause when we spawn (live/freezetime) unless we are dead?
             # User said: "pause when another round starts or I respawn"
             # So actually Freezetime should probably be PAUSED if we are alive (spawned).
             if round_phase == 'over':
                 should_play = True
                 reason = "Round Over"
             else:
                 # Freezetime - usually players are spawned and alive.
                 should_play = False
                 reason = "Freezetime (Alive)"
                 self.has_died_this_round = False

        # 2. Live Round
        else: # round_phase == 'live'
             # Check for Death Triggers
             # 1. Health is 0
             # 2. We are spectating (Implies we are dead in Comp)
             is_dead_or_spectating = (health == 0) or (provider_steamid and player_steamid and provider_steamid != player_steamid)

             if is_dead_or_spectating:
                 if not self.has_died_this_round:
                     self.has_died_this_round = True
                     should_play = True
                     reason = "Just Died/Spectating"
                 else:
                     should_play = True
                     reason = "Already Dead/Spectating"
             else:
                 # Alive and playing as ourselves
                 if self.has_died_this_round:
                      # Sticky death state: We died this round, so we stay "playing music"
                      # even if we are spectating someone who is alive (health > 0)
                      should_play = True
                      reason = "Spectating (Sticky State)"
                 else:
                      should_play = False
                      reason = "Alive"
        
        # Override for 'over' phase to ensure we always play at end of round
        if round_phase == 'over':
             should_play = True
             reason = "Round Over"

        self.update_gui(f"H:{health} | Ph:{round_phase} | Score:{total_score} | Died:{self.has_died_this_round}", should_play, reason, debug_vals)

    def update_gui(self, game_text, should_play, reason, debug_vals):
        self.root.after(0, lambda: self._safe_update_gui(game_text, should_play, reason, debug_vals))

    def _safe_update_gui(self, game_text, should_play, reason, debug_vals):
        if not self.is_enabled.get():
             self.game_state_label.config(text=f"Game State: {game_text} (Ignored)")
             return

        self.game_state_label.config(text=f"Game State: {game_text}")

        if should_play != self.media_is_playing:
            # A new transition invalidates any pending delayed resume (e.g., player respawned
            # within the 2s window after dying — we should pause, not resume).
            if self._pending_resume_job:
                self.root.after_cancel(self._pending_resume_job)
                self._pending_resume_job = None

            action = "Resuming" if should_play else "Pausing"
            self.log(f"{action} media. Reason: {reason} {debug_vals}")

            # Update the assumed state immediately so subsequent payloads see a consistent
            # state. The actual key press + focus switch may be delayed (see below).
            self.media_is_playing = should_play

            if should_play:
                # Resume path: delay the key press AND the focus switch by RESUME_DELAY_MS.
                # The player just died or the round just ended — give them a moment before
                # media kicks back in and the window steals focus.
                self.media_state_label.config(
                    text=f"Media Control: RESUMING IN {RESUME_DELAY_MS // 1000}s",
                    foreground="orange")
                self._pending_resume_job = self.root.after(
                    RESUME_DELAY_MS, self._do_delayed_resume, reason, debug_vals)
            else:
                # Pause path: instant. The player respawned and wants to be in the game.
                press_media_key()
                self.media_state_label.config(
                    text="Media Control: PAUSED", foreground="red")
                self._apply_focus(should_play)

    def _do_delayed_resume(self, reason, debug_vals):
        self._pending_resume_job = None
        # Defensive: if the app was disabled mid-delay, or the state somehow flipped
        # without canceling the job, do nothing.
        if not self.is_enabled.get() or not self.media_is_playing:
            return
        press_media_key()
        self._apply_focus(True)  # delayed focus switch to the media window
        self.media_state_label.config(text="Media Control: PLAYING", foreground="green")
        self.log(f"Media resumed after {RESUME_DELAY_MS // 1000}s delay. Reason: {reason} {debug_vals}")

if __name__ == "__main__":
    root = tk.Tk()
    app = CS2MediaApp(root)
    root.mainloop()
