/*
 * DOM behaviour test for mascot.js — run with Node + jsdom (v21, Node 18+):
 *
 *   cd plugins/leaderboard_mascots/tests
 *   npm install jsdom@21
 *   node dom_test.js
 *
 * The loader ignores this tests/ folder (see docs/PLUGINS.md §3), so it never
 * ships to the running server. It exists so the JS DOM behaviour is
 * re-verifiable, not just asserted. The Python contract (register/unregister,
 * static assets) is covered by tests/test_plugin_leaderboard_mascots.py.
 */
const fs = require("fs");
const { JSDOM } = require("jsdom");

const js = fs.readFileSync(__dirname + "/../static/mascot.js", "utf8");

// Mirror of the real dashboard_social.html board DOM (desktop + mobile),
// plus a header avatar OUTSIDE both containers that must NOT be touched.
const html = `<!doctype html><html><body>
  <div class="ps-avatar is-self">HDR</div>  <!-- header avatar, must be ignored -->

  <div class="desktop-table">
    <div style="display:grid;grid-template-columns:1fr;">
      <div style="display:flex;align-items:center;gap:12px;">
        <div>01</div>
        <div class="ps-avatar">AL</div>
        <div><div>Alice <span>you</span></div></div>
      </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr;">
      <div style="display:flex;align-items:center;gap:12px;">
        <div>02</div>
        <div class="ps-avatar">BO</div>
        <div><div>Bob</div></div>
      </div>
    </div>
  </div>

  <div class="mobile-cards">
    <div class="board-card">
      <div class="board-card-head">
        <span class="board-card-rank">01</span>
        <div class="ps-avatar">AL</div>
        <span class="board-card-name">Alice<span class="board-card-tag">you</span></span>
      </div>
    </div>
    <div class="board-card">
      <div class="board-card-head">
        <span class="board-card-rank">02</span>
        <div class="ps-avatar">BO</div>
        <span class="board-card-name">Bob</span>
      </div>
    </div>
  </div>
</body></html>`;

const dom = new JSDOM(html, { runScripts: "outside-only", pretendToBeVisual: true });
const { window } = dom;
// getContext isn't implemented in bare jsdom; stub so drawMascot no-ops cleanly.
window.HTMLCanvasElement.prototype.getContext = () => null;
window.eval(js);
// jsdom parses with readyState "loading", so init() is waiting on this event.
window.document.dispatchEvent(new window.Event("DOMContentLoaded"));

const d = window.document;
let pass = true;
const chk = (cond, msg) => { console.log((cond ? "PASS " : "FAIL ") + msg); if (!cond) pass = false; };

// Header avatar untouched (no sibling canvas, no mascotDone).
const hdr = d.querySelector(".ps-avatar.is-self");
chk(!hdr.dataset.mascotDone, "header avatar left alone");

// Desktop: 2 mascot canvases + 2 nicknames.
const dMasc = d.querySelectorAll(".desktop-table canvas.lbm-mascot:not(.lbm-mascot--roamer)");
const dNick = d.querySelectorAll(".desktop-table .lbm-nickname");
chk(dMasc.length === 2, "desktop: 2 mascot canvases (" + dMasc.length + ")");
chk(dNick.length === 2, "desktop: 2 nicknames (" + dNick.length + ")");

// Mobile: 2 small mascots + 2 nicknames.
const mMasc = d.querySelectorAll(".mobile-cards canvas.lbm-mascot--sm");
const mNick = d.querySelectorAll(".mobile-cards .lbm-nickname");
chk(mMasc.length === 2, "mobile: 2 sm mascot canvases (" + mMasc.length + ")");
chk(mNick.length === 2, "mobile: 2 nicknames (" + mNick.length + ")");

// Per-row mascots are meaningful images: role="img" + aria-label carrying the
// nickname, and titled. (Roamer canvases are aria-hidden — set in spawn(), not
// present at init time.) Ported from PR #33's mascot-a11y refactor.
const rowMasc = d.querySelectorAll("canvas.lbm-mascot:not(.lbm-mascot--roamer)");
chk(rowMasc.length === 4 && [...rowMasc].every(c =>
    c.getAttribute("role") === "img" &&
    /^mascot: .+/.test(c.getAttribute("aria-label") || "") &&
    c.getAttribute("aria-hidden") === null &&
    c.title === "mascot"),
    "row mascots: role=img + aria-label nickname + titled (" + rowMasc.length + ")");
// aria-label matches the visible nickname text for the same row.
const aLabel = (d.querySelector(".desktop-table canvas.lbm-mascot")
    .getAttribute("aria-label") || "").replace(/^mascot: /, "");
chk(aLabel === d.querySelector(".desktop-table .lbm-nickname").textContent,
    "aria-label matches visible nickname ('" + aLabel + "')");

