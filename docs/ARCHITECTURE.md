# Architecture: Why PinSheet Server Is Built This Way

This document explains the reasoning behind PinSheet Server's major design
decisions. It is not a how-to guide and not an API reference — for setup see the
[README](../README.md), and for the data model and stat definitions see
[STATS.md](STATS.md). The purpose here is understanding: why the system is shaped
the way it is, what each decision buys, and what it costs. Where the code does
not record the designer's intent, that is said plainly rather than guessed at.

The through-line is a single premise stated in the README tagline — *"Analogue
golf, digital stats — self-hosted."* Almost every choice below follows from
taking that premise seriously: a golfer keeps score on paper at the course, then
wants rich digital analysis afterward, on infrastructure they own. The tensions
that premise creates — fast transcription versus rich data, formal handicap
correctness versus a hobby-scale codebase, extensibility versus safety — are the
real subject of this document.

---

## L0: The shape of the system in one breath

PinSheet Server is a single-process Flask application that stores everything in
one SQLite file, renders HTML on the server, and computes golf statistics —
including a full World Handicap System (WHS) index — from a compact shorthand a
golfer transcribes off a physical scorecard. It is multi-user in the sense that
several golfers can share one instance and view each other's numbers, but every
write is scoped to the writer's own data. It can be extended by dropping Python
packages into a `plugins/` folder, though nothing in that folder runs until an
admin explicitly enables it.

Each of those clauses is a deliberate trade-off. The rest of this document takes
them one at a time.

---

## L1: The decisions and their trade-offs

### 1. Record-by-exception shorthand: capturing only the misses

The most distinctive data decision is that the five per-hole stats follow the
paper scorecard's *record-by-exception* convention — on paper, only misses are
written down and blanks mean hits. The app splits that convention across two
layers. **The calculation layer keeps the by-exception semantics**: a blank
stored value is a positive signal, and reading that code is the clearest way to
understand the design intent. In `source/calc/approach.py`, `calc_fir_percent`
counts a fairway as hit when `not h.fairway or h.fairway == "H"` — that is, an
empty value is treated identically to an explicit "hit" marker. The same
pattern recurs in `calc_gir_percent` and across the calc package (`approach.py`,
`scoring.py`). Absence is not missing data; absence is a positive signal.

**The entry layer does not** work by exception. The round-entry shorthand
requires an explicit code for fairway and GIR on every hole — `H` for a hit,
`N` for not-applicable, a direction code for a miss — and a blank fails
client-side validation (`validateShorthand` in `source/web/static/app.js`).
You write a code on every hole, not only on misses; the code either confirms
the hit or carries the *direction* of the miss, not merely its occurrence.

**What this optimizes for.** The split buys two things at once. The
by-exception *interpretation* keeps the data model faithful to the paper source
of truth: a fairway cell holding a miss code is exactly what the golfer wrote
on the card, and `N` carves out "not applicable" from the overloaded meaning of
blank. This is a sound fit for the "analogue golf" premise: the scorecard is
the source of truth, and the app's job is to ingest it faithfully. (The precise
motivation is not documented in a design note in the repo, so this reading is
inferred from the data model and the calculation code, not from recorded
intent.) The trade-off of that faithfulness is that entry is not "type scores
and putts only": every hole's fairway and GIR get an explicit code, so even a
well-played round means typing `H H` on most holes.

Encoding the miss *direction* in the same cell is a second, subtler win. Because
a miss code already distinguishes left from right, short from long, in-bounds from
out-of-bounds, the shorthand does double duty: it is both the "did you hit it"
flag and the raw material for the miss-tendency and scrambling-by-direction stats
in `docs/STATS.md`. One character on paper becomes several derived metrics.

**What it costs.** The by-exception interpretation trades explicit storage for
an economical notation, and that has real consequences. At the data layer, a
blank cell is structurally indistinguishable from a cell the user simply forgot
to fill in — the system cannot tell "hit the fairway" from "didn't record the
fairway," because both are the empty string. The code leans into this by
*defining* blank as hit rather than trying to detect the ambiguity, which is the
only internally-consistent choice available, but it means the accuracy of the
"positive" stats rests entirely on disciplined data entry — and the entry
layer's explicit-code requirement (`H`/`N`/direction) is what makes that
discipline enforceable at the point of input. There is also a sentinel-value
cost: par-3 fairways and non-applicable cells need an explicit `N` code (see
the `h.fairway == "N"` and `gir == "N"` guards in `source/calc/approach.py`)
precisely because blank is already taken to mean "hit." The scheme spends a
special value to carve out "not-applicable" from the overloaded meaning of
emptiness.

