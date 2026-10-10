# Requirement traceability

Status meanings: **verified** has retained automated evidence; **pending physical** must
be demonstrated on the Raspberry Pi or live LAMP host; **pending review** requires a
human/team check.

| Requirement | Implementation | Automated verification | Target evidence/status |
|---|---|---|---|
| FR-01 session controls | Scanner and guidance keyboard controls | cancellation and terminal-record tests | Restart and physical controls: pending physical |
| FR-02 angled views and safe D fallback | `src/vision/face_scan.py` angled workflow and physical reconstruction | angled capture, reconstruction, ambiguity, and validation tests | Ten physical sessions: pending physical |
| FR-03 sticker classification | LAB calibration and OpenCV sampling | scanner classification tests | >=95% of at least 450 visible classifications: pending physical |
| FR-04 order/orientation guidance | OpenCV overlays and keyboard controls | scanner workflow tests | User observation: pending review |
| FR-05 rejection/rescan | colour-count and Kociemba validation | invalid/incomplete/impossible-state tests | Physical invalid cube: pending physical |
| FR-06 solving | Kociemba adapter | solved, valid scramble, and invalid-state tests | Complete physical scramble: pending physical |
| FR-07 progress and moves | OpenCV scanner and move-guidance interface | guidance/control tests | Five-minute demonstration: pending physical |
| FR-08 SQLite history | `src/storage/history.py` | terminal status, idempotency, and field tests | Local database inspection: pending physical |
| FR-09 LAMP history | PHP endpoint, MySQL schema, dashboard, HTTP uploader | payload, API, dashboard, and web-contract tests | Live upload/browser check: pending physical |
| NFR-01 accuracy | controlled lighting, calibration, validation | deterministic classification fixtures | >=95% result: pending physical |
| NFR-02 performance | local capture and processing | workflow regression tests | Every measured view <5 s: pending physical |
| NFR-03 usability | explicit position/orientation/result overlays | control and scanner tests | Team/user observation: pending review |
| NFR-04 reliability | fallback plus physical-state validation | ambiguity and rejection tests | Fallback and invalid-cube video: pending physical |
| NFR-05 maintainability | separated vision, solver, hardware, interface, storage, and sync modules | full regression suite and compilation | Architecture review: pending review |
| NFR-06 availability | local row committed before remote attempt | failed upload remains pending | Offline/reconnect test: pending physical |
| NFR-07 responsiveness | `RemoteSyncWorker` owns all upload/retry calls | blocked uploader cannot delay scanner; lifecycle/concurrency tests | Slow/offline LAMP demonstration: pending physical |

The original preliminary report remains the historical baseline. `CR-001` in
`requirements.md` is the traceable decision that changes FR-02 for the final system.
