# PinSheet Modern — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Flask + waitress web app that replaces the Textual TUI frontend while preserving the JSON data model and all stat calculations.

**Architecture:** Server-rendered Jinja2 pages for navigation, vanilla JS `fetch()` for inline mutations. Progressive disclosure wizards for round and course entry with auto-save drafts. Dark theme with 12 color themes via CSS custom properties.

**Tech Stack:** Python 3.10+, Flask, waitress, Jinja2, vanilla JS, Chart.js (vendored, no CDN), plain CSS with custom properties.

---

## Phase 1: Foundation (done)

- [x] Calc functions ported 1:1 (handicap, scoring, approach, putting)
- [x] Store layer ported (JSON file I/O)
- [x] Flask server shell with dashboard route
- [x] Dashboard stat panels rendering with real data
- [x] `base.html` shell template with navigation bar
- [x] `app.css` dark theme foundation
- [x] AGENTS.md, session memory framework, design spec

---

## Phase 2: Rounds

### Task 2.1: Dashboard — complete backend

**Files:**
- Modify: `main.py` — expand `dashboard()` route
- Modify: `web/templates/dashboard.html` — add rounds table

**Goal:** Dashboard route returns full data: stat panels + sorted recent rounds table + "this time last year" HI.

- [ ] **Step 1: Add dashboard API route**

  ```python
  # main.py — new route after dashboard()
  @app.route("/api/dashboard")
  def api_dashboard():
      settings = load_settings()
      courses = get_courses()
      all_rounds = get_all_rounds()
      include_9hole = settings.get("include_9hole", True)

      l20 = _last_n_rounds(all_rounds, courses, 20)
      b8 = _best_n_rounds(all_rounds, courses, 8)

      panels = {}
      for stat_def in STAT_CATALOG:
          key = stat_def["key"]
          if key not in DEFAULT_DASHBOARD_STATS:
              continue
          primary = stat_def["fn_primary"](l20, b8, courses, include_9hole)
          secondary = stat_def["fn_secondary"](l20, b8, courses, include_9hole)
          panels[key] = {
              "label": stat_def["label"],
              "value": f"{primary:.1f}{stat_def['suffix']}" if primary is not None else None,
              "secondary": f"{secondary:.1f}{stat_def['suffix']}" if secondary is not None else None,
              "blank_text": stat_def["blank_text"],
          }

      last_year_hi = _get_last_year_hi(all_rounds, include_9hole)

      return jsonify({"panels": panels, "last_year_hi": last_year_hi})
  ```

- [ ] **Step 2: Add `_get_last_year_hi` helper**

  ```python
  # main.py — new helper
  from datetime import date, timedelta

  def _get_last_year_hi(all_rounds, include_9hole):
      today = date.today()
      target = today.replace(year=today.year - 1)
      window_start = target - timedelta(days=60)
      window_end = target + timedelta(days=60)
      for r in all_rounds:
          if not r.get("differential") or r["differential"] == "0":
              continue
          d = r.get("date", "")
          if window_start.isoformat() <= d <= window_end.isoformat():
              window = _build_window(all_rounds, d)
              hi = calc_handicap_index(window, include_9hole)
              if hi is not None:
                  return hi
      return None

  def _build_window(all_rounds, target_date):
      return [r for r in all_rounds if r.get("date", "") <= target_date][:20]
  ```

- [ ] **Step 3: Add rounds table data to `/` route**

  ```python
  # main.py — inside dashboard() route, add before render_template:
  rounds_data = []
  for r in all_rounds[:20]:
      course = courses.get(r.get("course", ""), {})
      total = r.get("total_gross", "")
      par = course.get("par", 0)
      score_to_par = int(total) - int(par) if total and par and total != "0" else None
      rounds_data.append({
          "date": r.get("date", ""),
          "course": r.get("course", ""),
          "tees": r.get("tees", ""),
          "total": total,
          "score_to_par": score_to_par,
          "differential": r.get("differential", ""),
          "index": r.get("index", 0),
      })
  ```

  Update `render_template` call to pass `rounds=rounds_data`.

- [ ] **Step 4: Update dashboard.html with rounds table**

  ```html
  <!-- web/templates/dashboard.html — replace placeholder with -->
  <section class="recent-rounds">
      <h2>Recent Rounds</h2>
      {% if rounds %}
      <table class="data-table">
          <thead>
              <tr>
                  <th>Date</th>
                  <th>Course</th>
                  <th>Tees</th>
                  <th>Score</th>
                  <th>+/-</th>
                  <th>Diff</th>
              </tr>
          </thead>
          <tbody>
          {% for r in rounds %}
              <tr data-date="{{ r.date }}" data-index="{{ r.index }}"
                  class="clickable-row{% if r.in_handicap %} in-handicap{% endif %}">
                  <td>{{ r.date }}</td>
                  <td>{{ r.course }}</td>
                  <td>{{ r.tees }}</td>
                  <td>{{ r.total }}</td>
                  <td>{% if r.score_to_par is not none %}{{ '%+d'|format(r.score_to_par) }}{% else %}—{% endif %}</td>
                  <td>{{ r.differential }}</td>
              </tr>
          {% endfor %}
          </tbody>
      </table>
      {% else %}
      <p class="placeholder">No rounds yet. <a href="/rounds/new">Enter your first round</a>.</p>
      {% endif %}
  </section>
  ```

