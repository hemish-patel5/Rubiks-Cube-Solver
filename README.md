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

- Live camera preview
- Rubik's Cube face scanning
- Colour detection using OpenCV
- Cube state validation
- Solve history database

### Planned

- Full six-face scanning workflow
- Automatic colour calibration
- Rubik's Cube solving algorithm
- Sense HAT status display
- SQLite logging
- LAMP web dashboard
- Optional motorised rotating platform

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
│   └── rubiks_assistant/
│       ├── camera/
│       ├── vision/
│       ├── cube/
│       ├── interface/
│       ├── storage/
│       ├── web/
│       ├── motor/
│       └── utils/
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

- [ ] Configure Raspberry Pi camera
- [ ] Live OpenCV camera preview
- [ ] Create fixed 3×3 scanning overlay

## Phase 2 – Colour Detection

- [ ] Capture HSV values
- [ ] Create colour calibration dataset
- [ ] Implement colour classification
- [ ] Detect all nine stickers on a face

## Phase 3 – Cube Representation

- [ ] Scan all six faces
- [ ] Validate cube state
- [ ] Detect invalid scans

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