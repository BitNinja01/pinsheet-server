/*
 * PinSheet SPA (/app) — vanilla JS, no build step, CSP-compliant.
 *
 * Security posture (see eng-frontend build notes for full detail):
 *  - No inline <script>, no inline event-handler attributes anywhere in
 *    index.html — every listener below is wired via addEventListener.
 *  - No eval / new Function / setTimeout-with-string. CSP script-src 'self'
 *    with no 'unsafe-inline'/'unsafe-eval' is satisfiable as-is.
 *  - All rendering goes through the `el()` DOM-builder helper, which only
 *    ever assigns untrusted strings via textContent / attribute values —
 *    never via innerHTML — so API-returned data (course names, round
 *    notes, etc.) cannot inject markup even though it originates from the
 *    same trust domain as this app.
 *  - The bearer API key lives in `state.apiKey` (memory) and is mirrored to
 *    sessionStorage only so a page reload within the same tab doesn't force
 *    re-entry on a phone. It is NEVER written to localStorage or a cookie,
 *    and is only ever sent as the `Authorization: Bearer <key>` header on
 *    same-origin `/api/v1/*` fetches — never logged, never included in any
 *    URL, never left in the DOM as anything but a masked display value.
 *  - Every API error is rendered from the RFC 9457 problem+json body
 *    (`title`/`detail`/`status`/`type`) via textContent, not innerHTML.
 */
