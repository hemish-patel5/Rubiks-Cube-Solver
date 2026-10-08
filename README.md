# ENSE810 Embedded Software Engineering – Group 4

## Rubik's Cube Scanning and Solving Assistant

This repository contains the source code, documentation, and hardware resources for **Group 4's ENSE810 Embedded Software Engineering project** at Auckland University of Technology (AUT).

The project aims to develop a **Raspberry Pi-based Rubik's Cube Scanning and Solving Assistant** that uses computer vision to recognise the colours on a standard 3×3 Rubik's Cube, validate the cube state, calculate a solution, and guide the user through the required solving moves.

The system focuses on reliable colour recognition using OpenCV under controlled lighting conditions. As an optional extension, a motorised platform may be developed to automatically rotate the cube between scans.

---

# Group Members

- **Hemish Patel**
- **Kaiden Ziegler**
- **Rafael Marco Manubay**

---

# Project Objectives

The system will:

- Capture four guided angled views covering five faces, with safe reconstruction or a
  direct scan of the concealed yellow face.
- Detect and classify the colour of each sticker using OpenCV.
- Construct and validate a complete digital representation of the cube.
- Calculate a valid solving sequence using a Rubik's Cube solving algorithm.
- Display step-by-step solving instructions to the user.
- Record solve history and statistics in an SQLite database.
- Display solve history and statistics through a web dashboard.
- Provide user feedback using the Raspberry Pi Sense HAT.
- Optionally rotate the cube automatically using a servo or stepper motor.

---

# Features

### Current

- Live camera preview using a USB webcam or Raspberry Pi camera
- Four-position angled scanning with physical bottom-face reconstruction and fallback
- Per-session colour calibration from visible centre stickers
- Colour-count validation and a solver-ready URFDLB facelet string
- Incremental JSON storage of colours, raw BGR/HSV samples, and face images
- Kociemba 1.2.1 physical-state validation and 3x3 solutions
- OpenCV next/back/cancel move guidance
- Sense HAT LED status and joystick controls with a laptop fallback
- SQLite terminal history and retryable summary synchronization
- Background LAMP synchronization that does not block scanning or guidance
- Plain PHP/MySQL JSON endpoint and responsive dashboard with session removal

### Planned

- Raspberry Pi camera and Sense HAT acceptance testing
- Live LAMP deployment, HTTPS, upload/retry, and browser acceptance
- Optional motorised rotating platform

---

# Running the Webcam Scanner

Install the desktop dependencies and start the scanner from the repository root:

```powershell
python -m pip install -r requirements.txt
python src/vision/face_scan.py
```

The default `auto` backend first tries webcam device `0`, then Picamera2. Select a
different USB webcam or force a backend with:

```powershell
python src/vision/face_scan.py --backend opencv --device 1
python src/vision/face_scan.py --backend picamera2
```

On Linux desktops, the scanner and full assistant automatically select `xcb`
when OpenCV bundles that Qt plugin without a Wayland plugin. You can run the
normal command without a `QT_QPA_PLATFORM=xcb` prefix. A desktop display
connection is still required; a plain SSH session without forwarding cannot
show the preview.

Scan the faces in the order shown on screen. Keep the specified adjacent edge at
the top of the image; this preserves the orientation needed by a Rubik's Cube
solver. Use the keyboard controls shown in the preview:

- `SPACE` captures the current face.
- `B` goes back to rescan the previous face.
- `R` clears the current scan.
- `Q` closes the scanner.

### Angled scanner

The default scanner uses an above-cube view:

```bash
python src/vision/face_scan.py --mode angled-sides --backend opencv --device 0 \
  --output scan_output
```

Keep white on top throughout. The four camera positions are green, red, blue,
then orange facing forward. At the first position, align both the white top and
green front with their perspective guides; one press of `SPACE` saves both `U`
and `F`. The next three presses save `R`, `B`, and `L`. Each face is perspective
corrected into a square `face_*.jpg`, while `capture_*.jpg` retains the original
camera view.

