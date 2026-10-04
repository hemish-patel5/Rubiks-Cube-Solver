# Current requirements and controlled changes

This file is the maintained requirement baseline for the final ENSE810 project. It does
not replace or rewrite the submitted preliminary report. Changes are recorded so the
team can show why the design evolved and how each change was verified.

## Functional requirements

| ID | Requirement |
|---|---|
| FR-01 | The system shall allow the user to start, cancel, and restart a scanning session. |
| FR-02 | The system shall capture four guided angled views covering five cube faces. It shall infer the concealed yellow face only when the remaining colour evidence makes that inference unambiguous; otherwise it shall request a direct yellow-face scan. Validation and solving shall not proceed until a complete, physically valid six-face state exists. |
| FR-03 | The system shall identify the nine sticker regions and classify their colours using OpenCV. |
| FR-04 | The system shall guide the user through view order and cube orientation. |
| FR-05 | The system shall reject invalid, incomplete, or inconsistent cube states and request another scan where appropriate. |
| FR-06 | The system shall calculate a valid sequence of solving moves for a validated 3x3 state. |
| FR-07 | The system shall display scanning progress, errors, and each required move. |
| FR-08 | The system shall record cube states, move counts, solve times, and errors in SQLite. |
| FR-09 | The system shall provide current and historical solve information through a LAMP web interface. |

## Nonfunctional requirements

| ID | Requirement |
|---|---|
| NFR-01 Accuracy | Under controlled lighting, at least 95% of camera-visible stickers shall be classified correctly. |
| NFR-02 Performance | Each captured view shall be analysed and displayed within five seconds. |
| NFR-03 Usability | The interface shall clearly indicate the required view, orientation, and scan result. |
| NFR-04 Reliability | Invalid or incomplete states shall be rejected before solving. Ambiguous hidden-face reconstruction shall trigger the direct yellow-face fallback. |
| NFR-05 Maintainability | Capture, colour detection, validation, solving, database, interface, and remote-sync responsibilities shall remain separated. |
| NFR-06 Availability | Solve records shall remain stored locally when the remote server is unavailable. |
| NFR-07 Responsiveness | Remote synchronisation shall run independently of camera and user-interface activity. Network failure shall not prevent local recording, scanning, cancellation, or move guidance. |

## CR-001: guided angled scanning

| Field | Record |
|---|---|
| Status | Implemented; team approval evidence still to be attached |
| Implementation date | 4 October 2026 |
| Original requirement | "The system shall capture images of each of the six cube faces." |
| Revised requirement | FR-02 above |
| Reason | Four guided above-cube positions reduce repositioning while preserving the information needed to construct a complete cube state. A direct yellow-face scan remains the safe fallback when five visible faces do not determine one valid hidden face. |
| Functional impact | The default workflow captures U/F together, then R, B, and L. It attempts physical D-face reconstruction and requests a direct D scan when reconstruction is ambiguous. The six-face head-on mode remains available as a fallback. |
| Safety/reliability impact | No inferred state may reach the solver unless colour counts and Kociemba physical-state validation succeed. Ambiguity must never be resolved by choosing an arbitrary candidate. |
| Verification | Existing angled-scanner unit tests; ambiguous reconstruction fallback test; invalid-state rejection test; ten-session physical accuracy/performance exercise in `evidence-log.md`. |
| Approval evidence | **PENDING:** attach a dated team message, meeting minute, or pull-request approval naming the reviewers. Do not replace this field with an unsupported claim. |

## Multithreading decision

Remote LAMP synchronisation is the only threaded responsibility. Camera capture and all
OpenCV window operations remain on the main thread because the scanner is already
responsive and moving OpenCV GUI work across threads would add platform-specific risk.
SQLite is the durable queue; a thread event only signals that pending records may exist.
This keeps the concurrency boundary small, testable, and directly connected to the
responsiveness and offline-availability requirements.