### 2. The WHS handicap index: why best-8-of-20, and why all the extra rules

The handicap engine in `source/calc/handicap.py` is the most rule-dense part of
the codebase, and its complexity is not incidental — it is a faithful
implementation of the World Handicap System's Rule 5, which is itself the product
of decades of institutional wrestling with a genuinely hard problem: estimating a
golfer's *demonstrated potential* from a noisy, self-reported score history.

At its core the index is an average of the best 8 of a player's most recent 20
score differentials (`calc_handicap_index`, with `WHS_HANDICAP_WINDOW = 20` and
`count_table_n` selecting 8 at a full record). Every part of that sentence encodes
a deliberate statistical stance:

- **Why differentials rather than raw scores.** A score of 90 means something
  different on an easy course than a hard one. `calc_round_dif` normalizes each
  round against the tee's slope and rating (`(113 / slope) * (gross - rating)`),
  producing a course-independent measure so that rounds played anywhere can be
  compared on one axis. Without this, the index would reward playing easy courses.

- **Why *best* 8, not the average.** The handicap is meant to reflect what a
  golfer can do when playing well, not their typical result. Taking the lowest
  differentials is an explicit choice to measure potential over central tendency —
  which is also why a handicap "feels hard to play to."

- **Why a *window* of 20.** Golfers improve and decline. A lifetime average would
  anchor the number to a player they no longer are. The 20-round window makes the
  index track current form and lets old rounds age out.

The subtler rules exist to guard edge cases that a naive best-8-of-20 would get
wrong, and the code comments in `handicap.py` are unusually explicit about each:

- **The count table (`count_table_n`, `count_table_adjustment`, WHS Rule 5.2a).**
  A new player with only 3 or 5 acceptable rounds has no meaningful "best 8." The
  count table scales how many differentials to use down toward 1 for sparse
  records, and Rule 5.2a subtracts an adjustment (−2.0 at 3 rounds, −1.0 at 4 and
  6) to counteract the optimism of averaging a tiny sample. This guards the
  cold-start case where a single good round would otherwise swing the index
  wildly.

- **The soft cap and hard cap (`apply_handicap_cap`, WHS Rule 5.8).** Once a Low
  Handicap Index is established, the code limits how fast the index can rise: the
  amount above a +3.0 increase is halved (soft cap), and it can never exceed +5.0
  over the low (hard cap). This exists to resist both slumps and sandbagging — a
  temporarily bad stretch cannot inflate the handicap without bound.

- **Exceptional Score Reduction (`exceptional_reduction`, WHS Rule 5.9).** When a
  round comes in far below the index in effect at the time, the index is pulled
  down immediately (−1.0 for a 7-to-10-stroke gap, −2.0 beyond). This guards
  against a genuine leap in ability lagging behind because it would take many
  rounds to filter through the best-8 average on its own.

Two implementation details in this file reward attention because they reveal how
carefully the edge cases were considered. First, the window is defined in terms of
*eligible* differentials, not raw rounds: `calc_handicap_index` walks a
most-recent-first list and only counts rounds that pass `_is_eligible_diff_round`,
so an excluded or unscored round does not silently consume a window slot. The
docstring calls the alternative "a cross-user data-exposure footgun" in a related
context and is at pains to keep the window semantically precise. Second,
`exceptional_reduction` rounds the *gap itself* back to a tenth before comparing
against the 7.0/10.0 thresholds, with a comment explaining that IEEE-754 binary
floating point can render `20.0 - 13.0` as `6.999999999999998` and misclassify a
true 7.0 gap one bucket low. That is a designer who has been bitten by
floating-point representation error and has chosen to defend the rule boundaries
explicitly.

