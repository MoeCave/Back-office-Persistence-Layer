# Tournament Back-Office Manager — v2.0.0
## TCP client/server · SQLAlchemy persistence · Alembic

The back-office (CRUD for fighters, tournaments, categories, matches and
registrations) is split into two independent programs that talk over
blocking TCP sockets (`socket` from the standard library):

| Program | Entry point | Responsibility |
|---------|-------------|----------------|
| **Server** | `python server.py` | Listens on a port, serves **one client at a time**, routes requests to services, accesses the database through repositories |
| **Client** | `python client.py` | Connects to the server, sends requests and shows results in a Rich console UI. It never imports SQLAlchemy or the domain layer |

The communication protocol (framing, request/response format, every
supported operation and the error strategy) is documented in
**[docs/PROTOCOL.md](docs/PROTOCOL.md)**.

```
 client.py ──► src/client (menus, gateway)
                   │  JSON frames over TCP  (src/common/protocol.py)
                   ▼
 server.py ──► src/server/app.py        accept loop, one client at a time
                   └► router.py + routes.py   (resource, action) → handler
                         └► services/*        validation + business rules
                               └► converters.py / dto.py   ORM → DTO dicts
                                     └► src/domain (models, repositories,
                                                    UnitOfWork) → database
```

---

## Project structure

```
Back-office-Persistence-Layer/
├── client.py                    ← TCP client entry point
├── server.py                    ← TCP server entry point
├── docs/PROTOCOL.md             ← protocol documentation
├── alembic/ …                   ← migrations (001 initial, 002 last_update)
├── tests/                       ← pytest suite (no external services)
├── verify.py                    ← offline sanity check of the setup
└── src/
    ├── common/protocol.py       ← framing, envelopes, validation (shared)
    ├── client/
    │   ├── gateway.py           ← ServerGateway + resource proxies
    │   └── ui/                  ← Rich console menus and helpers
    ├── server/
    │   ├── app.py               ← blocking TCP server loop
    │   ├── router.py            ← dispatch + exception → error response
    │   ├── routes.py            ← declarative (resource, action) table
    │   ├── errors.py            ← NotFound / Validation / Conflict errors
    │   ├── validation.py        ← payload validation helpers
    │   ├── converters.py, dto.py← ORM → DTO (no ORM object leaves the server)
    │   └── services/            ← one service per aggregate
    └── domain/                  ← SQLAlchemy models, repositories, UnitOfWork
```

---

## Requirements

- Python 3.10+
- Docker Desktop (for PostgreSQL in development/production)
- Git

---

## First-time setup

### 1. Clone the repository

```bash
git clone https://github.com/BlowingFever/Back-office-Persistence-Layer.git
cd Back-office-Persistence-Layer
```

### 2. Create and activate virtual environment

```bash
python -m venv .venv
source .venv/bin/activate        # Mac / Linux
# .venv\Scripts\activate         # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` with your database credentials:

```env
APP_ENV=development

DATABASE_URL_TEST=sqlite:///./test_tournament.db
DATABASE_URL_DEVELOPMENT=postgresql+psycopg2://tournament_user:tournament_pass@localhost:5432/tournament_dev
DATABASE_URL_PRODUCTION=postgresql+psycopg2://tournament_user:tournament_pass@localhost:5432/tournament_prod
```

| `APP_ENV`     | Database used                           |
|---------------|-----------------------------------------|
| `test`        | SQLite (`DATABASE_URL_TEST`)            |
| `development` | PostgreSQL (`DATABASE_URL_DEVELOPMENT`) |
| `production`  | PostgreSQL (`DATABASE_URL_PRODUCTION`)  |

### 5. Start PostgreSQL with Docker

```bash
docker compose up -d
docker compose ps    # verify: tournament_db   Up   0.0.0.0:5432->5432/tcp
```

### 6. Run database migrations

```bash
alembic upgrade head
```

Expected output:
```
Running upgrade  -> 001_initial_schema, Initial schema creation
Running upgrade 001_initial_schema -> 002_add_last_update, Added last_update attribute
```

### 7. Verify the setup (optional)

```bash
python verify.py
```

Expected output:
```
🏆  All checks passed — project is correctly structured.
```

---

## Daily workflow