- [ ] **Step 5: Add CSS for rounds table**

  ```css
  /* web/static/app.css — append */
  .data-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.875rem;
  }
  .data-table th {
      text-align: left;
      color: var(--text-muted);
      font-weight: 500;
      padding: 0.5rem 0.75rem;
      border-bottom: 1px solid var(--border);
  }
  .data-table td {
      padding: 0.4rem 0.75rem;
      border-bottom: 1px solid rgba(255,255,255,0.04);
  }
  .clickable-row {
      cursor: pointer;
      transition: background 0.1s;
  }
  .clickable-row:hover {
      background: rgba(255,255,255,0.03);
  }
  .in-handicap {
      background: rgba(0,230,118,0.06);
  }
  ```

- [ ] **Step 6: Add click-to-navigate JS for table rows**

  ```javascript
  // web/static/app.js — new file
  document.addEventListener("DOMContentLoaded", function () {
      document.querySelectorAll(".clickable-row").forEach(function (row) {
          row.addEventListener("click", function () {
              var date = this.dataset.date;
              var index = this.dataset.index;
              window.location.href = "/rounds/" + date + "/" + index;
          });
      });
  });
  ```

  Link `app.js` in `base.html`:
  ```html
  <script src="/static/app.js"></script>
  ```

- [ ] **Step 7: Mark handicap-used rounds**

  ```python
  # main.py — inside dashboard(), after l20/b8 computation:
  handicap_dates = set()
  for r in get_best_n_rounds(all_rounds, include_9hole):
      handicap_dates.add((r.get("date"), r.get("index")))

  # In rounds_data loop, add:
  "in_handicap": (r.get("date"), r.get("index")) in handicap_dates,
  ```

  Add import: `from calc.handicap import get_best_n_rounds`

- [ ] **Step 8: Add "this time last year" to handicap panel**

  ```python
  # main.py — inside dashboard(), inside panels loop, after computing panels[key]:
  if key == "handicap" and last_year_hi is not None:
      panels[key]["subtitle"] = f"1y {last_year_hi:.1f}"
  ```

  In `dashboard.html`, render subtitle if present:
  ```html
  <div class="stat-secondary">
      {% if p.subtitle %}{{ p.subtitle }}{% else %}L20: {{ p.secondary }}{% endif %}
  </div>
  ```

- [ ] **Step 9: Run and verify**

  ```bash
  python main.py
  # Navigate to http://127.0.0.1:8420
  # Verify: 6 stat panels, rounds table with data, clickable rows
  ```

- [ ] **Step 10: Commit**

  ```bash
  git add main.py web/templates/dashboard.html web/static/app.css web/static/app.js
  git commit -m "feat: complete dashboard with rounds table and last-year HI"
  ```

### Task 2.2: Round entry wizard — core shell

**Files:**
- Create: `web/templates/round_entry.html`
- Modify: `main.py` — add `/rounds/new` route

**Goal:** Multi-step progressive disclosure form with auto-save draft. First pass: all 8 steps visible, stepped navigation, draft save/resume.

- [ ] **Step 1: Add route handler**

  ```python
  # main.py — new route
  @app.route("/rounds/new")
  def round_entry():
      settings = load_settings()
      courses = get_courses()
      return render_template("round_entry.html", settings=settings, courses=courses)
  ```

- [ ] **Step 2: Create round_entry.html shell**

  ```html
  {% extends "base.html" %}
  {% block content %}
  <div class="wizard" id="round-wizard">
      <h1 class="wizard-title">New Round</h1>

      <div class="wizard-step" data-step="date">
          <label class="step-label">Date</label>
          <input type="date" class="step-input" id="round-date"
                 value="{{ today|default('') }}">
      </div>

      <div class="wizard-step" data-step="course">
          <label class="step-label">Course</label>
          <select class="step-input" id="round-course">
              <option value="">Select course...</option>
              {% for name, course in courses.items() %}
              <option value="{{ name }}">{{ name }}</option>
              {% endfor %}
          </select>
      </div>

      <div class="wizard-step" data-step="tee" style="display:none">
          <label class="step-label">Tees</label>
          <select class="step-input" id="round-tee">
              <option value="">Select tees...</option>
          </select>
      </div>

      <div class="wizard-step" data-step="holes" style="display:none">
          <label class="step-label">Holes Played</label>
          <div class="radio-group">
              <label><input type="radio" name="holes_played" value="18" checked> Full 18</label>
              <label><input type="radio" name="holes_played" value="front9"> Front 9</label>
              <label><input type="radio" name="holes_played" value="back9"> Back 9</label>
          </div>
      </div>

      <div class="wizard-step" data-step="transport" style="display:none">
          <label class="step-label">Transport</label>
          <div class="radio-group">
              <label><input type="radio" name="transport" value="" checked> N/A</label>
              <label><input type="radio" name="transport" value="walking"> Walking</label>
              <label><input type="radio" name="transport" value="riding"> Riding</label>
          </div>
      </div>

      <div class="wizard-step" data-step="entry_mode" style="display:none">
          <label class="step-label">Entry Mode</label>
          <div class="radio-group">
              <label><input type="radio" name="entry_mode" value="detailed" checked> Detailed (hole-by-hole)</label>
              <label><input type="radio" name="entry_mode" value="score_only"> Score Only</label>
          </div>
      </div>

      <div class="wizard-step" data-step="holes_detail" style="display:none">
          <label class="step-label">Hole Scores</label>
          <div id="scorecard-area"></div>
      </div>

      <div class="wizard-step" data-step="notes" style="display:none">
          <label class="step-label">Notes</label>
          <textarea class="step-input" id="round-notes" rows="3"
                    placeholder="Optional: weather, swing thoughts, course conditions..."></textarea>
          <button class="btn btn-accent" id="submit-round">Save Round</button>
      </div>
  </div>

  <div id="draft-resume" class="draft-notice" style="display:none">
      <p>You have an unfinished round draft.</p>
      <button class="btn btn-accent" id="draft-resume-btn">Resume</button>
      <button class="btn" id="draft-discard-btn">Discard</button>
  </div>
  {% endblock %}
  ```