After the fourth position, the scanner reconstructs the hidden yellow `D` face
from the remaining physical edge and corner cubies and verifies candidate states
with Kociemba. Some cube states have more than one physically valid hidden face;
five visible faces cannot distinguish them. In that case the GUI asks for one
head-on yellow scan with green at the top. This fallback prevents the solver from
using an arbitrary completion. The original workflow remains available with
`--mode head-on`.

Each capture is stored immediately in `scan_output/cube_state.json`, along with
`face_U.jpg` through `face_B.jpg`. The JSON contains the 3x3 colour matrix and raw
BGR/HSV values for every sticker. After face six it also contains a 54-character
`facelets_URFDLB` string and reports whether exactly nine stickers of every colour
were found.

For consistent results, use diffuse lighting, avoid reflections, fill the guide
with the face, and keep sticker centres inside the small sample squares.
Final classification compares stickers with the six centre references after
normalizing their brightness, reducing yellow/orange confusion in shadows.
Before all six centres are captured, preview and saved partial-scan colours use
provisional HSV thresholds. Once all centres are available, every saved sticker
is reclassified with the calibrated LAB classifier, so final labels may differ
from the earlier preview. The live colour overlay also refreshes every 150 ms,
while capture samples the current frame.
Glare, deep shadows, and camera white-balance changes can still affect colours;
colour-count and physical-state validation remain required before solving.

## Running the complete 3x3 assistant

Use the full command to scan, validate, solve, guide, and record one run:

```powershell
python src/app.py --scan-mode angled-sides --backend auto --device 0 \
  --output scan_output --database data/solve_history.db
```

The main application defaults to angled scanning, physical validation, solving,
and guidance. `cube_state.json` records `captured_faces`, `inferred_faces`, and
whether each face was inferred. A colour-balanced but physically impossible cube
is rejected so it can be rescanned. A solved cube produces zero moves.

Keyboard guidance uses `SPACE` or `N` for next, `B` for back, and `Q` to cancel.
Sense HAT controls are:

| Context | Joystick controls |
|---|---|
| Scanner | middle capture, left back, down reset, up cancel |
| Guidance | right/middle next, left back, up cancel |

If Sense HAT is unavailable, the application continues with keyboard controls.
The LED matrix mirrors ready, scanning, accepted, error, calculating, current
move, and complete states when hardware is present.

Every run writes one `COMPLETE`, `ERROR`, or `CANCELLED` row to SQLite before any
remote attempt. To enable best-effort LAMP synchronization, set `RUBIKS_SYNC_URL`
and `RUBIKS_SYNC_API_KEY` in the application environment. A `remote-sync` worker
retries pending rows in the background at startup, when a terminal row is stored,
and every ten seconds. Network failures cannot block the scanner or discard local
history. Shutdown allows one final attempt for up to four seconds; unfinished rows
remain pending for a future run.
Only allowlisted terminal summaries leave the device—never face images, raw
BGR/HSV samples, calibration evidence, or local paths. See
[`docs/lamp-deployment.md`](docs/lamp-deployment.md) for server configuration and
the live acceptance checklist.

### Testing the rotating platform

The standalone platform test drives a STEP/DIR motor driver continuously without
starting the scanner. It uses Raspberry Pi BCM numbering: GPIO 5 for `DIR` and
GPIO 6 for `STEP`. The default clockwise direction is `DIR=LOW`, matching the
original Arduino program. Run it on the Pi with:

```bash
python src/hardware/stepper_spin.py
```

The gentle geared-platform profile pauses for a quarter second, then ramps from
20 to 250 pulses per second over the first 2500 pulses. Increase it only after the
unloaded platform turns reliably without gear slip.
Press `Ctrl+C` to stop and leave the step output low. To make a cautious finite
test first, run `python src/hardware/stepper_spin.py --steps 1000`. Reverse an
unexpected direction with `--clockwise-level high`.

Connect BCM GPIO 5 (physical pin 29) to the driver's `DIR` input and BCM GPIO 6
(physical pin 31) to `STEP`. Connect Pi 3.3 V to the TMC2209 logic `VDD` and Pi
ground to its logic ground. The existing USB-A power lead connects 5 V to the
driver `+` and ground to `-`; all grounds must be common. The motor connections
are blue to `2B`, yellow to `2A`, orange to `1A`, pink to `1B`, with red left
disconnected. Configure the TMC2209 current limit appropriately before testing.

