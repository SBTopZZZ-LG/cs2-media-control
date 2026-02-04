import tkinter as tk
from tkinter import ttk, scrolledtext
import threading
from flask import Flask, request
import logging
import ctypes
import time

# Configuration
PORT = 3000
HOST = '127.0.0.1'

def press_media_key():
    # VK_MEDIA_PLAY_PAUSE = 0xB3
    try:
        ctypes.windll.user32.keybd_event(0xB3, 0, 0, 0) # Key Down
        ctypes.windll.user32.keybd_event(0xB3, 0, 2, 0) # Key Up
    except Exception as e:
        print(f"Failed to press media key: {e}")

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

        # Controls
        control_frame = ttk.LabelFrame(root, text="Controls")
        control_frame.pack(fill="x", padx=10, pady=5)
        ttk.Checkbutton(control_frame, text="Enable Auto-Resume/Pause", variable=self.is_enabled, command=self.on_enable_toggle).pack(anchor="w", padx=5, pady=5)
        
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
            # State change detected
            action = "Resuming" if should_play else "Pausing"
            self.log(f"{action} media. Reason: {reason} {debug_vals}")
            
            # Simulate Key Press (DirectInput safe)
            press_media_key()
            
            # Update State
            self.media_is_playing = should_play
            
            state_text = "PLAYING" if self.media_is_playing else "PAUSED"
            color = "green" if self.media_is_playing else "red"
            self.media_state_label.config(text=f"Media Control: {state_text}", foreground=color)

if __name__ == "__main__":
    root = tk.Tk()
    app = CS2MediaApp(root)
    root.mainloop()