```bash
# 1. Start the database and activate the environment
docker compose up -d
source .venv/bin/activate

# 2. Terminal 1 — server (APP_ENV=test uses SQLite, no Docker needed)
python server.py                    # --host 127.0.0.1 --port 9000

# 3. Terminal 2 — client
python client.py                    # --host 127.0.0.1 --port 9000

# Run the unit tests (SQLite in memory, sockets mocked / loopback)
pytest

# Code style (PEP 8)
black src tests client.py server.py verify.py
ruff check src tests client.py server.py verify.py

# Stop Docker
docker compose down
```

---

## Alembic reference

```bash
alembic upgrade head        # apply all pending migrations
alembic current             # show current revision
alembic history             # full migration history
alembic downgrade -1        # downgrade one step
alembic downgrade base      # wipe schema
```

---

## Domain model summary

| Table                           | Type              | Description                             |
|---------------------------------|-------------------|-----------------------------------------|
| `fighter`                       | Aggregate root    | Competition participant                 |
| `medical_record`                | 1:1 → fighter     | Medical info per fighter                |
| `tournament`                    | Aggregate root    | Competition event                       |
| `tatami`                        | 1:N → tournament  | Competition mat                         |
| `category`                      | Aggregate root    | Division (belt + weight + gender)       |
| `fighter_category_registration` | N:M with attrs    | Fighter enrolled in category/tournament |
| `match`                         | 1:N → tournament  | Single bout between two fighters        |

---

## Repository methods

### FighterRepository
| Method | Description |
|--------|-------------|
| `add / get / get_all / update / delete / count` | CRUD |
| `get_by_last_name(name)` | Filter by last name |
| `get_by_belt_level(level)` | Filter by belt |
| `get_by_country(country)` | Filter by country |
| `get_by_email(email)` | Find by email |
| `get_paginated(page, page_size)` | Paginated list |
| `add_medical_record(...)` | Domain op: attach medical record |
| `approve_registration(...)` | Domain op: approve a registration |

### TournamentRepository
| Method | Description |
|--------|-------------|
| `add / get / get_all / update / delete / count` | CRUD |
| `get_by_name(name)` | Filter by name |
| `get_by_location(location)` | Filter by location |
| `get_active_tournaments()` | Future/ongoing events |
| `get_upcoming()` | Not yet started |
| `add_tatami_to_tournament(...)` | Domain op: create tatami |

### CategoryRepository
| Method | Description |
|--------|-------------|
| `add / get / get_all / update / delete / count` | CRUD |
| `get_by_name(name)` | Filter by name |
| `get_by_belt_level(level)` | Filter by belt |
| `get_by_gender(gender)` | Filter by gender |
| `get_by_weight_range(min, max)` | Filter by weight range |

### MatchRepository
| Method | Description |
|--------|-------------|
| `add / get / get_all / update / delete / count` | CRUD |
| `get_by_tournament(id)` | Matches in a tournament |
| `get_by_fighter(id)` | All matches for a fighter |
| `get_by_category(id)` | Matches in a category |
| `get_by_round(tournament_id, round)` | Matches in a specific round |
| `get_wins_by_fighter(id)` | Matches won by a fighter |

### RegistrationRepository
| Method | Description |
|--------|-------------|
| `add / get / get_all / update / delete / count` | CRUD |
| `get(tuple)` | Find by composite PK `(fighter_id, category_id, tournament_id)` |
| `get_by_tournament(id)` | Registrations for a tournament |
| `get_by_fighter(id)` | Registrations for a fighter |
| `get_pending_approvals(id)` | Unapproved registrations |

---

## Troubleshooting

**`connection refused` on port 5432**
Docker Desktop is not running. Run `docker compose up -d`.

**`alembic: command not found`**
Virtual environment is not active. Run `source .venv/bin/activate`.

**`ModuleNotFoundError: No module named 'src'`**
Run all commands from the project root directory, not from inside a subfolder.

**`ValueError: No DATABASE_URL configured`**
`.env` file is missing or `APP_ENV` is set to an environment with no URL.
Run `cp .env.example .env` and fill in the values.

**`Cannot connect to server at 127.0.0.1:9000`** (client)
The server is not running or uses another port. Start it with
`python server.py` (add `APP_ENV=test` to use SQLite) and pass the same
`--port` to the client.

**`Address already in use`** (server)
Another process holds the port. Use `python server.py --port 9001`.

**`pytest` finds no tests**
Run it from the project root; `pyproject.toml` points it to `tests/`.
