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

- Capture images of all six faces of a Rubik's Cube using a Raspberry Pi camera.
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
- Guided scanning of all six 3x3 faces
- Per-session colour calibration from the six centre stickers
- Colour-count validation and a solver-ready URFDLB facelet string
- Incremental JSON storage of colours, raw BGR/HSV samples, and face images
- Kociemba 1.2.1 physical-state validation and 3x3 solutions
- OpenCV next/back/cancel move guidance
- Sense HAT LED status and joystick controls with a laptop fallback
- SQLite terminal history and retryable summary synchronization
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

### Experimental angled side scanner

To test the above-cube view while keeping the existing six-face scanner intact:

```bash
python src/vision/face_scan.py --mode angled-sides --backend opencv --device 0 \
  --output angled_scan
```

Keep white on top throughout. The four camera positions are green, red, blue,
then orange facing forward. At the first position, align both the white top and
green front with their perspective guides; one press of `SPACE` saves both `U`
and `F`. The next three presses save `R`, `B`, and `L`. Each face is perspective
corrected into a square `face_*.jpg`, while `capture_*.jpg` retains the original
camera view.

This mode deliberately does not scan the yellow `D` face. Its JSON therefore
reports an incomplete cube and is intended for capture testing only; use the
default `head-on` mode for solving until bottom-face inference is implemented.

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
python src/app.py --backend auto --device 0 --output scan_output --database data/solve_history.db
```

The scanner retains the existing OpenCV window, grid, face sequence, orientation
prompts, photographs, and `cube_state.json`. A colour-balanced but physically
impossible cube is reported in that same window so `B` or `R` can be used to
rescan. A solved cube produces zero moves.

Keyboard guidance uses `SPACE` or `N` for next, `B` for back, and `Q` to cancel.
Sense HAT controls are:

| Context | Joystick controls |
|---|---|
| Scanner | middle capture, left back, down reset, up cancel |
| Guidance | right/middle next, left back, up cancel |

If Sense HAT is unavailable, the application continues with keyboard controls.
The LED matrix mirrors ready, scanning, accepted, error, calculating, current
move, and complete states when hardware is present.

Every run writes one `COMPLETE`, `ERROR`, or `CANCELLED` row to SQLite. To enable
best-effort LAMP synchronization, set `RUBIKS_SYNC_URL` and
`RUBIKS_SYNC_API_KEY` in the application environment. Pending rows are attempted
once at startup and once after a terminal row is stored; failures remain pending.
Only allowlisted terminal summaries leave the device—never face images, raw
BGR/HSV samples, calibration evidence, or local paths. See
[`docs/lamp-deployment.md`](docs/lamp-deployment.md) for server configuration and
the live acceptance checklist.

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
- ⏳ Raspberry Pi camera, Sense HAT, physical solve, and performance acceptance
- ⏳ Live MySQL migration, HTTPS, authenticated upload/retry, and browser verification

## Local verification

From the repository root:

```powershell
python -m unittest discover -s tests -v
python src/vision/face_scan.py --help
python src/app.py --help
php -l web/api/sessions.php
php -l web/index.php
```

The PHP lint commands require PHP on the development machine or LAMP host.

---

# License

This repository was developed as part of the **ENSE810 Embedded Software Engineering** course at **Auckland University of Technology (AUT)** for educational purposes.
