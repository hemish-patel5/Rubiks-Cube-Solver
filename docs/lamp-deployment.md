# LAMP deployment and acceptance

The repository contains a locally contract-tested LAMP path, but no live LAMP
host was available during implementation. Do not treat this page as deployment
evidence until every pending item below has been observed on the target hosts.
The PHP files require PHP 8.1 or newer with PDO MySQL enabled.

## Components

- `web/schema.sql`: MySQL table keyed by `session_id`.
- `web/api/sessions.php`: API-key-protected JSON `POST` endpoint with allowlisted
  fields, validation, prepared statements, and idempotent upsert.
- `web/index.php`: responsive solve summary dashboard with
  session removal, CSRF protection, and pagination.
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

Dashboard (use a MySQL account with `SELECT` and `DELETE` permission):

```text
RUBIKS_DB_HOST
RUBIKS_DB_PORT
RUBIKS_DB_NAME
RUBIKS_DB_READ_USER
RUBIKS_DB_READ_PASSWORD
```

Apply the schema with an administrator-controlled account, then grant the API
account only `INSERT` and `UPDATE`, and grant the dashboard account only
`SELECT` and `DELETE`. A single account can also be used for both components with
`SELECT`, `INSERT`, `UPDATE`, and `DELETE`. Keep credentials outside the web root
and source control. The dashboard API key is currently hardcoded in server-side
PHP at the project owner's request.

## Deploying session removal

For the single-account Raspberry Pi setup described in the project walkthrough:

```sh
sudo mariadb rubiks
```

```sql
GRANT DELETE ON rubiks.solve_runs TO 'rubiks_app'@'127.0.0.1';
EXIT;
```

Deploy the updated dashboard (no schema migration or API endpoint change needed):

```sh
sudo install -m 644 web/index.php /var/www/html/rubiks/index.php
```

Open `/rubiks/` and use a session's **Remove** button. There is no unlock section
or browser login: every dashboard visitor can remove sessions. The server-side
`DASHBOARD_API_KEY` constant must match Apache's `RUBIKS_API_KEY`. The key is not
rendered in the HTML or stored in the database. Successful deletion redirects
to the dashboard and updates totals, averages, recent sessions, and recent
errors. When rotating the key, update the PHP constant as well as Apache and
the Pi's sync settings.

Removal affects the server database only. Local SQLite history, samples, and
photographs remain on the Pi. Records already marked `synced=1` are not retried
automatically. A manual re-upload, or a pending record not yet acknowledged by
the Pi, can recreate a deleted server record.

## Retry behavior

SQLite rows begin with `synced=0`. If both Raspberry Pi sync variables are set,
the application attempts every pending row once at startup and once after the
new terminal row is saved. A timeout, HTTP error, invalid response, or server
failure leaves the row at `synced=0` for the next application run.

## Pending live acceptance

- [ ] Apply `web/schema.sql` to the target MySQL database.
- [ ] Configure HTTPS and verify the certificate from the Raspberry Pi.
- [ ] Configure database permissions for uploads and dashboard reads/removal.
- [ ] Verify an authenticated upload and an unauthorized `401` response.
- [ ] Interrupt connectivity, verify `synced=0`, then verify retry and idempotent upsert.
- [ ] Open the dashboard on a LAN desktop and phone-sized browser.
- [ ] Confirm totals, completed solves, success rate, average moves/time, recent sessions, and errors.
- [ ] Remove a test session and verify its
      server row is absent and dashboard statistics update after refresh.
- [ ] Verify mismatched server/dashboard API keys and invalid CSRF tokens cannot
      delete rows; verify repeated deletion and deletion on the last page.
