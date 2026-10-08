# Teammate test handoff

Use this guide to test `feature/threaded-sync-evidence` on the Raspberry Pi and report evidence back to the team. The implementation commit `bd32aed` must appear in the branch history.

Do not include API keys, passwords, tokens, or the contents of `config.sh` in screenshots or test reports.

## 1. Check out the branch

From the repository folder:

```bash
git status
git fetch origin
git switch --track origin/feature/threaded-sync-evidence
git log --oneline -3
```

If the branch already exists locally, use:

```bash
git switch feature/threaded-sync-evidence
git pull --ff-only
git log --oneline -3
```

Confirm that implementation commit `bd32aed` appears in the recent history. If `git status` shows uncommitted work, stop and send the output to the team; do not reset or delete the changes.

## 2. Prepare Python

On the Raspberry Pi, activate the project's existing virtual environment:

```bash
source .venv/bin/activate
```

For a clean desktop environment, create one if needed:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Do not replace a working Raspberry Pi environment containing Picamera2 or its system OpenCV packages.

## 3. Run the automated checks

```bash
python -m unittest discover -s tests -v
python -m compileall -q src tests
python src/app.py --help
python src/vision/face_scan.py --help
```

Expected results:

- The test suite reports `Ran 53 tests` followed by `OK` (one PHP CLI test may be skipped when PHP is unavailable).
- One dashboard contract test may be skipped if PHP CLI is not installed.
- Compilation completes without an error.
- Both help commands display their options without raising an exception.

Run this focused scanner fallback test if the complete suite cannot run on the Pi:

```bash
python -m unittest tests.test_face_scan.FaceScannerTests.test_angled_scanner_requests_yellow_when_bottom_is_ambiguous -v
```

## 4. Test the physical scanner

Load the existing configuration without printing its values:

```bash
source config.sh
```

For a USB camera:

```bash
python src/app.py \
  --scan-mode angled-sides \
  --backend opencv \
  --device 0 \
  --output scan_output \
  --database data/solve_history.db
```

For the Raspberry Pi camera:

```bash
python src/app.py \
  --scan-mode angled-sides \
  --backend picamera2 \
  --output scan_output \
  --database data/solve_history.db
```

Expected flow:

1. Green captures the upper and front faces.
2. Continue with the red, blue, and orange views.
3. If the concealed yellow face cannot be inferred unambiguously, the application requests a direct yellow-face scan.
4. The complete six-face cube is validated before a solution is produced.
5. Move guidance begins only after a valid scan.

Also verify keyboard capture, back/reset, cancellation, previous/next move navigation, and one complete physical solve.

## 5. Test background synchronisation

This test proves that a network problem does not freeze scanning or lose the local result.

1. Temporarily make the LAMP server unavailable by disconnecting the network or stopping Apache.
2. Complete or cancel one session.
3. Check the latest local rows:

```bash
sqlite3 data/solve_history.db \
  "SELECT session_id, terminal_status, synced FROM solve_runs ORDER BY finished_at DESC LIMIT 5;"
```

The offline session should exist locally with `synced=0`.

4. Keep the server offline and start the scanner again. Confirm that scanning, controls, and cancellation remain responsive while the earlier upload fails in the background.
5. Leave the application running, restore the LAMP server, and wait up to approximately 10 seconds.
6. Run the SQLite query again. The pending row should change to `synced=1`.
7. Confirm that the result appears once on the dashboard and that restarting the application does not create a duplicate upload.

A failed upload must never delete the local row or terminate the application. During shutdown, the application may wait for one bounded final attempt, up to four seconds; an unsuccessful row must remain pending for the next run.

## 6. Return this evidence

Send the team:

- Tester name, date, and tested commit.
- Raspberry Pi model, camera/backend, lighting conditions, and other equipment.
- Automated test result, including any failure or skipped test.
- Pass/fail results for camera capture, keyboard controls, cancellation, full solve, and yellow-face fallback.
- Evidence that the offline row was `synced=0`, then became `synced=1` and appeared on the dashboard after reconnection.
- Confirmation that the camera and controls stayed responsive while the server was offline.
- Exact error messages and reproduction steps for every failure.

Do not send credentials with this evidence.

For the full assessment evidence, record ten complete sessions across at least five known scrambles, at least 450 visible sticker classifications, at least 95% classification accuracy, and a capture-to-result time below five seconds for every view. Record the mean, maximum, and 95th percentile timing as well. Add all dated results and artefact references to [`docs/evidence-log.md`](evidence-log.md).

See [`docs/lamp-deployment.md`](lamp-deployment.md) for the server and dashboard setup.