(function () {
  "use strict";

  var API_BASE = "/api/v1";
  var KEY_STORAGE = "pinsheet_api_key";

  // ---------------------------------------------------------------------
  // API key storage (sessionStorage-backed, in-memory source of truth)
  // ---------------------------------------------------------------------

  function readStoredKey() {
    try {
      return sessionStorage.getItem(KEY_STORAGE) || "";
    } catch (e) {
      // Private-browsing / storage-disabled: fall back to memory-only.
      return "";
    }
  }

  var state = {
    apiKey: readStoredKey(),
  };

  function setApiKey(key) {
    state.apiKey = key || "";
    try {
      if (state.apiKey) {
        sessionStorage.setItem(KEY_STORAGE, state.apiKey);
      } else {
        sessionStorage.removeItem(KEY_STORAGE);
      }
    } catch (e) {
      // sessionStorage unavailable — key still works for this page's
      // lifetime via `state.apiKey`, just won't survive a reload.
    }
  }

  function maskKey(key) {
    if (!key) return "";
    if (key.length <= 10) return "••••••";
    return key.slice(0, 7) + "…" + key.slice(-4);
  }

  // ---------------------------------------------------------------------
  // DOM builder helper — textContent/attributes only, never innerHTML
  // ---------------------------------------------------------------------

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        var v = attrs[k];
        if (v === null || v === undefined) return;
        if (k === "class") {
          node.className = v;
        } else if (k === "dataset") {
          Object.keys(v).forEach(function (dk) {
            node.dataset[dk] = v[dk];
          });
        } else {
          // Deliberately excludes any "on*" handling — event wiring must
          // go through addEventListener, never an attribute, to keep this
          // file CSP-compliant (no inline handlers, no unsafe-inline need).
          node.setAttribute(k, v);
        }
      });
    }
    if (children !== undefined && children !== null) {
      var list = Array.isArray(children) ? children : [children];
      list.forEach(function (c) {
        if (c === null || c === undefined || c === false) return;
        node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
      });
    }
    return node;
  }

  function clearNode(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  // ---------------------------------------------------------------------
  // API client — RFC 9457 problem+json aware
  // ---------------------------------------------------------------------

  function ApiError(status, problem) {
    this.name = "ApiError";
    this.status = status;
    this.problem = problem || {};
    this.message = this.problem.title || ("Request failed (" + status + ")");
  }
  ApiError.prototype = Object.create(Error.prototype);

  function apiFetch(path, options) {
    options = options || {};
    var headers = {};
    Object.keys(options.headers || {}).forEach(function (k) {
      headers[k] = options.headers[k];
    });
    if (state.apiKey) headers["Authorization"] = "Bearer " + state.apiKey;
    if (options.body !== undefined && headers["Content-Type"] === undefined) {
      headers["Content-Type"] = "application/json";
    }

    return fetch(API_BASE + path, {
      method: options.method || "GET",
      headers: headers,
      body: options.body,
    }).catch(function () {
      throw new ApiError(0, {
        title: "Network error",
        detail: "Could not reach the server. Check your connection and try again.",
      });
    }).then(function (resp) {
      if (resp.status === 204) return null;
      var contentType = resp.headers.get("content-type") || "";
      var isJson = contentType.indexOf("json") !== -1;
      var parsePromise = isJson ? resp.json().catch(function () { return null; }) : Promise.resolve(null);
      return parsePromise.then(function (data) {
        if (resp.ok) return data;
        var isProblem = contentType.indexOf("application/problem+json") !== -1;
        var problem = isProblem && data ? data : {
          title: "Request failed (" + resp.status + ")",
          detail: (data && data.detail) || resp.statusText || "Unexpected error.",
          status: resp.status,
        };
        throw new ApiError(resp.status, problem);
      });
    });
  }

  // ---------------------------------------------------------------------
  // Global chrome: key panel + error banner
  // ---------------------------------------------------------------------

  var refs = {};

  function initChrome() {
    refs.appRoot = document.getElementById("app");
    refs.navEl = document.getElementById("app-nav");
    refs.viewEl = document.getElementById("view");
    refs.errorBanner = document.getElementById("error-banner");
    refs.keyToggle = document.getElementById("key-toggle");
    refs.keyPanel = document.getElementById("key-panel");
    refs.keyInput = document.getElementById("api-key-input");
    refs.keyShow = document.getElementById("key-show");
    refs.keySave = document.getElementById("key-save");
    refs.keyClear = document.getElementById("key-clear");
    refs.keyStatus = document.getElementById("key-status");

    refs.keyInput.value = state.apiKey;
    updateKeyStatus();

    refs.keyToggle.addEventListener("click", function () {
      var expanded = refs.keyToggle.getAttribute("aria-expanded") === "true";
      refs.keyToggle.setAttribute("aria-expanded", String(!expanded));
      refs.keyPanel.hidden = expanded;
    });

    refs.keyShow.addEventListener("click", function () {
      var showing = refs.keyInput.type === "text";
      refs.keyInput.type = showing ? "password" : "text";
      refs.keyShow.textContent = showing ? "show" : "hide";
    });

    refs.keySave.addEventListener("click", function () {
      setApiKey(refs.keyInput.value.trim());
      updateKeyStatus();
      clearError();
    });

    refs.keyClear.addEventListener("click", function () {
      setApiKey("");
      refs.keyInput.value = "";
      updateKeyStatus();
    });

    refs.appRoot.addEventListener("click", handleLinkClick);
    window.addEventListener("popstate", function () {
      renderRoute(location.pathname);
    });
  }

  function updateKeyStatus() {
    refs.keyStatus.textContent = state.apiKey
      ? "Key set for this tab (" + maskKey(state.apiKey) + ")."
      : "No key set — every /api/v1 call will fail with 401 until you add one.";
  }

  function showError(err) {
    var problem = (err && err.problem) || { title: "Unexpected error", detail: String((err && err.message) || err) };
    clearNode(refs.errorBanner);
    refs.errorBanner.appendChild(el("strong", { class: "error-title" }, problem.title || "Error"));
    if (problem.detail) refs.errorBanner.appendChild(el("p", { class: "error-detail" }, problem.detail));
    var metaBits = [];
    if (problem.status) metaBits.push("status " + problem.status);
    if (problem.type) metaBits.push(problem.type);
    if (metaBits.length) refs.errorBanner.appendChild(el("p", { class: "error-meta" }, metaBits.join(" · ")));
    var dismiss = el("button", { type: "button", class: "btn-ghost error-dismiss" }, "Dismiss");
    dismiss.addEventListener("click", clearError);
    refs.errorBanner.appendChild(dismiss);
    refs.errorBanner.hidden = false;
  }

  function clearError() {
    refs.errorBanner.hidden = true;
    clearNode(refs.errorBanner);
  }

  // ---------------------------------------------------------------------
  // Router
  // ---------------------------------------------------------------------

  var ROUTES = [
    { path: "/app", view: viewHome },
    { path: "/app/courses", view: viewCourses },
    { path: "/app/rounds", view: viewRounds },
    { path: "/app/rounds/new", view: viewRoundNew },
    { path: "/app/stats", view: viewStats },
  ];

  function normalizePath(p) {
    if (p.length > 1 && p.charAt(p.length - 1) === "/") return p.slice(0, -1);
    return p || "/app";
  }

  function matchRoute(pathname) {
    var norm = normalizePath(pathname);
    for (var i = 0; i < ROUTES.length; i++) {
      if (ROUTES[i].path === norm) return ROUTES[i].view;
    }
    return viewNotFound;
  }

  function setActiveNav(pathname) {
    var norm = normalizePath(pathname);
    var links = refs.navEl.querySelectorAll("a");
    for (var i = 0; i < links.length; i++) {
      var href = normalizePath(links[i].getAttribute("href") || "");
      links[i].classList.toggle("is-active", href === norm);
    }
  }

  function renderRoute(pathname) {
    clearError();
    setActiveNav(pathname);
    clearNode(refs.viewEl);
    var view = matchRoute(pathname);
    var result;
    try {
      result = view(refs.viewEl);
    } catch (err) {
      showError(err);
      return;
    }
    if (result && typeof result.catch === "function") {
      result.catch(function (err) {
        showError(err);
      });
    }
  }

  function navigate(path, opts) {
    opts = opts || {};
    if (opts.push !== false) history.pushState({}, "", path);
    renderRoute(path);
  }

  function handleLinkClick(e) {
    var a = e.target.closest ? e.target.closest("a") : null;
    if (!a) return;
    var href = a.getAttribute("href") || "";
    if (href.indexOf("/app") !== 0) return;
    if (a.hasAttribute("target")) return;
    e.preventDefault();
    navigate(href);
  }

  // ---------------------------------------------------------------------
  // Shared render helpers
  // ---------------------------------------------------------------------

  function fieldWrap(label, inputNode) {
    var wrap = el("div", { class: "field-group" });
    wrap.appendChild(el("label", { class: "field-label" }, label));
    wrap.appendChild(inputNode);
    return wrap;
  }

  function linkCard(href, title, sub) {
    var a = el("a", { class: "home-card", href: href });
    a.appendChild(el("div", { class: "home-card-title" }, title));
    a.appendChild(el("div", { class: "home-card-sub" }, sub));
    return a;
  }

  function loadingNote(root, text) {
    var node = el("p", { class: "view-sub" }, text);
    root.appendChild(node);
    return node;
  }

  // Defensive normalizers: the v1 backend contract for these envelopes was
  // not yet buildable/inspectable in this repo at SPA build time (no
  // source/routes/api_v1 package exists yet — see build notes). These
  // helpers accept a bare array, an {items:[...]}/{<key>:[...]} envelope,
  // or (for courses) a {name: {...}} map, so the SPA keeps working once the
  // backend lands even if the exact envelope differs from this guess.
  function normalizeList(data, key) {
    if (Array.isArray(data)) return data;
    if (data && Array.isArray(data[key])) return data[key];
    if (data && Array.isArray(data.items)) return data.items;
    return [];
  }

  function normalizeCourseList(data) {
    var list = normalizeList(data, "courses");
    if (list.length) return list.map(coerceCourse);
    if (data && typeof data === "object" && !Array.isArray(data)) {
      return Object.keys(data).map(function (name) {
        var c = data[name];
        return coerceCourse(Object.assign({ name: name }, (c && typeof c === "object") ? c : {}));
      });
    }
    return [];
  }

  function coerceCourse(c) {
    return { name: (c && c.name) || "", location: (c && c.location) || null };
  }

  function formatLocation(loc) {
    if (!loc || typeof loc !== "object") return "";
    var parts = [loc.city, loc["state/province"] || loc.state_province, loc.country].filter(function (v) { return !!v; });
    return parts.join(", ");
  }

  function humanizeKey(k) {
    return String(k).replace(/_/g, " ").replace(/\b\w/g, function (c) { return c.toUpperCase(); });
  }

  function todayIso() {
    var d = new Date();
    var mm = String(d.getMonth() + 1).padStart(2, "0");
    var dd = String(d.getDate()).padStart(2, "0");
    return d.getFullYear() + "-" + mm + "-" + dd;
  }

  function range(a, b) {
    var out = [];
    for (var i = a; i <= b; i++) out.push(i);
    return out;
  }

  function holeNumbersFor(selection) {
    if (selection === "front") return range(1, 9);
    if (selection === "back") return range(10, 18);
    return range(1, 18);
  }

  function holesLabel(sel) {
    if (sel === "front") return "Front 9";
    if (sel === "back") return "Back 9";
    return "18 holes";
  }

  // Maps this form's UI selection ("all"/"front"/"back") to the exact raw
  // string RoundCreateInSchema.holes_played expects on the wire. These are
  // NOT arbitrary -- they must match store._HOLES_NORM's keys
  // (store.py: {"": "all", "18": "all", "front9": "front", "back9": "back"})
  // so the server-side holes_selection the round round-trips into (rendered
  // via holesLabel() above, from RoundOutSchema.holes_selection) correctly
  // preserves front-vs-back, not just "18 holes" for everything.
  function holesPlayedValue(sel) {
    if (sel === "front") return "front9";
    if (sel === "back") return "back9";
    return "18";
  }

  // ---------------------------------------------------------------------
  // Views
  // ---------------------------------------------------------------------

  function viewHome(root) {
    root.appendChild(el("h1", { class: "view-title" }, "PinSheet"));
    root.appendChild(el("p", { class: "view-sub" },
      state.apiKey ? "Key set for this tab — ready to log a round." : "Add your API key above to load your data."));
    var grid = el("div", { class: "home-grid" });
    grid.appendChild(linkCard("/app/rounds/new", "Enter a round", "Log scores hole by hole, on the course."));
    grid.appendChild(linkCard("/app/rounds", "Your rounds", "Browse rounds you've logged."));
    grid.appendChild(linkCard("/app/courses", "Courses", "Browse the shared course catalog."));
    grid.appendChild(linkCard("/app/stats", "Stats", "Handicap index and scoring trends."));
    root.appendChild(grid);
  }

  function viewCourses(root) {
    root.appendChild(el("h1", { class: "view-title" }, "Courses"));
    var status = loadingNote(root, "Loading courses…");
    return apiFetch("/courses", { method: "GET" }).then(function (data) {
      status.remove();
      var courses = normalizeCourseList(data);
      if (!courses.length) {
        root.appendChild(el("p", { class: "empty-state" }, "No courses yet. You can type a new course name from the New Round screen."));
        return;
      }
      var list = el("ul", { class: "course-list" });
      courses.forEach(function (c) {
        var li = el("li", { class: "course-item" });
        li.appendChild(el("div", { class: "course-name" }, c.name || "(unnamed course)"));
        var loc = formatLocation(c.location);
        if (loc) li.appendChild(el("div", { class: "course-loc" }, loc));
        list.appendChild(li);
      });
      root.appendChild(list);
    }).catch(function (err) {
      status.remove();
      throw err;
    });
  }

  function roundListItem(r) {
    var li = el("li", { class: "round-item" });
    var top = el("div", { class: "round-item-top" });
    top.appendChild(el("span", { class: "round-date" }, r.date || "—"));
    top.appendChild(el("span", { class: "round-course" }, r.course || "—"));
    li.appendChild(top);
    var bottom = el("div", { class: "round-item-bottom" });
    bottom.appendChild(el("span", { class: "round-score" }, r.total_gross ? ("Gross " + r.total_gross) : "No score"));
    if (r.differential) bottom.appendChild(el("span", { class: "round-diff" }, "Diff " + r.differential));
    if (r.holes_selection) bottom.appendChild(el("span", { class: "round-holes" }, holesLabel(r.holes_selection)));
    li.appendChild(bottom);
    return li;
  }

  function viewRounds(root) {
    root.appendChild(el("h1", { class: "view-title" }, "Your rounds"));
    root.appendChild(el("a", { class: "btn-primary btn-block", href: "/app/rounds/new" }, "+ New round"));
    var status = loadingNote(root, "Loading rounds…");
    return apiFetch("/rounds", { method: "GET" }).then(function (data) {
      status.remove();
      var rounds = normalizeList(data, "rounds");
      if (!rounds.length) {
        root.appendChild(el("p", { class: "empty-state" }, "No rounds logged yet."));
        return;
      }
      var list = el("ul", { class: "round-list" });
      rounds.forEach(function (r) { list.appendChild(roundListItem(r)); });
      root.appendChild(list);
    }).catch(function (err) {
      status.remove();
      throw err;
    });
  }

  function viewRoundNew(root) {
    root.appendChild(el("h1", { class: "view-title" }, "New round"));

    var form = el("form", { class: "round-form", novalidate: "novalidate" });

    var dateInput = el("input", { type: "date", id: "rf-date", value: todayIso(), required: "required" });
    form.appendChild(fieldWrap("Date", dateInput));

    var courseSelect = el("select", { id: "rf-course-select", class: "select-input" },
      el("option", { value: "" }, "Loading courses…"));
    form.appendChild(fieldWrap("Course", courseSelect));

    var otherInput = el("input", { type: "text", id: "rf-course-other", placeholder: "New course name", maxlength: "200" });
    var otherWrap = el("div", { class: "field-group", hidden: "hidden", id: "rf-course-other-wrap" }, otherInput);
    form.appendChild(otherWrap);

    var teesInput = el("input", { type: "text", id: "rf-tees", placeholder: "e.g. Blue", maxlength: "100" });
    form.appendChild(fieldWrap("Tees", teesInput));

    var holesSelect = el("select", { id: "rf-holes", class: "select-input" }, [
      el("option", { value: "all" }, "18 holes"),
      el("option", { value: "front" }, "Front 9"),
      el("option", { value: "back" }, "Back 9"),
    ]);
    form.appendChild(fieldWrap("Holes played", holesSelect));

    form.appendChild(el("h2", { class: "view-subtitle" }, "Scores"));
    var gridWrap = el("div", { class: "hole-grid", id: "rf-hole-grid" });
    form.appendChild(gridWrap);

    var totalOut = el("div", { class: "round-total", id: "rf-total" }, "Total: —");
    form.appendChild(totalOut);

    var notesInput = el("textarea", { id: "rf-notes", rows: "3", maxlength: "2000", placeholder: "Notes (optional)" });
    form.appendChild(fieldWrap("Notes", notesInput));

    var submitBtn = el("button", { type: "submit", class: "btn-primary btn-block" }, "Save round");
    form.appendChild(submitBtn);

    root.appendChild(form);

    function updateTotal() {
      var inputs = gridWrap.querySelectorAll(".hole-gross");
      var total = 0, any = false;
      inputs.forEach(function (inp) {
        if (inp.value !== "") { any = true; total += parseInt(inp.value, 10) || 0; }
      });
      totalOut.textContent = any ? ("Total: " + total) : "Total: —";
    }

    function buildHoleGrid(selection) {
      clearNode(gridWrap);
      holeNumbersFor(selection).forEach(function (n) {
        var gross = el("input", {
          type: "number", inputmode: "numeric", min: "1", max: "20",
          class: "hole-gross", "data-hole": String(n), "aria-label": "Hole " + n + " gross",
        });
        var putts = el("input", {
          type: "number", inputmode: "numeric", min: "0", max: "12",
          class: "hole-putts", "data-hole": String(n), "aria-label": "Hole " + n + " putts",
        });
        var row = el("div", { class: "hole-row" }, [
          el("span", { class: "hole-num" }, "#" + n),
          el("label", { class: "hole-input-label" }, ["Gross", gross]),
          el("label", { class: "hole-input-label" }, ["Putts", putts]),
        ]);
        gridWrap.appendChild(row);
      });
      updateTotal();
    }

    gridWrap.addEventListener("input", function (e) {
      if (e.target.classList.contains("hole-gross")) updateTotal();
    });
    holesSelect.addEventListener("change", function () { buildHoleGrid(holesSelect.value); });
    buildHoleGrid("all");

    courseSelect.addEventListener("change", function () {
      otherWrap.hidden = courseSelect.value !== "__other__";
    });

    var coursesLoaded = apiFetch("/courses", { method: "GET" }).then(function (data) {
      var courses = normalizeCourseList(data);
      clearNode(courseSelect);
      courseSelect.appendChild(el("option", { value: "" }, courses.length ? "Select a course…" : "No courses yet"));
      courses.forEach(function (c) {
        if (!c.name) return;
        courseSelect.appendChild(el("option", { value: c.name }, c.name));
      });
      courseSelect.appendChild(el("option", { value: "__other__" }, "+ Enter a new course name"));
    }).catch(function (err) {
      clearNode(courseSelect);
      courseSelect.appendChild(el("option", { value: "__other__" }, "Type a course name below"));
      otherWrap.hidden = false;
      showError(err);
    });

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      clearError();

      var course = courseSelect.value === "__other__" ? otherInput.value.trim() : courseSelect.value;
      if (!course) { showError(new ApiError(0, { title: "Check the form", detail: "Course is required." })); return; }
      if (!dateInput.value) { showError(new ApiError(0, { title: "Check the form", detail: "Date is required." })); return; }

      var holes = {};
      gridWrap.querySelectorAll(".hole-row").forEach(function (row) {
        var g = row.querySelector(".hole-gross");
        var p = row.querySelector(".hole-putts");
        var entry = {};
        if (g.value !== "") entry.gross = g.value;
        if (p.value !== "") entry.putts = p.value;
        if (Object.keys(entry).length) holes[g.dataset.hole] = entry;
      });

      // Field names/values below MUST match RoundCreateInSchema exactly
      // (source/routes/api_v1/schemas.py) -- see Revision 1 build notes.
      //  - entry_mode: this form is the per-hole grid, which IS the
      //    schema's "detailed" mode ("score_only" is a different,
      //    total-only flow this UI doesn't offer). The backend recomputes
      //    total_gross server-side from `holes` for "detailed" mode, so
      //    total_gross/gross_total is never sent from here.
      //  - holes_played: NOT "holes_selection" (that field doesn't exist on
      //    the schema and was being silently dropped). Sent as the RAW
      //    store value store._HOLES_NORM expects ("18"/"front9"/"back9"),
      //    not a generic "9", so the front-vs-back distinction survives
      //    server-side normalization into RoundOutSchema.holes_selection.
      var payload = {
        date: dateInput.value,
        course: course,
        tees: teesInput.value.trim(),
        holes_played: holesPlayedValue(holesSelect.value),
        entry_mode: "detailed",
        holes: holes,
        notes: notesInput.value.trim(),
      };

      submitBtn.disabled = true;
      submitBtn.textContent = "Saving…";
      apiFetch("/rounds", { method: "POST", body: JSON.stringify(payload) }).then(function () {
        navigate("/app/rounds");
      }).catch(function (err) {
        showError(err);
        submitBtn.disabled = false;
        submitBtn.textContent = "Save round";
      });
    });

    return coursesLoaded;
  }

  function renderStatsObject(obj, depth) {
    depth = depth || 0;
    var wrap = el("div", { class: depth === 0 ? "stats-grid" : "stats-subgroup" });
    Object.keys(obj).forEach(function (key) {
      var value = obj[key];
      if (value !== null && typeof value === "object" && !Array.isArray(value)) {
        var section = el("div", { class: "stats-section" });
        section.appendChild(el("h2", { class: "view-subtitle" }, humanizeKey(key)));
        section.appendChild(renderStatsObject(value, depth + 1));
        wrap.appendChild(section);
      } else if (Array.isArray(value)) {
        var arrSection = el("div", { class: "stats-section" });
        arrSection.appendChild(el("h2", { class: "view-subtitle" }, humanizeKey(key)));
        arrSection.appendChild(el("p", { class: "stats-value" }, value.length ? value.map(String).join(", ") : "—"));
        wrap.appendChild(arrSection);
      } else {
        var card = el("div", { class: "stat-card" });
        card.appendChild(el("div", { class: "stat-label" }, humanizeKey(key)));
        card.appendChild(el("div", { class: "stat-value" },
          (value === null || value === undefined || value === "") ? "—" : String(value)));
        wrap.appendChild(card);
      }
    });
    return wrap;
  }

  function viewStats(root) {
    root.appendChild(el("h1", { class: "view-title" }, "Stats"));
    var status = loadingNote(root, "Loading stats…");
    return apiFetch("/stats", { method: "GET" }).then(function (data) {
      status.remove();
      if (!data || (typeof data === "object" && !Object.keys(data).length)) {
        root.appendChild(el("p", { class: "empty-state" }, "No stats yet — log a round to see your numbers."));
        return;
      }
      root.appendChild(renderStatsObject(data));
    }).catch(function (err) {
      status.remove();
      throw err;
    });
  }

  function viewNotFound(root) {
    root.appendChild(el("h1", { class: "view-title" }, "Not found"));
    root.appendChild(el("p", { class: "view-sub" }, "That screen doesn't exist."));
    root.appendChild(el("a", { class: "btn-primary", href: "/app" }, "Go home"));
  }

  // ---------------------------------------------------------------------
  // Boot
  // ---------------------------------------------------------------------

  document.addEventListener("DOMContentLoaded", function () {
    initChrome();
    renderRoute(location.pathname || "/app");
  });
})();
