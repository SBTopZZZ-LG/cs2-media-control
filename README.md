# CS2 Media Controller

This simple Python GUI application automatically pauses and resumes your media (Spotify, YouTube Music, etc.) based on your in-game status in Counter-Strike 2.

## Features
- **Auto-Respect**: Pauses media when the round starts or you respawn.
- **Downtime Entertainment**: Resumes media when you die or the round ends.
- **Visual Status**: Shows connection status and game state in a window.

## Installation

1. **Build the Application (Recommended):**
   - Right-click `build_exe.ps1` and select "Run with PowerShell".
   - This will create a `CS2MediaControl.exe` file in this folder.
   - You can now run this EXE directly without opening terminals.

   *Alternatively, runs as script:*
   - `pip install -r requirements.txt`
   - `python cs2_media_control.py`

2. **Install the Game State Integration Config:**
   **Automatic Method:**
   - Right-click `install_config.ps1` and select "Run with PowerShell".
   
   **Manual Method:**
   - Copy the file `gamestate_integration_media.cfg` from this folder.
   - Navigate to your CS2 installation folder. usually:
     `D:\SteamLibrary\steamapps\common\Counter-Strike Global Offensive\game\csgo\cfg` (or C:\Program Files...)
   - Paste the file there.

## Usage

1. Start your music player (e.g., Spotify) and have music playing (or paused, just be ready).
2. Run the application:
   ```bash
   python cs2_media_control.py
   ```
3. Launch CS2.
4. The application status should update as you play.

## Troubleshooting

- **Admin Privileges**: If the media keys don't trigger while you are in-game, try running the python script as Administrator.
- **Status Sync**: If the app thinks music is playing but it's paused (inverted), just manually press your Play/Pause key once to sync them up.
- **Firewall**: Ensure Windows Firewall allows the Python connection on port 3000 (Localhost only, so usually fine).
