# Tournament Back-Office — Communication Protocol (v2.0.0)

JSON-based request/response protocol over blocking TCP sockets
(Python `socket`). The server handles **one client at a time**; further
clients wait in the listen backlog until the current one disconnects.

* Default endpoint: `127.0.0.1:9000` (`python server.py --host H --port P`)
* Implementation: `src/common/protocol.py` (framing, envelopes,
  validation), `src/server/router.py` + `src/server/routes.py` (routing).

---

## 1. Transport and framing

TCP is a byte stream, so every message (request **and** response) is
framed with a length prefix:

```
+---------------------------+--------------------------------+
| 4 bytes, big-endian,      | UTF-8 encoded JSON object      |
| unsigned (`!I`) = N       | exactly N bytes                |
+---------------------------+--------------------------------+
```

| Rule | Value |
|------|-------|
| Header | 4 bytes, network byte order, unsigned 32-bit length of the body |
| Body encoding | UTF-8 JSON (non-JSON types such as `datetime` are sent as strings) |
| Maximum body | 64 MiB (`MAX_MESSAGE_BYTES`) |
| Pattern | strictly request → response, one response per request, in order |
| Connection | persistent; the client closes it to end the session |

---

## 2. Request format

```json
{
  "resource": "fighters",
  "action":   "get",
  "payload":  { "fighter_id": 1 }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `resource` | string | yes | One of `fighters`, `tournaments`, `categories`, `matches`, `registrations` |
| `action` | string | yes | Operation to run on the resource (section 4) |
| `payload` | object | no | Operation arguments; defaults to `{}`. Must be a JSON object |

Conventions:

* Identifiers are integers (numeric strings such as `"7"` are accepted).
* Dates are strings: `YYYY-MM-DD`, `YYYY-MM-DD HH:MM` or ISO-8601.
  Responses always use ISO-8601 (`2026-06-01T00:00:00`).
* Optional fields may be omitted or `null`. On `update`, only the keys
  present in the payload are modified.

---

## 3. Response format

Every request receives exactly one response with the same four keys.

**Success**

```json
{ "success": true, "data": { "...": "..." }, "error": null, "error_code": null }
```

**Error**

```json
{
  "success": false,
  "data": null,
  "error": "Fighter with id=99 not found.",
  "error_code": "NOT_FOUND"
}
```

`data` is a DTO (JSON object), a list of DTOs, or a small result object
such as `{"deleted": 3}`. ORM objects are never exposed.

---

## 4. Supported operations

"Required" fields are validated by the server; ids must be integers.

### 4.1 `fighters`

| Action | Payload | Returns |
|--------|---------|---------|
| `list` | – | list of fighters |
| `list_paginated` | `page` (≥1, default 1), `page_size` (1–100, default 10) | `{total, page, page_size, items}` |
| `get` | **`fighter_id`** | fighter + `medical_record`, `registrations`, `total_matches`, `total_wins` |
| `create` | **`first_name`**, **`last_name`**, `gender`, `belt_level`, `club_name`, `country`, `email` (unique), `phone`, `birth_date` | created fighter |
| `update` | **`fighter_id`**, any of the `create` fields | updated fighter |
| `delete` | **`fighter_id`** | `{"deleted": fighter_id}` |
| `search_by_last_name` | `last_name` | list |
| `search_by_belt_level` | `belt_level` | list |
| `search_by_country` | `country` | list |
| `search_by_email` | `email` | fighter or `null` |
| `upsert_medical_record` | **`fighter_id`**, `blood_type`, `doctor_name`, `conditions`, `notes` | medical record |
| `approve_registration` | **`fighter_id`**, **`category_id`**, **`tournament_id`** | registration |

### 4.2 `tournaments`

| Action | Payload | Returns |
|--------|---------|---------|
| `list` | – | list |
| `get` | **`tournament_id`** | tournament + `tatamis`, `total_matches`, `total_registrations`, `pending_registrations` |
| `create` | **`name`**, `location`, `start_date`, `end_date` (not before start), `max_fighters` | created tournament |
| `update` | **`tournament_id`**, any of the `create` fields | updated tournament |
| `delete` | **`tournament_id`** | `{"deleted": tournament_id}` |
| `search_by_name` | `name` | list |
| `search_by_location` | `location` | list |
| `list_active` | – | list |
| `list_upcoming` | – | list |
| `add_tatami` | **`tournament_id`**, **`name`**, `mat_number`, `area_size`, `is_active` | tatami |
| `list_tatamis` | **`tournament_id`** | list of tatamis |

### 4.3 `categories`

| Action | Payload | Returns |
|--------|---------|---------|
| `list` | – | list |
| `get` | **`category_id`** | category + `total_registrations`, `total_matches` |
| `create` | **`name`**, `belt_level`, `gender`, `weight_min_kg`, `weight_max_kg` | created category |
| `update` | **`category_id`**, any of the `create` fields | updated category |
| `delete` | **`category_id`** | `{"deleted": category_id}` |
| `search_by_name` | `name` | list |
| `search_by_belt_level` | `belt_level` | list |
| `search_by_gender` | `gender` | list |
| `search_by_weight_range` | `min_kg`, `max_kg` | list |

### 4.4 `matches`

| Action | Payload | Returns |
|--------|---------|---------|
| `list` | – | list |
| `get` | **`match_id`** | match + `fighters_info` (blue / red / winner names) |
| `create` | **`tournament_id`**, `category_id`, `blue_fighter_id`, `red_fighter_id`, `winner_id`, `round_number`, `duration_seconds`, `win_method`, `scheduled_time` | created match |
| `update` | **`match_id`**, `winner_id`, `win_method`, `duration_seconds` | updated match |
| `delete` | **`match_id`** | `{"deleted": match_id}` |
| `get_by_tournament` | **`tournament_id`** | list |
| `get_by_fighter` | **`fighter_id`** | `{matches, total_wins}` |
| `get_by_category` | **`category_id`** | list |
| `get_by_round` | **`tournament_id`**, **`round_number`** | list |
| `get_wins_by_fighter` | **`fighter_id`** | list |

### 4.5 `registrations`

A registration is identified by the composite key
`(fighter_id, category_id, tournament_id)`.

| Action | Payload | Returns |
|--------|---------|---------|
| `list` | – | list |
| `get` | the three key fields (required) | registration |
| `list_by_tournament` | **`tournament_id`** | list |
| `list_by_fighter` | **`fighter_id`** | list |
| `list_pending_approvals` | **`tournament_id`** | list |
| `create` | the three key fields, `weight_in_weight_kg`, `is_approved` | created registration |
| `update` | the three key fields, `weight_in_weight_kg`, `is_approved` | updated registration |
| `approve` | the three key fields | registration (approved) |
| `delete` | the three key fields | `{"deleted": true}` |

---

## 5. Error handling strategy

1. **Never crash, always answer.** Any request that can be framed gets a
   response; a bad request must not stop the server.
2. **Layered checks.** (a) framing/JSON, (b) envelope shape
   (`validate_request`), (c) router (resource/action), (d) service
   validation, (e) database constraints.
3. **Typed errors → `error_code`.** The router converts every exception
   into the envelope below; the client uses `error_code`, not the
   human-readable text, to decide what to do.
4. **No leaks.** Unexpected exceptions are logged on the server and the
   client only sees `Internal server error.`; SQL is never returned.

| `error_code` | Meaning | Typical causes |
|--------------|---------|----------------|
| `BAD_REQUEST` | Malformed request | not a JSON object, invalid JSON body, missing/ill-typed `resource`/`action`, unknown resource, `payload` not an object |
| `VALIDATION_ERROR` | Invalid data | missing required field, non-integer id, non-numeric weight, invalid date, `page_size` out of range, `end_date` before `start_date` |
| `UNKNOWN_ACTION` | Action not supported for the resource | typo in `action` |
| `NOT_FOUND` | Entity does not exist | `get`/`update`/`delete` with an unknown id |
| `CONFLICT` | Conflicts with existing data | duplicate email, existing registration, FK/unique constraint violated |
| `INTERNAL_ERROR` | Unexpected server failure | bug or database outage (details only in the server log) |

Connection-level behaviour:

| Situation | Server behaviour |
|-----------|------------------|
| Body is not valid UTF-8 JSON | Responds `BAD_REQUEST`, connection stays open |
| Declared length > 64 MiB | Responds `BAD_REQUEST`, then closes (stream misaligned) |
| Client disconnects (also mid-message) | Closes the socket, waits for the next client |
| Client silent longer than `--timeout` (default 900 s) | Closes the socket |
| `Ctrl+C` on the server | Logs and exits cleanly |

---

## 6. Examples

Request / response bodies (framing omitted):

```jsonc
// Create
→ {"resource":"fighters","action":"create",
   "payload":{"first_name":"Ana","last_name":"Lopez","email":"ana@x.com"}}
← {"success":true,"data":{"fighter_id":1,"first_name":"Ana", "...":"..."},
   "error":null,"error_code":null}

// Not found
→ {"resource":"fighters","action":"get","payload":{"fighter_id":99}}
← {"success":false,"data":null,
   "error":"Fighter with id=99 not found.","error_code":"NOT_FOUND"}

// Validation
→ {"resource":"fighters","action":"create",
   "payload":{"first_name":"B","last_name":"B","birth_date":"31/12/2000"}}
← {"success":false,"data":null,
   "error":"Field 'birth_date' must be a date like 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM'.",
   "error_code":"VALIDATION_ERROR"}

// Unknown resource
→ {"resource":"coaches","action":"list"}
← {"success":false,"data":null,
   "error":"Unknown resource 'coaches'. Valid resources: [...].",
   "error_code":"BAD_REQUEST"}
```

Minimal Python client (without the `ServerGateway` helper):

```python
import socket
from src.common.protocol import send_message, receive_message

with socket.create_connection(("127.0.0.1", 9000)) as sock:
    send_message(sock, {"resource": "fighters", "action": "list"})
    print(receive_message(sock))
```