- [ ] **Step 3: Add wizard CSS**

  ```css
  /* web/static/app.css — append */
  .wizard {
      max-width: 640px;
      margin: 0 auto;
  }
  .wizard-title {
      font-size: 1.25rem;
      margin-bottom: 1.5rem;
  }
  .wizard-step {
      margin-bottom: 1.5rem;
      padding: 1rem;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 6px;
  }
  .step-label {
      display: block;
      font-size: 0.75rem;
      color: var(--accent);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 0.5rem;
  }
  .step-input {
      width: 100%;
      padding: 0.5rem 0.75rem;
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 4px;
      color: var(--text);
      font-size: 0.875rem;
  }
  .step-input:focus {
      outline: none;
      border-color: var(--accent);
  }
  textarea.step-input {
      resize: vertical;
      font-family: var(--font);
  }
  .radio-group {
      display: flex;
      gap: 1.5rem;
  }
  .radio-group label {
      font-size: 0.875rem;
      color: var(--text);
      cursor: pointer;
  }
  .radio-group input[type="radio"] {
      margin-right: 0.25rem;
      accent-color: var(--accent);
  }
  select.step-input {
      appearance: none;
      cursor: pointer;
  }
  .btn {
      padding: 0.5rem 1rem;
      border: 1px solid var(--border);
      border-radius: 4px;
      background: var(--surface);
      color: var(--text);
      font-size: 0.875rem;
      cursor: pointer;
  }
  .btn-accent {
      background: var(--accent);
      color: var(--bg);
      border-color: var(--accent);
      font-weight: 600;
  }
  .draft-notice {
      max-width: 640px;
      margin: 2rem auto;
      padding: 1rem;
      background: var(--surface);
      border: 1px solid var(--accent);
      border-radius: 6px;
      text-align: center;
  }
  ```

- [ ] **Step 4: Add wizard JS — progressive disclosure**

  ```javascript
  // web/static/app.js — append
  (function () {
      var wizard = document.getElementById("round-wizard");
      if (!wizard) return;

      var stepCourse = document.getElementById("round-course");
      var stepTee = document.getElementById("round-tee");
      var teeParent = document.querySelector('[data-step="tee"]');
      var holesParent = document.querySelector('[data-step="holes"]');
      var transportParent = document.querySelector('[data-step="transport"]');
      var entryParent = document.querySelector('[data-step="entry_mode"]');
      var detailParent = document.querySelector('[data-step="holes_detail"]');
      var notesParent = document.querySelector('[data-step="notes"]');

      // Courses data from template
      var coursesData = {};

      stepCourse.addEventListener("change", function () {
          var name = this.value;
          if (!name) {
              teeParent.style.display = "none";
              holesParent.style.display = "none";
              return;
          }
          var course = coursesData[name];
          stepTee.innerHTML = '<option value="">Select tees...</option>';
          if (course && course.tees) {
              Object.keys(course.tees).forEach(function (t) {
                  var td = course.tees[t];
                  var label = t;
                  if (td.yardage) label += " (" + td.yardage + "y)";
                  stepTee.innerHTML += '<option value="' + t + '">' + label + '</option>';
              });
          }
          teeParent.style.display = "block";
      });

      stepTee.addEventListener("change", function () {
          if (this.value) {
              holesParent.style.display = "block";
          }
      });

      document.querySelectorAll('input[name="holes_played"]').forEach(function (el) {
          el.addEventListener("change", function () {
              transportParent.style.display = "block";
          });
      });

      document.querySelectorAll('input[name="transport"]').forEach(function (el) {
          el.addEventListener("change", function () {
              entryParent.style.display = "block";
          });
      });

      document.querySelectorAll('input[name="entry_mode"]').forEach(function (el) {
          el.addEventListener("change", function () {
              if (this.value === "detailed") {
                  buildScorecard();
                  detailParent.style.display = "block";
              }
              notesParent.style.display = "block";
          });
      });
  })();
  ```

- [ ] **Step 5: Populate courses data in template**

  ```html
  <!-- web/templates/round_entry.html -- add after {% block content %} opening -->
  <script>
  window._courses = {{ courses|tojson }};
  </script>
  ```

  Update JS to use `window._courses`:
  ```javascript
  var coursesData = window._courses;
  ```