// Leader (Alice, rank 1) gets a LEADER_NICK; Bob gets a regular NICK.
const LEADER = ["The Closer","Birdie Boss","Fairway Finisher","Green Reaper","Ace of Clubs","Eagle Eye","Pin Seeker","The Bag Man"];
const aliceNick = d.querySelector(".desktop-table .lbm-nickname").textContent;
const bobNick = d.querySelectorAll(".desktop-table .lbm-nickname")[1].textContent;
chk(LEADER.includes(aliceNick), "leader Alice gets leader nick: '" + aliceNick + "'");
chk(!LEADER.includes(bobNick), "non-leader Bob gets regular nick: '" + bobNick + "'");

// Determinism: Alice's nickname identical across desktop + mobile (same seed=name).
const aliceMobile = d.querySelector(".mobile-cards .lbm-nickname").textContent;
chk(aliceNick === aliceMobile, "Alice nick stable desktop==mobile ('" + aliceNick + "')");

// Idempotency: re-running init must not double-decorate (mascotDone guard).
window.document.dispatchEvent(new window.Event("DOMContentLoaded"));
const dMasc2 = d.querySelectorAll(".desktop-table canvas.lbm-mascot:not(.lbm-mascot--roamer)").length;
chk(dMasc2 === 2, "idempotent: still 2 desktop mascots after re-init (" + dMasc2 + ")");

// Roamer stage prepared on .desktop-table (motion allowed by default in jsdom).
const stage = d.querySelector(".desktop-table");
chk(stage.style.overflow === "hidden", "roamer stage overflow hidden set");

// --- Reduced-motion scenario: roamer must NOT start (no leak). ---
const dom2 = new JSDOM(html, { runScripts: "outside-only", pretendToBeVisual: true });
const w2 = dom2.window;
w2.HTMLCanvasElement.prototype.getContext = () => null;
w2.matchMedia = (q) => ({ matches: /prefers-reduced-motion/.test(q), media: q,
    addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} });
w2.eval(js);
w2.document.dispatchEvent(new w2.Event("DOMContentLoaded"));
const stage2 = w2.document.querySelector(".desktop-table");
chk(stage2.style.overflow !== "hidden", "reduced-motion: roamer loop skipped (stage untouched)");
// Rows still get their static mascots + nicknames even under reduced-motion.
chk(w2.document.querySelectorAll(".desktop-table .lbm-nickname").length === 2,
    "reduced-motion: static mascots/nicknames still applied");

// --- Empty-board scenario: no rankings ⇒ no-op, no crash, no roamer. ---
const emptyHtml = `<!doctype html><html><body>
  <div class="ps-avatar is-self">HDR</div>
  <div class="desktop-table">
    <div style="flex:1;display:flex;align-items:center;justify-content:center;">
      <div class="empty-state"><p class="placeholder">No data yet.</p></div>
    </div>
  </div>
</body></html>`;
const dom3 = new JSDOM(emptyHtml, { runScripts: "outside-only", pretendToBeVisual: true });
const w3 = dom3.window;
w3.HTMLCanvasElement.prototype.getContext = () => null;
let emptyThrew = false;
try {
    w3.eval(js);
    w3.document.dispatchEvent(new w3.Event("DOMContentLoaded"));
} catch (e) { emptyThrew = true; }
chk(!emptyThrew, "empty board: init() does not throw");
chk(w3.document.querySelectorAll("canvas.lbm-mascot").length === 0,
    "empty board: no mascots added");
chk(w3.document.querySelector(".desktop-table").style.overflow !== "hidden",
    "empty board: roamer not started (no seeds)");

// --- Single-player board: one row ⇒ one mascot, that player is the leader. ---
const soloHtml = `<!doctype html><html><body>
  <div class="desktop-table">
    <div style="display:grid;grid-template-columns:1fr;">
      <div style="display:flex;align-items:center;gap:12px;">
        <div>01</div>
        <div class="ps-avatar">SO</div>
        <div><div>Solo Player</div></div>
      </div>
    </div>
  </div>
</body></html>`;
const dom4 = new JSDOM(soloHtml, { runScripts: "outside-only", pretendToBeVisual: true });
const w4 = dom4.window;
w4.HTMLCanvasElement.prototype.getContext = () => null;
w4.eval(js);
w4.document.dispatchEvent(new w4.Event("DOMContentLoaded"));
const soloMasc = w4.document.querySelectorAll(".desktop-table canvas.lbm-mascot");
const soloNick = w4.document.querySelector(".desktop-table .lbm-nickname");
chk(soloMasc.length === 1, "solo board: exactly 1 mascot (" + soloMasc.length + ")");
chk(soloNick && LEADER.includes(soloNick.textContent),
    "solo board: sole player is the leader ('" + (soloNick && soloNick.textContent) + "')");

// NOTE: jsdom has no 2D canvas backend, so getContext() is stubbed to null and
// drawMascot() no-ops — this suite verifies DOM placement/wiring, NOT the pixel
// rendering. Pixel output is validated by eye in a real browser.
console.log(pass ? "\nALL DOM TESTS PASS" : "\nDOM TESTS FAILED");
process.exit(pass ? 0 : 1);
