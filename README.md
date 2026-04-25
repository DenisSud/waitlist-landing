# Citera Practice — landing + waitlist

Two static HTML pages and a small FastAPI backend that records waitlist
sign-ups in a local SQLite file.

## Files

```
citera/
├── index.html          # Landing page
├── waitlist.html       # Waitlist sign-up form
├── server.py           # FastAPI backend (also serves the HTML)
├── requirements.txt
└── citera.db           # Created automatically on first run
```

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate            # on Windows: .venv\Scripts\activate
pip install -r requirements.txt
python server.py
```

Open <http://localhost:8000/> — the landing page is served by FastAPI, and
the waitlist form posts to `POST /api/waitlist` on the same origin.

If you prefer to host the HTML elsewhere (Vercel, Netlify, your own static
host), edit `API_URL` at the top of the `<script>` block in `waitlist.html`
to point at your deployed backend.

## API

| Method | Path                  | Purpose                                |
|--------|-----------------------|----------------------------------------|
| POST   | `/api/waitlist`       | Add an email. Body: `{email, role?, domain?}` |
| GET    | `/api/waitlist/stats` | Public head-count                      |
| GET    | `/api/waitlist/list`  | Admin listing — requires `?token=...` matching the `CITERA_ADMIN_TOKEN` env var |

### Example

```bash
curl -X POST http://localhost:8000/api/waitlist \
  -H 'Content-Type: application/json' \
  -d '{"email":"ivanov@msu.ru","role":"postgrad","domain":"natural"}'
```

Response:

```json
{
  "ok": true,
  "ticket_id": "CT-2026-4827",
  "email": "ivanov@msu.ru",
  "created_date": "25.04.2026"
}
```

### Reading entries

Set an admin token before launching:

```bash
export CITERA_ADMIN_TOKEN="something-long-and-random"
python server.py
```

Then:

```bash
curl 'http://localhost:8000/api/waitlist/list?token=something-long-and-random'
```

Or just inspect the SQLite file directly:

```bash
sqlite3 citera.db "SELECT ticket_id, email, role, domain, created_at FROM waitlist ORDER BY id DESC;"
```

## Notes for production

- Replace `allow_origins=["*"]` in `server.py` with your real frontend
  domain once you deploy.
- Put the server behind a reverse proxy with HTTPS (Caddy, Nginx, Traefik).
- For higher write volume, swap SQLite for Postgres — only the
  `get_conn()` and DDL would need to change.
- Consider sending a confirmation email via SMTP from the
  `join_waitlist` handler before returning the response.