- [ ] **Step 6: Add draft save/resume JS**

  ```javascript
  // web/static/app.js — append (inside wizard IIFE)
  function saveDraft() {
      var draft = {
          date: document.getElementById("round-date").value,
          course: stepCourse.value,
          tees: stepTee.value,
          holes_played: document.querySelector('input[name="holes_played"]:checked')?.value || "",
          transport: document.querySelector('input[name="transport"]:checked')?.value || "",
          entry_mode: document.querySelector('input[name="entry_mode"]:checked')?.value || "",
          notes: document.getElementById("round-notes")?.value || "",
      };
      fetch("/api/drafts/round", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(draft),
      });
  }

  var draftTimer = null;
  wizard.addEventListener("change", function () {
      clearTimeout(draftTimer);
      draftTimer = setTimeout(saveDraft, 500);
  });

  // Check for existing draft on load
  fetch("/api/drafts/round")
      .then(function (r) { return r.json(); })
      .then(function (data) {
          if (data && data.date) {
              document.getElementById("draft-resume").style.display = "block";
              wizard.style.display = "none";
          }
      });

  document.getElementById("draft-resume-btn")?.addEventListener("click", function () {
      document.getElementById("draft-resume").style.display = "none";
      wizard.style.display = "block";
      fetch("/api/drafts/round")
          .then(function (r) { return r.json(); })
          .then(function (draft) {
              if (draft.date) document.getElementById("round-date").value = draft.date;
              if (draft.course) { stepCourse.value = draft.course; stepCourse.dispatchEvent(new Event("change")); }
              if (draft.tees) { stepTee.value = draft.tees; stepTee.dispatchEvent(new Event("change")); }
              // reveal all filled steps
              if (draft.course) teeParent.style.display = "block";
              if (draft.tees) holesParent.style.display = "block";
              if (draft.holes_played) transportParent.style.display = "block";
              if (draft.transport) entryParent.style.display = "block";
              if (draft.entry_mode) notesParent.style.display = "block";
          });
  });

  document.getElementById("draft-discard-btn")?.addEventListener("click", function () {
      fetch("/api/drafts/round", { method: "DELETE" }).then(function () {
          document.getElementById("draft-resume").style.display = "none";
          wizard.style.display = "block";
      });
  });
  ```

- [ ] **Step 7: Add draft API endpoints**

  ```python
  # main.py — new routes
  @app.route("/api/drafts/round", methods=["GET"])
  def api_draft_round_get():
      draft = load_round_draft()
      return jsonify(draft or {})

  @app.route("/api/drafts/round", methods=["PUT"])
  def api_draft_round_put():
      save_round_draft(request.get_json())
      return jsonify({"ok": True})

  @app.route("/api/drafts/round", methods=["DELETE"])
  def api_draft_round_delete():
      clear_round_draft()
      return jsonify({"ok": True})
  ```

- [ ] **Step 8: Compile and test**

  ```bash
  python -m py_compile main.py
  python main.py
  # Test: /rounds/new loads, course dropdown populates, steps reveal progressively
  ```

- [ ] **Step 9: Commit**

  ```bash
  git add main.py web/templates/round_entry.html web/static/app.css web/static/app.js
  git commit -m "feat: round entry wizard shell with progressive disclosure and draft save"
  ```

### Task 2.3: Round entry — scorecard grid and submit

**Files:**
- Modify: `main.py` — add `POST /api/rounds`, `GET /api/rounds/<date>/<index>`
- Modify: `web/static/app.js` — `buildScorecard()`, submit handler
- Modify: `web/templates/round_entry.html` — add save result redirect

**Goal:** Scorecard grid renders for detailed mode, totals auto-update, submit saves round and redirects.

- [ ] **Step 1: Add `buildScorecard()` to app.js**

  ```javascript
  // web/static/app.js — inside wizard IIFE
  function buildScorecard() {
      var area = document.getElementById("scorecard-area");
      var course = coursesData[stepCourse.value];
      var holes = course.holes;
      var tee = course.tees[stepTee.value];
      var holesPlayed = document.querySelector('input[name="holes_played"]:checked').value;
      var holeCount = holesPlayed === "18" ? 18 : 9;
      var startHole = holesPlayed === "back9" ? 10 : 1;

      var html = '<table class="data-table scorecard-input"><thead><tr>';
      html += '<th>Hole</th><th>Par</th><th>Yards</th>';
      html += '<th>Score</th><th>FW</th><th>GIR</th><th>Putts</th><th>Pen</th>';
      html += '</tr></thead><tbody>';

      for (var i = 0; i < holeCount; i++) {
          var holeNum = startHole + i;
          var h = holes[String(holeNum)];
          var par = h ? h.par : 0;
          var yds = tee && tee.yardages ? (tee.yardages[String(holeNum)] || "") : "";
          html += '<tr data-hole="' + holeNum + '">';
          html += '<td>' + holeNum + '</td>';
          html += '<td class="par">' + par + '</td>';
          html += '<td>' + (yds || "—") + '</td>';
          html += '<td><input type="number" class="hole-input hole-gross" min="1" max="20" size="2"></td>';
          html += '<td><select class="hole-input hole-fw"><option value="">—</option>'
               +  '<option value="H">H</option><option value="L">L</option><option value="R">R</option>'
               +  '<option value="OBL">OBL</option><option value="OBR">OBR</option>'
               +  (par === 3 ? '<option value="N">N</option>' : '')
               +  '</select></td>';
          html += '<td><select class="hole-input hole-gir"><option value="">—</option>'
               +  '<option value="H">H</option><option value="L">L</option><option value="R">R</option>'
               +  '<option value="S">S</option><option value="LO">LO</option>'
               +  '<option value="OBL">OBL</option><option value="OBR">OBR</option>'
               +  '<option value="OBS">OBS</option><option value="OBLO">OBLO</option>'
               +  '</select></td>';
          html += '<td><input type="number" class="hole-input hole-putts" min="0" max="10" value="0" size="2"></td>';
          html += '<td><input type="number" class="hole-input hole-pen" min="0" max="10" value="0" size="2"></td>';
          html += '</tr>';
      }

      html += '<tr class="totals-row"><td colspan="3">TOTALS</td>';
      html += '<td class="total-gross">—</td><td></td><td></td>';
      html += '<td class="total-putts">—</td><td class="total-pen">—</td>';
      html += '</tr></tbody></table>';

      area.innerHTML = html;

      // Auto-update totals
      area.querySelectorAll(".hole-gross,.hole-putts,.hole-pen").forEach(function (el) {
          el.addEventListener("input", updateTotals);
      });

      // Auto-save draft on scorecard change
      area.addEventListener("change", function () {
          clearTimeout(draftTimer);
          draftTimer = setTimeout(saveDraft, 500);
      });
  }

  function updateTotals() {
      var gross = 0, putts = 0, pen = 0;
      document.querySelectorAll(".hole-gross").forEach(function (el) {
          gross += parseInt(el.value) || 0;
      });
      document.querySelectorAll(".hole-putts").forEach(function (el) {
          putts += parseInt(el.value) || 0;
      });
      document.querySelectorAll(".hole-pen").forEach(function (el) {
          pen += parseInt(el.value) || 0;
      });
      var tg = document.querySelector(".total-gross");
      var tp = document.querySelector(".total-putts");
      var tn = document.querySelector(".total-pen");
      if (tg) tg.textContent = gross || "—";
      if (tp) tp.textContent = putts;
      if (tn) tn.textContent = pen;
  }
  ```

