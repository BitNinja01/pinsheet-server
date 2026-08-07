# Sequence Diagrams

Mermaid diagrams for the core flows. Participant names map to real modules:
`routes/*` = `source/routes/…`, `store` = `source/store.py`,
`calc` = `source/calc/…`, `db` = SQLite via `source/database.py`.

---

## 1. Add a round (score entry) — `POST /api/rounds`

`source/routes/rounds.py :: api_rounds_post`

```mermaid
sequenceDiagram
    autonumber
    actor U as User (browser)
    participant R as routes/rounds.py
    participant RD as request_data
    participant C as calc/handicap
    participant S as store.py
    participant DB as SQLite

    U->>R: POST /api/rounds {date, course, tees, entry_mode, holes|gross_total}
    R->>RD: get_courses(), get_all_rounds_for_user()
    RD->>S: get_courses / get_all_rounds (cached on g)
    S->>DB: SELECT courses / rounds
    DB-->>S: rows
    S-->>RD: CourseData, [RoundData]

    Note over R: total_gross via _safe_int (blank/NaN → 0)
    Note over R: incomplete = detailed & scored_holes < expected<br/>no_score = total_gross ≤ 0<br/>skip_differential = incomplete or no_score

    alt detailed round
        R->>C: calc_handicap_index(prior rounds)
        C-->>R: current index (or None)
        R->>C: calc_course_handicap + calc_hole_scores (ESC / net double bogey)
        C-->>R: adjusted_gross
    end

    alt skip_differential
        Note over R: differential = "0"  (exclusion sentinel)
    else
        R->>C: calc_round_dif(slope, adjusted_gross, rating)
        C-->>R: differential
    end

    R->>C: calc_handicap_index(all rounds incl. new)
    C-->>R: computed_handicap (or None if < 3 eligible)
    R->>S: next_round_index(date, user)
    S->>DB: SELECT round_index WHERE date
    DB-->>S: used indices
    S-->>R: lowest free index
    R->>S: save_round(round, date, index, user)
    S->>DB: INSERT OR REPLACE INTO rounds
    R->>R: fire_hook("on_round_saved"), optional match link
    R-->>U: 200 {date, index, differential, redirect?}
```

**Why the guards exist:** a blank/non-numeric gross used to 500; a second
same-day round used to overwrite the first (index hardcoded `0`); an incomplete
round produced a wildly negative differential that poisoned the handicap. See
`INVARIANTS.md`.

---

## 2. Edit a round + recompute cascade — `PUT /api/rounds/<date>/<index>`

`source/routes/rounds.py :: api_rounds_put` → `store.recompute_handicaps_for_user`

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant R as routes/rounds.py
    participant C as calc/handicap
    participant S as store.py
    participant DB as SQLite

    U->>R: PUT /api/rounds/{date}/{index} {…, differential_override?}
    R->>S: get_all_rounds_for_user()
    S-->>R: [RoundData] (find old_round or 404)

    Note over R: recompute total_gross + adjusted_gross (same _safe_int + ESC)
    Note over R: skip_differential = incomplete or total_gross ≤ 0

    alt override provided
        Note over R: differential = override, differential_locked = true
    else old round locked
        Note over R: keep old differential (locked — do not recompute)
    else skip_differential
        Note over R: differential = "0"
    else
        R->>C: calc_round_dif(...)
        C-->>R: differential
    end

    opt date changed
        R->>S: delete_round(old date/index)
    end
    R->>S: save_round(...)
    S->>DB: INSERT OR REPLACE

    R->>S: recompute_handicaps_for_user(user)
    loop rounds chronological
        alt differential missing/"0" AND not locked AND not incomplete
            S->>C: refill differential from total_gross
        end
        S->>C: calc_handicap_index(trailing 20)
        S->>DB: UPDATE differential / computed_handicap
    end
    R-->>U: 200 {ok, differential}
```

> **Cascade gotcha (fixed):** the cascade treats `differential == "0"` as "needs
> computing" and refills it from `total_gross`. Without the
> `_is_incomplete_round` guard it would *resurrect* an incomplete round's poison
> differential on the next edit/exclude/delete. The guard keeps `"0"` sticky for
> incomplete rounds.

---

## 3. Handicap index computation — `calc.calc_handicap_index`

`source/calc/handicap.py`

```mermaid
sequenceDiagram
    autonumber
    participant Caller as routes / store
    participant H as calc/handicap
    Caller->>H: calc_handicap_index(rounds, include_9hole)
    H->>H: calc_effective_diffs(rounds)
    Note over H: drop excluded, drop differential in ("","0"),<br/>drop 9-hole unless include_9hole
    H->>H: last_n_rounds(20) → count_table_n(n)
    alt n < 3
        H-->>Caller: None  (not enough rounds)
    else
        H->>H: average of the best count_table_n(n) differentials
        H-->>Caller: handicap index (float, 1 dp)
    end
```

---

## 4. Score evaluation — report card & stats (read path)

`source/routes/rounds.py :: report_card`, `source/routes/stats.py`

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant R as routes (rounds/stats)
    participant RD as request_data
    participant C as calc (scoring/approach/putting/analysis)
    participant TPL as Jinja template

    U->>R: GET /rounds/{d}/{i}/report  (or /stats/{section})
    R->>RD: get_all_rounds_for_user(), get_courses()
    RD-->>R: [RoundData], {CourseData}
    R->>C: last_n_rounds(20) baseline
    par per metric
        R->>C: calc_round_vs_par / vs_rating
    and
        R->>C: calc_fir_percent / gir_percent / scramble_percent
    and
        R->>C: calc_*_putt_percent, calc_scoring_avg_by_par_type
    and
        R->>C: calc_big_number_rate (blow-ups), calc_penalties_per_round
    end
    C-->>R: this-round value + last-20 baseline per metric
    R->>TPL: render report_card.html / stats/*.html
    TPL-->>U: HTML (weakness = metric worse than baseline)
```

> There is **no** single strokes-gained/"fix this first" output — the category
> deltas are the signal, diagnosis is left to the reader. A ranked
> `calc_improvement_priorities()` would be the natural place to add one.

---

## 5. Login / auth

`source/routes/auth.py`, `main._load_user`

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant A as routes/auth.py
    participant S as store.py
    participant L as Flask-Login

    U->>A: POST /login {username, password}
    A->>S: get_user_by_username
    S-->>A: user row (bcrypt hash)
    A->>A: bcrypt.checkpw
    alt valid
        A->>L: login_user(User)
        L-->>U: 302 + session cookie
    else invalid
        A-->>U: 200 "Invalid username or password"
    end
    Note over A: rate-limited by Flask-Limiter
```

---

## 6. Create a course — `POST /api/courses`

`source/routes/courses.py`

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant CR as routes/courses.py
    participant S as store.py
    participant DB as SQLite
    U->>CR: POST /api/courses {name, tees{slope,rating,yardage}, holes{par,index}, par}
    CR->>S: save_course(name, data)
    S->>DB: INSERT OR REPLACE INTO courses (tees/holes as JSON)
    S-->>CR: ok
    CR-->>U: 200 {ok, name}
    Note over U,DB: Courses are the source of par/slope/rating<br/>that every differential + net calc depends on.
```
