# prizepicksapi (Python)

Python client for [prizepicksapi.com](https://prizepicksapi.com): live PrizePicks player-prop lines, goblin and demon tiers on each selection, recorded line history, the change feed, graded results and game logs. Standard library only, Python 3.9+.

prizepicksapi.com is an independent service operated by Stunning Couches LLC. It is not affiliated with or endorsed by PrizePicks.

```bash
pip install prizepicksapi
```

## Try it with no key

The `demo_*` methods call the keyless demo endpoints. They return fictional rows (`is_demo: true`) with the same fields as the live board, so you can write your parser first.

```python
from prizepicksapi import PrizePicksAPI

api = PrizePicksAPI(api_key="")
for p in api.demo_projections(league="NBA", limit=3)["data"]:
    print(p["player"]["name"], p["market"]["stat"], p["line"], p["selections"][0]["tier"], "opened", p["line_context"]["opening_line"])

for row in api.demo_payouts()["data"][:2]:
    print(row["entry_type"], row["picks"], "break-even", row["derived"]["break_even_probability"])

print(api.credit_cost("/api/v1/projections?league=NBA&limit=200")["quoted_credits"])
```

Output on 15 Nov 2026:

```
Jordan Ellis Points 27.5 standard opened 26.5
Marcus Cole Rebounds 8.5 standard opened 7.5
Devin Brooks Assists 6.5 standard opened 5.5
power 2 break-even 0.57735
power 3 break-even 0.55032
6
```

## Live data

Get a free key (100 credits a month, no card) at https://prizepicksapi.com/sign-up and export it:

```bash
export PRIZEPICKS_API_KEY=...
```

```python
from prizepicksapi import PrizePicksAPI

api = PrizePicksAPI(user_request="NBA points model: pull today's board")  # optional X-User-Request header

# Every current NBA points line, following cursors for you
for p in api.iter_projections(league="NBA", stat="Points", limit=200):
    tiers = {s["side"]: s["tier"] for s in p["selections"]}
    print(p["player"]["name"], p["line"], tiers)

# Only goblin lines, compact rows (up to 1,000 per page)
goblins = api.projections(league="NBA", tier="goblin", view="compact", limit=1000)

# Recorded moves for one projection
history = api.history(goblins["data"][0]["id"])

# Change feed: new, moved, pulled and restored lines. Store meta.next_cursor and resume from it.
feed = api.changes(league="NBA", limit=200)

# Graded results and hit rates
graded = api.results(league="NBA", date="2026-11-14")
rates = api.hit_rates(player="Victor Wembanyama", stat="Points")

# The board as it stood at a past moment
past = api.board(as_of="2026-11-10T23:00:00Z", league="NBA")

# CSV page for a spreadsheet
csv_text = api.export_csv(league="NBA", limit=200)
```

## Errors and limits

Non-2xx responses raise `APIError` with the API's stable `code` (for example `INVALID_API_KEY`). HTTP 429 raises `RateLimitError`. Per-minute limits (`RATE_LIMIT_EXCEEDED`) and 503s are retried up to `max_retries` times using the `Retry-After` header; a monthly quota (`MONTHLY_QUOTA_EXCEEDED`) is raised at once.

```python
from prizepicksapi import APIError, RateLimitError

try:
    api.projections(league="NBA")
except RateLimitError as e:
    print("limited:", e.code, e.retry_after)
except APIError as e:
    print(e.status, e.code, e.message)
```

## Methods

| Method | Endpoint | Key |
|---|---|---|
| `demo_projections`, `demo_history`, `demo_changes`, `demo_payouts`, `demo_coverage`, `demo_export_csv` | `/api/v1/demo/*` | no |
| `credit_cost(path)` | `/api/v1/credit-costs` | no |
| `projections`, `iter_projections` | `/api/v1/projections` | yes |
| `history(id)` | `/api/v1/projections/{id}/history` | yes |
| `trending` | `/api/v1/projections/trending` | yes |
| `changes` | `/api/v1/changes` | yes |
| `board(as_of)` | `/api/v1/board` | yes |
| `results`, `hit_rates`, `game_logs`, `training_set` | `/api/v1/results` etc. | yes |
| `coverage`, `payouts`, `compare`, `players`, `fixtures` | `/api/v1/*` | yes |
| `export_csv` | `/api/v1/export` | yes |
| `request(path, params)`, `paginate(path, params)` | any GET endpoint | |

Full reference: https://prizepicksapi.com/docs and https://prizepicksapi.com/openapi.json. Plans: https://prizepicksapi.com/pricing.

## Tests

```bash
python3 -m unittest discover -s tests            # mocked transport
PRIZEPICKS_LIVE_TEST=1 python3 -m unittest discover -s tests   # also calls the keyless demo endpoint
```

## License

MIT.