- [ ] **Step 2: Add submit handler to app.js**

  ```javascript
  // web/static/app.js — inside wizard IIFE, after buildScorecard definition
  document.getElementById("submit-round").addEventListener("click", function () {
      var scoreOnly = document.querySelector('input[name="entry_mode"]:checked').value === "score_only";
      var payload = {
          date: document.getElementById("round-date").value,
          course: stepCourse.value,
          tees: stepTee.value,
          holes_played: document.querySelector('input[name="holes_played"]:checked').value,
          transport: document.querySelector('input[name="transport"]:checked').value,
          entry_mode: document.querySelector('input[name="entry_mode"]:checked').value,
          notes: document.getElementById("round-notes").value,
      };

      if (scoreOnly) {
          var total = prompt("Enter total gross score:");
          if (!total) return;
          payload.gross_total = String(total);
      } else {
          payload.holes = {};
          document.querySelectorAll(".scorecard-input tbody tr[data-hole]").forEach(function (row) {
              var hole = row.dataset.hole;
              payload.holes[hole] = {
                  gross: row.querySelector(".hole-gross")?.value || "",
                  fairway: row.querySelector(".hole-fw")?.value || "",
                  gir: row.querySelector(".hole-gir")?.value || "",
                  putts: row.querySelector(".hole-putts")?.value || "0",
                  penalties: row.querySelector(".hole-pen")?.value || "0",
              };
          });
      }

      fetch("/api/rounds", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
      })
      .then(function (r) { return r.json(); })
      .then(function (data) {
          fetch("/api/drafts/round", { method: "DELETE" }).then(function () {
              window.location.href = "/rounds/" + data.date + "/" + data.index;
          });
      });
  });
  ```

- [ ] **Step 3: Add `POST /api/rounds` route**

  ```python
  # main.py — new route
  from calc.handicap import (
      calc_handicap_index, calc_course_handicap, calc_round_dif,
      calc_expected_9hole_dif, calc_hole_scores,
  )

  @app.route("/api/rounds", methods=["POST"])
  def api_rounds_post():
      data = request.get_json()
      date = data.get("date", "")
      course_name = data.get("course", "")
      tees_name = data.get("tees", "")

      courses = get_courses()
      course = courses.get(course_name, {})
      tees = course.get("tees", {}).get(tees_name, {})

      holes_sel = data.get("holes_played", "18")
      if holes_sel == "front9":
          holes_sel = "front"
      elif holes_sel == "back9":
          holes_sel = "back"
      else:
          holes_sel = "all"

      slope, rating = get_slope_rating(tees, holes_sel)

      # Build round dict (matching original format)
      golf_round = {
          "date": date,
          "course": course_name,
          "tees": tees_name,
          "holes_played": data.get("holes_played", "18"),
          "holes_selection": holes_sel,
          "transport": data.get("transport", ""),
          "entry_mode": data.get("entry_mode", "detailed"),
          "notes": data.get("notes", ""),
          "holes": data.get("holes", {}),
          "gross_total": data.get("gross_total", ""),
      }

      # Compute differential
      total_gross = 0
      if data.get("entry_mode") == "score_only":
          total_gross = int(data.get("gross_total", "0"))
          golf_round["total_gross"] = str(total_gross)
      elif data.get("holes"):
          for h in data["holes"].values():
              gross = int(h.get("gross", 0))
              total_gross += gross
          golf_round["total_gross"] = str(total_gross)

      adjusted_gross = total_gross
      differential = calc_round_dif(slope, adjusted_gross, rating)
      golf_round["differential"] = str(differential)

      # Compute handicap after
      all_rounds = get_all_rounds()
      all_rounds.insert(0, golf_round)
      settings = load_settings()
      new_hi = calc_handicap_index(all_rounds, settings.get("include_9hole", True))
      if new_hi is not None:
          golf_round["computed_handicap"] = str(new_hi)

      # Save
      save_round(golf_round, date, 0)
      index = 0

      return jsonify({"date": date, "index": index, "differential": differential})
  ```

- [ ] **Step 4: Compile and test**

  ```bash
  python -m py_compile main.py
  python main.py
  # Test: fill out round entry, submit, verify redirects to round detail
  ```

