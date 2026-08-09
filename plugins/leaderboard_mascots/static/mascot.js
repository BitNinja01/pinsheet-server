/*
 * Leaderboard mascots — deterministic pixel creatures + golf-pun nicknames.
 *
 * Plugin build: no core template changes. This script finds the friends
 * leaderboard rows in the DOM (desktop table + mobile cards) and grafts a
 * mascot canvas and a nickname onto each one. Each player's mascot and
 * nickname are derived from their visible display name, so the same person
 * always gets the same little guy on every visit. A roaming mascot also
 * randomly "spawns" over the board for a bit of fun, then wanders off.
 *
 * No dependencies. Safely no-ops on any page without leaderboard rows.
 */
(function () {
    "use strict";

    // Golf-pun nicknames. The leader (rank 1) draws from the flattering pool;
    // everyone else gets the cheeky one.
    var NICKS = [
        "The Sandbagger", "Shank Master", "Duffer", "Mulligan King",
        "Wormburner", "Slice Machine", "Hook Hero", "Chunk Monster",
        "Whiff Wizard", "Three-Putt", "Bogey Bandit", "Gimme Grabber",
        "Lip-Out Larry", "Fried Egg", "Cart Path Cruiser", "Range Rat",
        "The Yips", "Chili Dipper", "Provisional Pete", "Snowman Slinger",
        "Fore!-Teller", "Double Bogey Don", "Rough Rider", "Tree Finder"
    ];
    var LEADER_NICKS = [
        "The Closer", "Birdie Boss", "Fairway Finisher", "Green Reaper",
        "Ace of Clubs", "Eagle Eye", "Pin Seeker", "The Bag Man"
    ];

    // xmur3 string hash -> 32-bit seed.
    function hashSeed(str) {
        var h = 1779033703 ^ str.length;
        for (var i = 0; i < str.length; i++) {
            h = Math.imul(h ^ str.charCodeAt(i), 3432918353);
            h = (h << 13) | (h >>> 19);
        }
        return function () {
            h = Math.imul(h ^ (h >>> 16), 2246822507);
            h = Math.imul(h ^ (h >>> 13), 3266489909);
            h ^= h >>> 16;
            return h >>> 0;
        };
    }

    // mulberry32 PRNG from a numeric seed.
    function rng(seed) {
        return function () {
            seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
            var t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
            t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
            return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
        };
    }

    function pick(rand, arr) {
        return arr[Math.floor(rand() * arr.length) % arr.length];
    }

    // Draw an 8x8 vertically-symmetric pixel creature onto a canvas.
    // Body color + eyes derived from the seed. Leaders get a gold crown.
    function drawMascot(canvas, seedStr, isLeader) {
        var seedFn = hashSeed(seedStr);
        var rand = rng(seedFn());
        var size = 8;
        canvas.width = size;
        canvas.height = size;
        var ctx = canvas.getContext("2d");
        if (!ctx) return;
        ctx.clearRect(0, 0, size, size);

        var hue = Math.floor(rand() * 360);
        var body = "hsl(" + hue + ",65%,55%)";
        var shade = "hsl(" + hue + ",65%,42%)";

        // Symmetric body: decide left half (cols 0..3), mirror to right.
        for (var y = 1; y < size; y++) {
            for (var x = 0; x < size / 2; x++) {
                if (rand() > 0.5) {
                    ctx.fillStyle = (rand() > 0.75) ? shade : body;
                    ctx.fillRect(x, y, 1, 1);
                    ctx.fillRect(size - 1 - x, y, 1, 1);
                }
            }
        }
        // Eyes.
        ctx.fillStyle = "#0b0b0b";
        ctx.fillRect(2, 3, 1, 1);
        ctx.fillRect(5, 3, 1, 1);
        // Crown for the leader.
        if (isLeader) {
            ctx.fillStyle = "#f5c542";
            ctx.fillRect(2, 0, 1, 1);
            ctx.fillRect(4, 0, 1, 1);
            ctx.fillRect(5, 0, 1, 1);
            ctx.fillRect(2, 1, 4, 1);
        }
    }

    function nicknameFor(seedStr, isLeader) {
        var rand = rng(hashSeed(seedStr)());
        return pick(rand, isLeader ? LEADER_NICKS : NICKS);
    }

    // Text of the first (text) child node only, so appended badges like the
    // "you" tag don't pollute the seed or nickname.
    function ownText(el) {
        if (!el) return "";
        var node = el.firstChild;
        while (node) {
            if (node.nodeType === 3 && node.textContent.trim()) {
                return node.textContent.trim();
            }
            node = node.nextSibling;
        }
        return (el.textContent || "").trim();
    }

    function prefersReducedMotion() {
        return !!(window.matchMedia &&
            window.matchMedia("(prefers-reduced-motion: reduce)").matches);
    }

    function makeCanvas(cls, seedStr, isLeader) {
        var cv = document.createElement("canvas");
        cv.className = cls;
        cv.title = "mascot";
        // Purely decorative — the substantive text lives in the .lbm-nickname.
        cv.setAttribute("aria-hidden", "true");
        drawMascot(cv, seedStr, isLeader);
        return cv;
    }

    function makeNickname(tag, seedStr, isLeader) {
        var el = document.createElement(tag);
        el.className = "lbm-nickname";
        el.textContent = nicknameFor(seedStr, isLeader);
        return el;
    }

    // Attach a mascot + nickname to one desktop leaderboard row's avatar.
    function decorateDesktop(avatar, seeds) {
        var cell = avatar.parentElement;            // flex: rank, avatar, nameWrap
        var nameWrap = avatar.nextElementSibling;   // <div><div>Name …</div></div>
        if (!cell || !nameWrap) return;
        var nameDiv = nameWrap.firstElementChild || nameWrap;
        var name = ownText(nameDiv);
        if (!name) return;

        var rankEl = avatar.previousElementSibling;
        var isLeader = parseInt(ownText(rankEl), 10) === 1;
        var seedStr = "pinsheet:" + name;
        seeds.push({ seed: seedStr, leader: isLeader });

        cell.insertBefore(makeCanvas("lbm-mascot", seedStr, isLeader), nameWrap);
        nameWrap.appendChild(makeNickname("div", seedStr, isLeader));
    }

    // Attach a mascot + nickname to one mobile board card's avatar.
    function decorateMobile(avatar, seeds) {
        var head = avatar.parentElement;            // .board-card-head
        if (!head) return;
        var nameEl = head.querySelector(".board-card-name");
        if (!nameEl) return;
        var name = ownText(nameEl);
        if (!name) return;

        var rankEl = head.querySelector(".board-card-rank");
        var isLeader = parseInt(ownText(rankEl), 10) === 1;
        var seedStr = "pinsheet:" + name;
        seeds.push({ seed: seedStr, leader: isLeader });

        head.insertBefore(
            makeCanvas("lbm-mascot lbm-mascot--sm", seedStr, isLeader), nameEl);
        var nick = makeNickname("span", seedStr, isLeader);
        nick.style.display = "block";
        nameEl.appendChild(nick);
    }

    function init() {
        var seeds = [];

        document.querySelectorAll(".desktop-table .ps-avatar").forEach(
            function (avatar) {
                if (avatar.dataset.mascotDone) return;
                avatar.dataset.mascotDone = "1";
                decorateDesktop(avatar, seeds);
            });

        document.querySelectorAll(".mobile-cards .ps-avatar").forEach(
            function (avatar) {
                if (avatar.dataset.mascotDone) return;
                avatar.dataset.mascotDone = "1";
                decorateMobile(avatar, seeds);
            });

        if (seeds.length) startRoamer(seeds);
    }

    // A mascot that randomly spawns, wiggles across the board, then leaves.
    function startRoamer(seeds) {
        // Under reduced-motion the CSS hides the roamer with display:none, which
        // means no animation runs and no animationend fires — so the cleanup
        // never happens and spawned canvases would pile up forever. Skip the
        // whole loop instead of leaking DOM nodes.
        if (prefersReducedMotion()) return;

        var board = document.querySelector(".desktop-table");
        if (board) {
            // Give the roamer an absolute-positioning context to travel over.
            board.style.position = board.style.position || "relative";
            board.style.overflow = "hidden";
        } else {
            board = document.body;
        }

        function spawn() {
            var choice = seeds[Math.floor(Math.random() * seeds.length)];
            // Built via makeCanvas() so the roamer inherits the same decorative
            // treatment as the row mascots (aria-hidden, title).
            var cv = makeCanvas("lbm-mascot lbm-mascot--roamer", choice.seed, choice.leader);
            var rect = board.getBoundingClientRect();
            var top = Math.max(8, Math.random() * Math.max(8, rect.height - 40));
            cv.style.top = top + "px";
            cv.style.setProperty("--roam-dur", (5 + Math.random() * 4).toFixed(1) + "s");
            board.appendChild(cv);
            cv.addEventListener("animationend", function () { cv.remove(); });
        }

        function loop() {
            spawn();
            setTimeout(loop, 6000 + Math.random() * 9000);
        }
        setTimeout(loop, 2500 + Math.random() * 4000);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
