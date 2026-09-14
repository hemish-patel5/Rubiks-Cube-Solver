# LAMP deployment and acceptance

The repository contains a locally contract-tested LAMP path, but no live LAMP
host was available during implementation. Do not treat this page as deployment
evidence until every pending item below has been observed on the target hosts.
The PHP files require PHP 8.1 or newer with PDO MySQL enabled.

## Components

- `web/schema.sql`: MySQL table keyed by `session_id`.
- `web/api/sessions.php`: API-key-protected JSON `POST` endpoint with allowlisted
  fields, validation, prepared statements, and idempotent upsert.
- `web/index.php`: responsive, read-only solve summary dashboard.
- `src/storage/sync.py`: standard-library uploader with a three-second timeout.

Only terminal summaries are uploaded. Face photographs, BGR/HSV samples,
calibration evidence, and Raspberry Pi file paths stay local.

## Environment variables

Raspberry Pi application:

```sh
export RUBIKS_SYNC_URL='https://lamp-host.example/api/sessions.php'
export RUBIKS_SYNC_API_KEY='replace-with-a-long-random-secret'
```

Apache/PHP write endpoint:

```text
RUBIKS_API_KEY
RUBIKS_DB_HOST
RUBIKS_DB_PORT
RUBIKS_DB_NAME
RUBIKS_DB_USER
RUBIKS_DB_PASSWORD
```

Dashboard (use a MySQL account with `SELECT` permission only):

```text
RUBIKS_DB_HOST
RUBIKS_DB_PORT
RUBIKS_DB_NAME
RUBIKS_DB_READ_USER
RUBIKS_DB_READ_PASSWORD
```

Apply the schema with an administrator-controlled account, then grant the API
account only `INSERT` and `UPDATE`, and grant the dashboard account only
`SELECT`. Keep credentials outside the web root and source control.

## Retry behavior

SQLite rows begin with `synced=0`. If both Raspberry Pi sync variables are set,
the application attempts every pending row once at startup and once after the
new terminal row is saved. A timeout, HTTP error, invalid response, or server
failure leaves the row at `synced=0` for the next application run.

## Pending live acceptance

- [ ] Apply `web/schema.sql` to the target MySQL database.
- [ ] Configure HTTPS and verify the certificate from the Raspberry Pi.
- [ ] Configure separate least-privilege write and read-only MySQL accounts.
- [ ] Verify an authenticated upload and an unauthorized `401` response.
- [ ] Interrupt connectivity, verify `synced=0`, then verify retry and idempotent upsert.
- [ ] Open the dashboard on a LAN desktop and phone-sized browser.
- [ ] Confirm totals, completed solves, success rate, average moves/time, recent sessions, and errors.