- [ ] **Step 5: Commit**

  ```bash
  git add main.py web/static/app.js web/templates/round_entry.html
  git commit -m "feat: round entry scorecard grid and submit"
  ```

### Task 2.4: Round detail / scorecard

**Files:**
- Create: `web/templates/round_detail.html`
- Modify: `main.py` — add `GET /rounds/<date>/<index>` route

**Goal:** Full scorecard view with color-coded cells, OUT/IN/TOT subtotals, summary bar, edit/delete buttons.

- [ ] **Step 1: Add route**

  ```python
  # main.py — new route
  @app.route("/rounds/<date>/<index>")
  def round_detail(date, index):
      courses = get_courses()
      rounds = get_all_rounds()
      round_data = None
      for r in rounds:
          if r.get("date") == date and str(r.get("index")) == str(index):
              round_data = r
              break
      if not round_data:
          return "Round not found", 404

      course = courses.get(round_data.get("course", ""), {})
      course_holes = course.get("holes", {})

      # Build hole rows
      holes = []
      front_gross = back_gross = front_par = back_par = 0
      front_putts = back_putts = 0
      hole_data = round_data.get("holes", {})
      hole_nums = sorted(hole_data.keys(), key=lambda x: int(x))

      for hn in hole_nums:
          h = hole_data[hn]
          hole_num = int(hn)
          par = int(course_holes.get(hn, {}).get("par", 0))
          gross = int(h.get("gross", 0)) if h.get("gross") else 0
          putts = int(h.get("putts", 0)) if h.get("putts") else 0
          pen = int(h.get("penalties", 0)) if h.get("penalties") else 0
          fw = h.get("fairway", "")
          gir = h.get("gir", "")

          if hole_num <= 9:
              front_gross += gross; front_par += par; front_putts += putts
          else:
              back_gross += gross; back_par += par; back_putts += putts

          holes.append({
              "num": hole_num, "par": par,
              "gross": gross, "gross_diff": gross - par if gross and par else None,
              "fw": fw, "gir": gir,
              "putts": putts, "penalties": pen,
              "is_par3": par == 3,
          })

      total_par = front_par + back_par
      total_gross = front_gross + back_gross

      return render_template("round_detail.html",
          round=round_data, course=course, holes=holes,
          front_nine={"gross": front_gross, "par": front_par, "putts": front_putts},
          back_nine={"gross": back_gross, "par": back_par, "putts": back_putts},
          total={"gross": total_gross, "par": total_par,
                 "diff": total_gross - total_par if total_par else 0},
          settings=load_settings(),
      )
  ```

- [ ] **Step 2: Create round_detail.html**

  ```html
  {% extends "base.html" %}
  {% block content %}
  <div class="round-detail">
      <div class="round-summary">
          <div class="summary-item"><span class="summary-label">Date</span> {{ round.date }}</div>
          <div class="summary-item"><span class="summary-label">Course</span> {{ round.course }}</div>
          <div class="summary-item"><span class="summary-label">Tees</span> {{ round.tees }}</div>
          <div class="summary-item"><span class="summary-label">Score</span> {{ total.gross }} ({% if total.diff > 0 %}+{% endif %}{{ total.diff }})</div>
          <div class="summary-item"><span class="summary-label">Diff</span> {{ round.differential }}</div>
          {% if round.computed_handicap %}
          <div class="summary-item"><span class="summary-label">HI After</span> {{ round.computed_handicap }}</div>
          {% endif %}
      </div>

      <div class="round-actions">
          <a href="/rounds/{{ round.date }}/{{ round.index }}/report" class="btn">Report Card</a>
          <button class="btn" id="btn-delete">Delete</button>
      </div>

      <table class="data-table scorecard-view">
          <thead>
              <tr>
                  <th>Hole</th><th>Par</th><th>Score</th>
                  <th>FW</th><th>GIR</th><th>Putts</th><th>Pen</th>
              </tr>
          </thead>
          <tbody>
          {% for h in holes %}
              {% if h.num == 10 %}
              <tr class="subtotal-row">
                  <td colspan="7">
                      OUT {{ front_nine.gross }} ({{ front_nine.par }}) &nbsp;
                      putts {{ front_nine.putts }}
                  </td>
              </tr>
              {% endif %}
              <tr class="hole-row{% if h.gross_diff is not none and h.gross_diff <= -1 %} birdie{% elif h.gross_diff is not none and h.gross_diff >= 2 %} double{% endif %}">
                  <td>{{ h.num }}</td>
                  <td>{{ h.par }}</td>
                  <td class="{% if h.gross_diff is not none and h.gross_diff <= -2 %}eagle{% elif h.gross_diff == -1 %}birdie-score{% elif h.gross_diff == 1 %}bogey-score{% elif h.gross_diff is not none and h.gross_diff >= 2 %}double-score{% endif %}">
                      {{ h.gross or "—" }}
                  </td>
                  <td class="fw-cell">{{ h.fw or "—" }}</td>
                  <td class="gir-cell">{{ h.gir if h.gir else ("—" if not h.is_par3 else "") }}</td>
                  <td class="{% if h.putts == 1 %}one-putt{% elif h.putts >= 3 %}three-putt{% endif %}">
                      {{ h.putts }}
                  </td>
                  <td class="{% if h.penalties > 0 %}has-penalty{% endif %}">
                      {{ h.penalties if h.penalties else "—" }}
                  </td>
              </tr>
          {% endfor %}
          <tr class="subtotal-row">
              <td colspan="7">
                  IN {{ back_nine.gross }} ({{ back_nine.par }}) &nbsp;
                  putts {{ back_nine.putts }} &nbsp;|&nbsp;
                  TOT {{ total.gross }} ({{ total.par }}) &nbsp;
                  putts {{ front_nine.putts + back_nine.putts }}
              </td>
          </tr>
          </tbody>
      </table>

      {% if round.notes %}
      <div class="round-notes">{{ round.notes }}</div>
      {% endif %}
  </div>

  <script>
  document.getElementById("btn-delete")?.addEventListener("click", function () {
      if (!confirm("Delete this round?")) return;
      fetch("/api/rounds/{{ round.date }}/{{ round.index }}", { method: "DELETE" })
          .then(function () { window.location.href = "/"; });
  });
  </script>
  {% endblock %}
  ```

