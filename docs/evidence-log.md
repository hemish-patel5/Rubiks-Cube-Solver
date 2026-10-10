# A+ verification evidence log

Do not mark a row as passed without a dated observation and retained artefact. Avoid
placing API keys, private messages, or private database content in evidence captures.

## Evidence record template

| Evidence ID | Date/time | Commit | Tester | Equipment/environment | Requirement(s) | Preconditions and steps | Expected | Actual measurement/result | Pass? | Artefact path/link |
|---|---|---|---|---|---|---|---|---|---|---|
| EV-AUTO-001 | 4 Oct 2026 | Feature working tree based on `c737ac3` | Codex, for team review | macOS development machine; project Python environment | NFR-05, NFR-07 | Run unit suite, Ruff format/lint, scoped mypy, compileall, CLI help, and whitespace check | All available checks pass | 45 tests passed; 1 live-dashboard test skipped because PHP CLI is not installed; Ruff, scoped mypy, compileall, CLI help, and `git diff --check` passed | Partial: PHP and target hardware remain pending | Retain terminal/PR check output with final branch review |
| EV-PI-001 |  |  |  | Raspberry Pi, camera, rotating platform, controlled lighting | FR-01 to FR-08 | Complete scan-to-guidance workflow | Valid solution and one local terminal row |  |  |  |
| EV-LAMP-001 |  |  |  | Pi plus live LAMP host | FR-09, NFR-06, NFR-07 | Start offline, complete run, restore server, retry | UI remains responsive; row stays local then uploads once |  |  |  |
| EV-DEMO-001 |  |  |  | Presentation setup | All | Rehearse the five-minute scenario | Complete, clear demonstration within five minutes |  |  |  |

## Accuracy dataset

Use at least five known scrambles and ten complete sessions. Score the 45
camera-visible final sticker positions once per session; inferred D-face stickers are not
camera-classification samples. This produces at least 450 visible decisions.

| Session | Scramble ID | Lighting/setup | Correct visible stickers | Visible stickers assessed | Accuracy | Ambiguous D fallback? | Evidence |
|---|---|---|---:|---:|---:|---|---|
| S01 |  |  |  | 45 |  |  |  |
| S02 |  |  |  | 45 |  |  |  |
| S03 |  |  |  | 45 |  |  |  |
| S04 |  |  |  | 45 |  |  |  |
| S05 |  |  |  | 45 |  |  |  |
| S06 |  |  |  | 45 |  |  |  |
| S07 |  |  |  | 45 |  |  |  |
| S08 |  |  |  | 45 |  |  |  |
| S09 |  |  |  | 45 |  |  |  |
| S10 |  |  |  | 45 |  |  |  |
| **Total** | At least 5 | Controlled |  | **>=450** | **Target >=95%** |  |  |

Accuracy is `total correct visible stickers / total visible stickers assessed * 100`.
Keep the ground-truth cube states or labelled photographs used for comparison.

## Performance dataset

Record capture-to-result duration for all four guided views in every session and every
direct yellow fallback. Report the sample count, mean, maximum, and 95th percentile.
Every individual duration must be below five seconds to satisfy the stated requirement.

| Metric | Result | Target | Pass? | Evidence/calculation |
|---|---:|---:|---|---|
| Sample count |  | >=40 plus fallbacks |  |  |
| Mean |  | Informational |  |  |
| Maximum |  | <5.0 s |  |  |
| 95th percentile |  | <5.0 s |  |  |

## Required scenario evidence

- [ ] Ambiguous hidden face requests a direct yellow-face scan.
- [ ] Invalid or physically impossible cube is rejected before solving.
- [ ] Camera and keyboard controls work on the Raspberry Pi.
- [ ] Full known scramble is scanned, solved, and guided to completion.
- [ ] Cancel creates exactly one `CANCELLED` local row.
- [ ] A new session can be started after cancellation/completion.
- [ ] Offline LAMP leaves a pending SQLite row while scanning remains responsive.
- [ ] Restored LAMP receives the row once and shows it on the dashboard.
- [ ] Application and worker shut down cleanly.
- [ ] Team approval evidence for CR-001 is attached.
