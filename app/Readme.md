# Linux Monitor API

A small [FastAPI](https://fastapi.tiangolo.com/) application that exposes
system metrics (CPU, memory, disk, network, processes, uptime) collected with
[psutil](https://psutil.io/), protected by a simple API key.

This is meant as a **starter template**: it's intentionally simple so you can
read through `main.py` top to bottom and understand every line, then extend
it as needed.

## 1. Requirements

- Python 3.9+ (works on any recent Linux distro)
- pip

## 2. Installation

```bash
# 1. Go into the project folder
cd py-dev/app

# 2. (Recommended) create a virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

## 3. Configure your API key

The app refuses to start if no API key is configured — this is on purpose,
so you never accidentally run it unprotected.

```bash
cp .env.example .env
# then edit .env and set a long, random value for MONITOR_API_KEY
```

You then need to load that variable into your shell before running the app.
The simplest way without extra tooling:

```bash
export $(grep -v '^#' .env | xargs)
```

(Alternatively just `export MONITOR_API_KEY="your-secret-value"` directly.)

## 4. Run the app

```bash
py app/main.py
```

- `--host 0.0.0.0` makes it reachable from other machines on your network.
  Use `127.0.0.1` instead if you only want local access.
- `--port 8000` is the port it listens on; change it if needed.
- Add `--reload` while developing, so the server restarts automatically when
  you edit `main.py`.

### for dev purposes only - disabled in prod ###  
Once running, open http://localhost:8000/docs in a browser: FastAPI
auto-generates interactive API documentation (Swagger UI) where you can try
out every endpoint. You'll need to click "Authorize" there and paste your API
key to test the protected routes.

## 5. Authentication

Every endpoint under `/api/` (except `/api/health`) requires an
`X-API-Key` HTTP header with the value you configured above. Requests
without it, or with an incorrect value, get an HTTP `401 Unauthorized`
response.

Example:

```bash
curl -H "X-API-Key: your-secret-value" http://localhost:8000/api/memory
```

## 6. Available endpoints

| Endpoint          | Description                                              | Shell equivalent      |
|-------------------|-----------------------------------------------------------|------------------------|
| `GET /api/health`   | Basic liveness check                | -                      |
| `GET /api/cpu`      | CPU core count, per-core usage %, frequency, load average | `top`, `mpstat`        |
| `GET /api/memory`   | RAM and swap usage                                        | `free -h`              |
| `GET /api/disk`     | Disk partitions/usage and IO counters                     | `df -h`, `iostat`      |
| `GET /api/network`  | Network IO counters and interface addresses/status        | `ifconfig`, `netstat`  |
| `GET /api/processes`| List of running processes (pid, name, cpu%, memory%...)   | `ps aux`               |
| `GET /api/system`   | Boot time, uptime, logged-in users                        | `uptime`, `who`        |

These map to the examples from the
[psutil shell equivalents guide](https://psutil.io/shell-equivalents/) —
feel free to browse it for ideas on how to add more endpoints (e.g. sensors,
open files, network connections...).

## 7. Project structure

```
linux-monitor-api/
├── main.py            # The whole application (routes + auth)
├── requirements.txt   # Python dependencies
├── .env.example        # Template for your API key
└── README.md
```

Everything lives in a single `main.py` file on purpose, to keep things easy
to follow. Once you're comfortable with it, a natural next step is splitting
it into modules (e.g. `auth.py`, `routers/cpu.py`, `routers/memory.py`...).

## 8. Ideas to go further

- **Run as a service**: use `systemd` so the API starts automatically on
  boot and restarts if it crashes.
- **Put it behind a reverse proxy** (nginx/Caddy) with HTTPS if you expose it
  outside your local network — the API key alone is not encryption.
- **Rate limiting**: add a library like `slowapi` to prevent abuse.
- **Multiple API keys / users**: store keys in a database instead of a
  single environment variable if different clients need different access
  levels.
- **Historical data**: periodically poll the endpoints and store results
  (e.g. in SQLite or a time-series DB) if you want graphs over time rather
  than just live snapshots.
## 9. Security notes

- Never commit your real `.env` file or API key to version control (a
  `.gitignore` entry for `.env` is a good idea).
- The API key is checked with a simple string comparison here for
  simplicity. For production use, consider a constant-time comparison
  (`secrets.compare_digest`) to reduce timing-attack risk, and consider
  rotating the key periodically.
- `psutil` needs to run with sufficient privileges to see all processes on
  the system; running the app as a restricted, dedicated user is generally
  fine, but some fields (e.g. for processes owned by other users) may show
  up as `null` or raise `AccessDenied` internally (already handled/skipped
  in `/api/processes`).