- [ ] **Step 3: Add scorecard CSS**

  ```css
  /* web/static/app.css — append */
  .round-summary {
      display: flex;
      gap: 2rem;
      flex-wrap: wrap;
      margin-bottom: 1.5rem;
  }
  .summary-item {
      font-size: 0.875rem;
  }
  .summary-label {
      display: block;
      font-size: 0.7rem;
      color: var(--text-muted);
      text-transform: uppercase;
  }
  .round-actions {
      display: flex;
      gap: 0.75rem;
      margin-bottom: 1.5rem;
  }
  .scorecard-view th {
      text-align: center;
      width: 50px;
  }
  .scorecard-view td {
      text-align: center;
  }
  .subtotal-row td {
      padding: 0.5rem 0.75rem;
      color: var(--accent);
      font-weight: 600;
      font-size: 0.8rem;
      border-top: 1px solid var(--border);
  }
  .birdie { }
  .eagle { color: var(--accent); font-weight: 700; }
  .birdie-score { color: var(--accent); }
  .bogey-score { color: #ffa726; }
  .double-score { color: #ef5350; }
  .one-putt { color: var(--accent); font-weight: 700; }
  .three-putt { color: #ef5350; }
  .has-penalty { color: #ef5350; }
  .round-notes {
      margin-top: 1rem;
      padding: 0.75rem;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 4px;
      font-size: 0.875rem;
      color: var(--text-muted);
      font-style: italic;
  }
  ```

- [ ] **Step 4: Add DELETE round API endpoint**

  ```python
  # main.py — new route
  @app.route("/api/rounds/<date>/<index>", methods=["DELETE"])
  def api_rounds_delete(date, index):
      delete_round(date, index)
      return jsonify({"ok": True})
  ```

- [ ] **Step 5: Compile and test**

  ```bash
  python -m py_compile main.py
  python main.py
  # Test: navigate to a round detail page, verify scorecard renders with colors
  ```

- [ ] **Step 6: Commit**

  ```bash
  git add main.py web/templates/round_detail.html web/static/app.css
  git commit -m "feat: round detail scorecard with color-coded cells"
  ```

### Task 2.5: Report card

**Files:**
- Create: `web/templates/report_card.html`
- Modify: `main.py` — add `GET /rounds/<date>/<index>/report` route

**Goal:** Two-column comparison table (this round vs L20 avg) with colored delta arrows.

- [ ] **Step 1: Add route and render**

  ```python
  # main.py — new route
  @app.route("/rounds/<date>/<index>/report")
  def report_card(date, index):
      courses = get_courses()
      all_rounds = get_all_rounds()

      this_round = None
      for r in all_rounds:
          if r.get("date") == date and str(r.get("index")) == str(index):
              this_round = r
              break
      if not this_round:
          return "Round not found", 404

      l20 = [r for r in all_rounds[:20] if not r.get("excluded")]
      if this_round not in l20:
          l20.insert(0, this_round)
          l20 = l20[:20]

      # Stat comparisons: (label, this_value, l20_value, higher_better, suffix, precision)
      from calc.approach import calc_fir_percent, calc_gir_percent, calc_scramble_percent
      from calc.putting import calc_putts_per_round, calc_putts_per_gir, calc_one_putt_percent, calc_two_putt_percent, calc_three_putt_percent
      from calc.scoring import calc_par_or_better_percent, calc_big_number_rate, calc_scoring_average, calc_scoring_avg_by_par_type
      from calc.handicap import calc_handicap_index

      rows = [
          ("Score vs Par", _round_vs_par(this_round, courses), _avg_vs_par(l20, courses), False, "", 1),
          ("Score vs Rating", _round_vs_rating(this_round, courses), _avg_vs_rating(l20, courses), False, "", 1),
          ("Par or Better %", calc_par_or_better_percent([this_round], courses), calc_par_or_better_percent(l20, courses), True, "%", 1),
          ("Blow-up Rate", calc_big_number_rate([this_round], courses), calc_big_number_rate(l20, courses), False, "%", 1),
          ("FIR %", calc_fir_percent([this_round], courses), calc_fir_percent(l20, courses), True, "%", 1),
          ("GIR %", calc_gir_percent([this_round]), calc_gir_percent(l20), True, "%", 1),
          ("Putts / Rnd", calc_putts_per_round([this_round]), calc_putts_per_round(l20), False, "", 1),
          ("Putts per GIR", calc_putts_per_gir([this_round]), calc_putts_per_gir(l20), False, "", 1),
          ("1-Putt %", calc_one_putt_percent([this_round]), calc_one_putt_percent(l20), True, "%", 1),
          ("2-Putt %", calc_two_putt_percent([this_round]), calc_two_putt_percent(l20), True, "%", 1),
          ("3-Putt %", calc_three_putt_percent([this_round]), calc_three_putt_percent(l20), False, "%", 1),
          ("Scramble %", calc_scramble_percent([this_round], courses), calc_scramble_percent(l20, courses), True, "%", 1),
      ]

      # Par 3/4/5 averages
      par_this = calc_scoring_avg_by_par_type([this_round], courses)
      par_l20 = calc_scoring_avg_by_par_type(l20, courses)
      for p in [3, 4, 5]:
          rows.append((
              f"Par {p} Avg",
              par_this.get(p),
              par_l20.get(p),
              False, "", 2,
          ))

      from calc.scoring import calc_scoring_average
      penalty_this = _penalties_per_round([this_round])
      penalty_l20 = _penalties_per_round(l20)
      rows.append(("Penalties / Rnd", penalty_this, penalty_l20, False, "", 1))

      return render_template("report_card.html", rows=rows, round=this_round, settings=load_settings())
  ```

  Add helpers:
  ```python
  def _round_vs_par(round_data, courses):
      course = courses.get(round_data.get("course", ""), {})
      par = int(course.get("par", 0))
      total = int(round_data.get("total_gross", 0))
      return total - par if par and total else None

  def _avg_vs_par(rounds, courses):
      vals = [_round_vs_par(r, courses) for r in rounds]
      vals = [v for v in vals if v is not None]
      return sum(vals) / len(vals) if vals else None

  def _round_vs_rating(round_data, courses):
      course = courses.get(round_data.get("course", ""), {})
      tees = course.get("tees", {}).get(round_data.get("tees", ""), {})
      rating = float(tees.get("rating", 72))
      total = int(round_data.get("total_gross", 0))
      return total - rating if total else None

  def _avg_vs_rating(rounds, courses):
      vals = [_round_vs_rating(r, courses) for r in rounds]
      vals = [v for v in vals if v is not None]
      return sum(vals) / len(vals) if vals else None

  def _penalties_per_round(rounds):
      totals = []
      for r in rounds:
          if not r.get("holes"):
              continue
          pen = sum(int(h.get("penalties", "0")) for h in r["holes"].values())
          totals.append(pen)
      return sum(totals) / len(totals) if totals else None
  ```