The dashboard lists sessions in pages of 25 with a **Remove** button on each row.
The API key is configured directly in server-side PHP and must match Apache's
`RUBIKS_API_KEY`; it is never rendered in the browser. Every dashboard visitor
can remove records without a login. Removal deletes the MySQL/MariaDB record and recalculates
statistics. The dashboard database account needs `SELECT` and `DELETE` permission.
Local SQLite history and scan files remain on the Pi. Synced local records are
not automatically uploaded again; manually re-uploading a deleted session will
recreate its server record.

---

# Technologies

## Hardware

- Raspberry Pi
- Raspberry Pi Camera Module (or USB Webcam)
- Raspberry Pi Sense HAT
- Rubik's Cube
- Fixed LED lighting
- Cube stand
- *(Optional)* Servo or stepper motor with driver

## Software

- Python
- OpenCV
- Picamera2
- NumPy
- SQLite
- Apache
- PHP
- MySQL
- Git & Bitbucket
- Trello
- Python multithreading (`Thread`, `Event`, and `Lock`)

---

# Repository Structure

```text
rubiks-cube-assistant/
│
├── src/
│   ├── app.py              # Full 3x3 workflow
│   ├── cube/solver.py      # Kociemba adapter
│   ├── hardware/           # Optional Sense HAT adapter
│   ├── interface/          # OpenCV move guidance
│   ├── storage/            # SQLite history and HTTP sync
│   └── vision/face_scan.py # Existing fixed-grid LAB scanner
├── docs/                   # Deployment and acceptance guidance
├── tests/                  # unittest regression and contract tests
├── web/                    # PHP endpoint, MySQL schema, dashboard
├── README.md
├── requirements.txt
└── .gitignore
```

---

# Development Roadmap

## Phase 1 – Camera Setup

- [x] Configure Raspberry Pi and USB webcam backends
- [x] Live OpenCV camera preview
- [x] Create fixed 3×3 scanning overlay

## Phase 2 – Colour Detection

- [x] Capture BGR and HSV values
- [x] Calibrate from the six centre stickers for each scan
- [x] Implement LAB nearest-reference colour classification
- [x] Detect all nine stickers on a face

## Phase 3 – Cube Representation

- [x] Scan and persist all six faces
- [x] Validate six colour counts
- [x] Report colour-count scan errors for rescanning

## Phase 4 – Cube Solver

- [x] Integrate Kociemba for 3x3 cubes
- [x] Generate and validate solving sequences
- [x] Display next/back/cancel solving instructions

## Phase 5 – Embedded Features

- [x] Sense HAT adapter with no-hardware fallback
- [x] SQLite terminal history
- [x] LAMP code and local security/data contract tests
- [x] Background LAMP synchronization with bounded shutdown
- [ ] Raspberry Pi and live LAMP acceptance

## Phase 6 – Optional Extension

- [ ] Motorised cube rotation platform

---

# Project Status

**Current Stage:** Locally implemented 3x3 workflow; hardware and live LAMP acceptance pending

Current progress:

- ✅ Project selected
- ✅ Repository created
- ✅ Development environment being configured
- ✅ Existing OpenCV/LAB team scanner preserved
- ✅ 3x3 solver, move guidance, Sense HAT adapter, and SQLite history implemented
- ✅ LAMP schema, authenticated write endpoint, and dashboard with session removal implemented
- ✅ Remote upload/retry isolated from the camera and UI in a tested background thread
- ⏳ Raspberry Pi camera, Sense HAT, physical solve, and performance acceptance
- ⏳ Live MySQL migration, HTTPS, authenticated upload/retry, and browser verification

## Local verification

From the repository root:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q src tests
python src/vision/face_scan.py --help
python src/app.py --help
php -l web/api/sessions.php
php -l web/index.php
```

The PHP lint commands require PHP on the development machine or LAMP host.
The maintained requirements, controlled change, traceability, architecture,
measurement tables, and demonstration plan are under [`docs/`](docs/).

---

# License

This repository was developed as part of the **ENSE810 Embedded Software Engineering** course at **Auckland University of Technology (AUT)** for educational purposes.
