# Azusa Detector (ᓀ‸ᓂ)

A Windows app that detects a white dot inside the black area of an OBS window and tracks its position, movement, and distance from a fixed circle.
**Position tracking** is the default mode. The interface supports English, Japanese, Korean, and Simplified Chinese.

## Installation

### Download the Windows app

1. Download the Windows x64 ZIP from the [latest release](https://github.com/DevOrca18/Azusa_Detector/releases/latest).
2. Extract the entire ZIP into a folder you can write to, then run `AzusaDetector.exe`.
3. For live monitoring, start OBS and the target game separately.

No Python or pip installation is required. The executable includes the sample video, alert sound, timer digit templates, and UI artwork.
Extract the archive before running the app: settings and recordings are written beside the executable.

The repository's `dist/main.exe` is an older build. Use `AzusaDetector.exe` from the latest release.
When sharing the app, distribute the ZIP with its instructions, source, and dependency licenses.

### Run from source

Requires Windows x64, Python 3.12, and Git. Run in PowerShell:

```powershell
git clone https://github.com/DevOrca18/Azusa_Detector.git
cd Azusa_Detector
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

To launch without a console after installation:

```powershell
.\.venv\Scripts\pythonw.exe main.py
```

## Usage

### 1. Try the sample video

Click the **play icon** below the preview or press **S** to loop the built-in 14-second white-dot video.
No OBS or game selection is needed. Press S again to return to the actual source.

The sample demonstrates position, movement, circle judging, and measurement guides.
It is a silent preview with no recording. The position reference resets at the start of each loop.
The sample's black area uses its original 1920×1080 pixels; values may differ from an image scaled down inside an OBS window.

To launch directly into the sample:

```powershell
.\AzusaDetector.exe --sample
# From source:
.\.venv\Scripts\python.exe main.py --sample
```

### 2. Select the capture windows

In the first setup step, select the two sources:

| Source | Purpose |
| --- | --- |
| OBS window | Detect the black area and white dot |
| Game window | Read the game timer for automatic recording |

Prepare the **black background and white dot** input in OBS. Keep its window visible; minimized windows cannot be captured.
If a window is missing from the list, press **F5** or use the refresh button.
Missing required sources and invalid active settings are highlighted. The start button stays gray until they are resolved.

### 3. Choose a mode and thresholds

| Mode | Settings | Behavior |
| --- | --- | --- |
| Position tracking — default | Separate X/Y or total distance, beep, measurement guide | Compare the current valid detection with the previous valid detection |
| Circle judging | Radius, GOOD/SOSO limits, beep | Judge and grade movement outside a circle with a fixed center in the black area |

**Position tracking**

- **Separate X/Y:** defaults to X **50 px** and Y **50 px**. Alert when `|ΔX| ≥ X` or `|ΔY| ≥ Y`.
- **Total distance:** alert when `sqrt(ΔX² + ΔY²) ≥ threshold`.
- **Beep ON:** show an alert and play a sound when the movement threshold is reached. Movement sounds are limited to once per second.
- **Measurement guide ON:** show a rectangle for X/Y or a circle for total distance, centered on the previous valid position. This toggle is independent of the beep and does not affect detection or recording.

**Circle judging**

- The circle boundary counts as inside. A point must move beyond it to count as outside.
- Turning the beep off preserves the visual alert, grading, and alert records.
- GOOD and SOSO limits are the fraction of valid judged frames detected outside the circle: `0.05 = 5%`.
- Sessions with no valid judgments, or recorded in position tracking mode, receive an `N/A` grade.

Coordinates and thresholds use **original capture pixels**: right is +X and down is +Y.
They do not represent the pixels of the scaled preview or physical distance in the game.

### 4. Start and stop monitoring

Click **Start monitoring** to turn the same preview panel into a live monitor.
If the sample is playing, the app switches to the selected OBS source.

- Before starting: preview only, with no recording or sound.
- While monitoring: alerts and manual or automatic recording are available.
- Select sources, mode, and language before starting. Thresholds, beep settings, and measurement guides can change while monitoring.
- Press **ESC**, click the stop icon below the video, or use the monitoring stop button to stop.
- Stopping monitoring or closing the app saves an active CSV recording.

**Position references and missing detections**

The first valid detection defines position `(0, 0)`. Each movement value compares two consecutive valid detections.
For `A → missing → missing → B`, the next movement is `B − A`; a missing interval does not make the next detection automatically safe.
If that movement reaches the threshold, it triggers an alert.

Missing frames have blank coordinate fields in the CSV. Starting or stopping a recording does not reset the position reference.
Starting a new monitoring run, requesting redetection, or changing the input dimensions resets it.

### 5. View recordings and activity

- Press **R** or click the record icon to start or stop a manual CSV recording.
- Enable automatic recording from the game timer. The default **Fixed duration** mode starts after stable detection of the start range (55–59 seconds), records for **60 seconds**, then saves automatically. The 60 seconds are measured from recording start, independently of the game timer.
- Change **Duration** to an integer from **1 to 3600 seconds** before monitoring. Missing timer readings, a lost capture, or an early 0/1 reading do not stop a timed recording. The live panel shows the time remaining; missing positions remain blank in the CSV.
- Select **Timer detection** for the previous behavior: stop after stable detection of the end range (0–1 seconds), or after the timer is missing for more than 2 seconds. Choose the stop mode and duration before monitoring.
- After an automatic recording ends, monitoring continues. Following the 5-second cooldown, a new valid start detection can start the next recording. R, ESC, redetection, closing the app, or turning automatic recording off can still end a recording early. Resizing the capture also ends it to preserve coordinate consistency.
- Open saved files with the **recordings folder** button on the left. Recordings contain data, not video.
- The **activity log** below the character shows starts, stops, setting changes, saved recordings, and errors.
- A played sound appears as `[14:30:12] (ᓀ‸ᓂ)`. Muting, disabled beeps, and sample playback do not produce sound entries.
- The log keeps the latest 300 entries during the current run. Scroll to older entries, or select text and press Ctrl+C to copy. Changing language preserves the entries. Repeated capture errors are logged again only when their state changes.
- The GitHub **usage guide** button opens this README.

## Buttons and shortcuts

Hover over an icon or focus it with the keyboard to see its action and shortcut.

| Key | Action |
| --- | --- |
| R | Start or stop CSV recording |
| M | Temporarily mute or unmute beeps |
| C | Save images of the game timer region |
| ESC | Stop monitoring |
| D | Redetect the region and reset position references; save any active recording first |
| F5 / Ctrl+R | Refresh the window list before monitoring |
| S | Play or stop the sample before monitoring |

The M button is disabled when the current mode's beep setting is off.
R/M/C/D/S shortcuts do not run while editing text in a settings field or the activity log.
The yellow button folds or expands the settings panel. The **Language** label stays in English in every language.

## Saved files

Files are stored relative to the executable's folder, or the repository folder when running from source.

| Path | Contents |
| --- | --- |
| `config.json` | Selected windows, mode, language, and detection settings |
| `azusa_record/` | Per-frame CSV files and `sessions_v2.csv` session summaries |
| `assets/digits/calibration/` | Timer-region and digit images saved with C |

On another PC, recheck window names, the OBS input, and the timer region.
The bundled timer reader uses digit templates. Tesseract OCR is not included in the executable.
Existing settings files without an automatic stop mode use the new **Fixed duration / 60 seconds** default on upgrade.

## Troubleshooting

- **Gray start button:** check the OBS/game selections and settings marked in red.
- **No image or minimized source:** restore the OBS window and refresh with F5. Use D to redetect if needed.
- **White dot not detected:** check that the dot is inside the black area. Tiny dots, large white panels, or multiple similarly sized white dots may be rejected.
- **No sound:** check the mode's beep toggle, temporary mute, and Windows volume. Playback errors appear in the activity log.
- **Executable blocked:** this unsigned build may be blocked by Windows application control. On managed PCs, ask the administrator for an approved build. In a development environment, use the source installation steps above.
- **Recording could not be saved:** check folder write permissions and free disk space. Failed recordings remain available for a save retry.

## Development and builds

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\build.ps1
```

Output: `release/AzusaDetector.exe`, including UI artwork, the sample video, alert sound, and digit templates.

Optional checks:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\release\AzusaDetector.exe --self-test
```

The self-test writes `self-test.json` to the application folder.
Offline checks do not replace validation with real OBS/game input or a separate PC.

@DevOrca18