- [ ] **Step 2: Create report_card.html**

  ```html
  {% extends "base.html" %}
  {% block content %}
  <h2>Report Card — {{ round.date }} at {{ round.course }}</h2>
  <table class="data-table report-card">
      <thead>
          <tr>
              <th>Stat</th><th>This Round</th><th>L20 Avg</th><th></th>
          </tr>
      </thead>
      <tbody>
      {% for label, this_val, l20_val, higher_better, suffix, precision in rows %}
          <tr>
              <td>{{ label }}</td>
              <td>{{ this_val|round(precision) if this_val is not none else "—" }}{{ suffix }}</td>
              <td>{{ l20_val|round(precision) if l20_val is not none else "—" }}{{ suffix }}</td>
              <td>
                  {% if this_val is not none and l20_val is not none and this_val != l20_val %}
                      {% set better = (this_val < l20_val) if not higher_better else (this_val > l20_val) %}
                      <span class="{% if better %}delta-good{% else %}delta-bad{% endif %}">
                          {{ "▲" if this_val > l20_val else "▼" }}
                      </span>
                  {% endif %}
              </td>
          </tr>
      {% endfor %}
      </tbody>
  </table>
  {% endblock %}
  ```

- [ ] **Step 3: Add report card CSS**

  ```css
  .delta-good { color: var(--accent); }
  .delta-bad { color: #ef5350; }
  .report-card td:last-child { width: 2rem; }
  ```

- [ ] **Step 4: Compile and test**

  ```bash
  python -m py_compile main.py
  python main.py
  # Test: navigate to /rounds/<date>/<index>/report
  ```

- [ ] **Step 5: Commit**

  ```bash
  git add main.py web/templates/report_card.html web/static/app.css
  git commit -m "feat: report card comparison table"
  ```

---

## Phase 3: Courses

### Task 3.1: Course list and detail

**Files:**
- Create: `web/templates/courses.html`
- Create: `web/templates/course_detail.html`
- Modify: `main.py` — add `/courses`, `/courses/<name>` routes, course API endpoints

### Task 3.2: Course entry wizard

**Files:**
- Create: `web/templates/course_entry.html`
- Modify: `main.py` — add `/courses/new` route, course draft API endpoints

---

## Phase 4: Stats

### Task 4.1: Stats screen backend

**Files:**
- Modify: `main.py` — add `/stats`, `/api/stats` routes

### Task 4.2: Stats screen frontend

**Files:**
- Create: `web/templates/stats.html`

---

## Phase 5: Settings & Polish

### Task 5.1: Settings page

**Files:**
- Create: `web/templates/settings.html`
- Modify: `main.py` — add `/settings` route, `PUT /api/settings`

### Task 5.2: Welcome screen

**Files:**
- Create: `web/templates/welcome.html`
- Modify: `main.py` — welcome-screen gate on dashboard route

### Task 5.3: GHIN export and season summary

**Files:**
- Create: `web/templates/ghin_export.html`
- Create: `web/templates/season_summary.html`
- Modify: `main.py` — add routes

---

## Phase 6: Distribution

### Task 6.1: Launcher scripts

**Files:**
- Create: `scripts/launchers/launch.sh`
- Create: `scripts/launchers/launch.bat`

### Task 6.2: dist.sh packaging

**Files:**
- Create: `scripts/dist.sh`