**What this costs.** The honest trade-off is complexity. There are three
independent windowing implementations that must agree —
`calc_handicap_index`, `calc_handicap_trend`, and the recompute loop in
`store.recompute_handicaps_for_user` — and the code comments repeatedly warn that
they do *not* delegate to one another (`calc_handicap_trend` "does NOT
call/delegate to `calc_handicap_index`"). The shared `WHS_HANDICAP_WINDOW`
constant is described as existing "so the two windowing implementations can't
drift apart," which is a candid admission that keeping them in sync is a standing
maintenance hazard. The system pays this complexity tax to be a *correct* handicap
engine rather than an approximate one — a defensible choice for an app whose whole
reason to exist is trustworthy numbers, but a real cost nonetheless. The
alternative, a simplified in-house formula, would have been far smaller and far
less defensible when a golfer compares PinSheet's index against an official one.

### 3. SQLite only, no external database

Every piece of durable state lives in one SQLite file (`data/pinsheet.db`),
opened in `source/database.py` and used through the function-per-operation layer
in `source/store.py`. There is no Postgres, no MySQL, no ORM, no connection pool —
`get_db()` opens a connection, the operation runs, and the connection closes
again, one call at a time.

This choice flows directly from "self-hosted." A golfer running this on a home
server, a Raspberry Pi, or a small VPS should not have to install and administer a
database server to track their rounds. SQLite makes the entire data layer a
single file, which is why the README can promise that "the `data/` directory is
portable — copy it between machines." Backup is a file copy; migration is a file
move; there is nothing to provision. `source/database.py` enables WAL mode
(`PRAGMA journal_mode=WAL`) so that reads do not block on writes, which matters
because handicap recomputation walks a user's whole history while the web UI is
still serving pages.

The most telling detail here is the CIFS/SMB fallback in `get_db()`. If the normal
open fails — which happens when `data/` sits on a network share that does not
support the byte-range locking SQLite's WAL relies on — the code catches the
`OperationalError` and reopens with `nolock=1` and `journal_mode=OFF`. The comment
names the exact scenario: a self-hoster keeping their data directory on a NAS.
This is a design that has clearly met its users where they actually run it, and
chose graceful degradation over a hard requirement.

**What it trades away.** SQLite with a connect-per-operation pattern is a
single-writer store. It is an excellent fit for one golfer, or a handful of
friends sharing an instance, but it is not built for many concurrent writers or
horizontal scaling. The `nolock` fallback in particular trades away crash-safety
guarantees (`journal_mode=OFF` disables the rollback journal) in exchange for
working at all on a network share — a reasonable bargain for a personal app, but
one that would be unacceptable for a multi-tenant service. This is the clearest
example of the whole system's scale assumption: single-user-to-small-group, not
SaaS. Choosing SQLite is choosing that scale on purpose.

### 4. Server-side rendering over a single-page app

PinSheet renders HTML on the server with Jinja2 templates and sends finished pages
to the browser, reaching for client-side JavaScript (Chart.js) only where it earns
its keep — the trend graphs on the dashboard. It is not a single-page application
(SPA) with a JSON API backing a React or Vue front end; the API keys and
`/api/...` surface exist for programmatic access, but the human-facing app is
server-rendered pages.

For this app's scale, server-side rendering is the lower-friction choice. The
stats are computed in Python anyway — the entire `source/calc/` package produces
numbers on the server — so rendering them into a template there avoids the
duplication a SPA imposes, where computation lives in Python but presentation
logic is reimplemented in JavaScript. A server-rendered app is also simpler to
self-host: there is no separate front-end build step, no bundler, no second
deployable artifact. The whole thing is "run one Python process," which is exactly
what the README's quick-start promises.

Chart.js is the considered exception. Trends are the one place where interactivity
genuinely adds understanding — hovering a point, reading a rolling average across
20 rounds — so the design pays the cost of client-side rendering *there* and
nowhere else. This is a "progressive enhancement" posture rather than a
"JavaScript-first" one: the page is complete without JavaScript, and the charts
enrich it.

**What it costs.** Server-side rendering means every interaction that changes what
you see is, in principle, a round-trip and a full page render rather than a
local state update. For a data-review app — where you load a page, read your
numbers, and move on — that latency profile is fine, arguably better than a SPA's
initial-bundle cost. It would feel worse for a highly interactive, app-like
experience with lots of in-place editing, which is simply not what PinSheet is.
The design fits the tool to its actual use rather than to a default fashion.

### 5. Convention-based, drop-in plugins

The plugin system in `source/plugin_loader.py` and `source/plugin.py` discovers
extensions by *convention* rather than registration. A plugin is a folder under
`plugins/` containing an `__init__.py` that defines a `plugin_info` dict and a
`register(app)` function. There is no central registry file to edit, no decorator
to apply, no entry-point manifest. The loader iterates the directory, and a plugin
that follows the naming and shape conventions is picked up. Hooks work the same
way: when the core fires `on_round_saved`, `fire_hook` in `source/plugin.py` looks
up an attribute of that exact name on each loaded plugin (`getattr(plugin, name,
None)`) and calls it if present. A plugin participates in a lifecycle event simply
by defining a function with the matching name.

The appeal of convention over a registry is that it makes the extension surface
*discoverable by shape*: dropping a correctly-structured folder into `plugins/` is
the entire installation, matching the same "just copy files" ergonomic as the
portable `data/` directory. The list of first-party plugins in the README
(pinsheet-balls, pinsheet-cartographer, and others) all follow this one mold.

But convention-based discovery collides head-on with security, and reading the
loader shows a design that has clearly been through that collision and come out
the other side hardened. Three decisions stand out:

- **Discovered but disabled by default.** `seed_plugin_state` inserts a new
  plugin as `enabled=0`, and `discover_plugins` treats a missing state row as
  "disabled" (default-deny). The comment is explicit that "plugin present on disk"
  is not "plugin trusted to execute" — an admin must enable it first. Convention
  makes plugins *easy to install*; the enable-gate ensures easy installation is
  not the same as automatic execution.

- **Metadata is read without executing code.** `_read_plugin_info_static` parses
  a disabled plugin's `__init__.py` with Python's `ast` module and
  `ast.literal_eval` rather than importing it, so the admin UI can list a plugin's
  name and version without crossing the trust boundary that `import` represents.
  Import — arbitrary top-level code execution — happens only for plugins an admin
  has explicitly enabled.

- **Hooks are allowlisted, not open.** `fire_hook` refuses to dispatch any name
  not in the fixed `ALLOWED_HOOKS` frozenset. Without that, the `getattr`-by-name
  mechanism would let the core invoke *any* attribute that happened to match an
  arbitrary hook string — the comment calls this "incidental attack surface
  amplification." The allowlist keeps the convenience of name-matched dispatch
  while bounding exactly which names are live.

**Why synchronous?** Hooks fire inline: `fire_hook` loops over plugins and calls
each one directly, wrapping the call in a try/except so a failing plugin logs a
warning instead of taking down the request. The code does not record an explicit
rationale for choosing synchronous over asynchronous or queued dispatch, so this
is an inference — but the shape is consistent with the rest of the system.
Synchronous, in-process hooks need no message broker, no background worker, and no
new moving parts, which fits the single-process, self-hosted deployment model
exactly. The trade-off is that a slow plugin hook slows the request that triggered
it, and the per-plugin try/except is the only isolation on offer — there is no
sandbox and no timeout. For a small set of trusted, admin-enabled plugins, that is
a proportionate design; it would not be safe for untrusted third-party code, which
is precisely why the enable-gate and allowlist exist upstream of it.

The larger story here is a system that started with the *ergonomic* choice
(convention, drop-in) and then retrofitted a *provenance model* (disabled by
default, static metadata reads, hook allowlist, and — per the loader's comments —
the removal of automatic `pip install`) once the security implications of
"executes any code you drop in a folder" became clear. The comments reference
ADRs and vulnerability IDs, which suggests these hardening steps were deliberate
responses to identified threats rather than original design. That history is worth
knowing: the plugin system's safety properties are a second layer laid over a
first-layer convenience decision, not something the convention gave for free.

### 6. Multi-user with read-only enforcement

PinSheet is multi-user in an asymmetric way that is easy to misread. Any logged-in
golfer can *view* aggregated numbers from every other golfer — the leaderboard
code in `source/routes/dashboard.py` freely reads other users' rounds via
`get_all_rounds(uid)` to build shared standings and challenge tables. Viewing is
communal. Writing is not.

The enforcement model for writes is structural rather than gate-based, and it is
worth understanding the difference. Rather than checking "is this my data?" at the
top of each write handler, the system makes it *impossible to name someone else's
data as the write target*. Every write route in `source/routes/rounds.py`,
`courses.py`, and `settings.py` passes `current_user.id` — the identity of the
logged-in session — into the store function, never a user id taken from the
request. `save_round`, `update_round`, `delete_round`, `save_settings`, and their
peers in `source/store.py` all take a `user_id` and scope their SQL to it
(`WHERE ... AND user_id = ?`). Because the writer's identity comes from the
authenticated session and not from a form field or URL parameter, there is simply
no channel through which a request could ask to modify another user's rounds.

The reads are what make the asymmetry deliberate: the very same
`get_all_rounds(user_id)` used to render your own dashboard is called with *other*
users' ids to build leaderboards and challenges. Read scoping is a parameter you
can vary; write scoping is pinned to the session. That is the whole model in one
sentence.

One store-layer comment makes the reasoning unusually visible. `get_all_rounds`
was changed to make `user_id` a *required* argument with no default, and the
comment explains why: a default of `1` "silently returned the first user's rounds
for any caller that forgot to pass an id — a cross-user data-exposure footgun in a
multi-user DB." The defense against cross-user leakage is to make the identity
impossible to omit, so a forgetful caller fails loudly rather than quietly
serving the wrong person's data.

The API-key path reinforces the same asymmetry from a different angle. In
`source/main.py`, a request authenticated by a bearer key is forced non-admin
(`user.is_admin = False`), and `store.get_user_by_api_key` re-applies that at the
store layer with the comment "keys are never admin — enforced at the store layer
too." The pattern throughout is defense in depth: the same invariant is asserted
at more than one layer so that a mistake at one does not become a breach.

**What this model buys and costs.** The benefit is that shared viewing — the
social, competitive heart of a group of friends tracking golf together — coexists
with strict write isolation, and the write isolation is enforced by construction
rather than by remembering to check. The cost is that "read-only" here means
"everyone can see everyone's data," which is a privacy stance appropriate to a
small, trusted, self-hosted group and not to strangers. There is no per-user
visibility control; viewing is all-or-nothing across the instance. As with the
SQLite decision, this is coherent only under the app's actual scale assumption — a
handful of golfers who chose to share one server — and the design does not pretend
otherwise.

---

## L2: The strategic thread — one scale assumption, honestly applied

Read together, these six decisions are not independent. They are the same
judgment applied repeatedly: *this is a self-hosted tool for one golfer or a small
trusted group, and every trade-off should be resolved in favor of that reader.*

- SQLite-only and the CIFS fallback assume small scale and personal hardware.
- Server-side rendering assumes a data-review workflow, not an app-like one.
- Shared viewing with session-pinned writes assumes a trusted group, not the
  open internet.
- Convention-based plugins assume an owner who wants easy extension — and the
  enable-gate assumes that owner must still consciously vouch for what runs.

The one place the system refuses to simplify is the handicap engine. There, the
scale assumption does not license approximation, because the entire value
proposition is a *trustworthy* number a golfer can hold up against an official
one. So the code pays full freight on WHS Rule 5 — count tables, soft and hard
caps, exceptional-score reduction, floating-point-defended thresholds, and three
carefully-synchronized windowing implementations — even though that is by far the
most expensive complexity in the codebase. That contrast is the most revealing
thing about the architecture: it is willing to be small and simple almost
everywhere, precisely so it can afford to be rigorous in the one place that
justifies the app's existence.

Where this document has inferred motivation from the implementation rather than
from a recorded design note, it has said so. The safest way to keep this document
honest over time is to treat the code comments in `source/calc/handicap.py`,
`source/store.py`, and `source/plugin_loader.py` as the primary sources — they are
unusually explicit about intent — and to update the inferred passages here
whenever a real design decision is written down elsewhere.
