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

### Planned

- Rubik's Cube solving algorithm
- Sense HAT status display
- SQLite logging
- LAMP web dashboard
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

Scan the faces in the order shown on screen. Keep the specified adjacent edge at
the top of the image; this preserves the orientation needed by a Rubik's Cube
solver. Use the keyboard controls shown in the preview:

- `SPACE` captures the current face.
- `B` goes back to rescan the previous face.
- `R` clears the current scan.
- `Q` closes the scanner.

Each capture is stored immediately in `scan_output/cube_state.json`, along with
`face_U.jpg` through `face_B.jpg`. The JSON contains the 3x3 colour matrix and raw
BGR/HSV values for every sticker. After face six it also contains a 54-character
`facelets_URFDLB` string and reports whether exactly nine stickers of every colour
were found.

For consistent results, use diffuse lighting, avoid reflections, fill the guide
with the face, and keep sticker centres inside the small sample squares.

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
- Git & GitHub
- Trello

---

# Repository Structure

```text
rubiks-cube-assistant/
│
├── config/                 # Application configuration files
├── src/
│   └── vision/
│       └── face_scan.py   # Existing fixed-grid LAB scanner
│
├── calibration/            # Colour calibration data
├── captures/               # Captured images
├── database/               # SQLite database
├── docs/                   # Project documentation
├── hardware/               # Hardware designs and wiring
├── scripts/                # Utility scripts
├── tests/                  # Unit tests
├── web/                    # LAMP dashboard
│
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

- [ ] Integrate Rubik's Cube solving algorithm
- [ ] Generate solving sequence
- [ ] Display solving instructions

## Phase 5 – Embedded Features

- [ ] Sense HAT integration
- [ ] SQLite database
- [ ] LAMP web dashboard
- [ ] Multithreading

## Phase 6 – Optional Extension

- [ ] Motorised cube rotation platform

---

# Project Status

**Current Stage:** Initial Development

Current progress:

- ✅ Project selected
- ✅ Repository created
- ✅ Development environment being configured
- ⏳ OpenCV Rubik's Cube scanning implementation in progress
- ⏳ Colour calibration
- ⏳ Cube state generation

---

# License

This repository was developed as part of the **ENSE810 Embedded Software Engineering** course at **Auckland University of Technology (AUT)** for educational purposes.
