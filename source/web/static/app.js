document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".clickable-row").forEach(function (row) {
        row.addEventListener("click", function () {
            if (this.dataset.href) {
                window.location.href = this.dataset.href;
            } else if (this.dataset.date && this.dataset.index) {
                window.location.href = "/rounds/" + this.dataset.date + "/" + this.dataset.index;
            }
        });
    });
});

(function () {
    var sidebar = document.getElementById('ps-sidebar');
    var backdrop = document.getElementById('sidebar-backdrop');
    var hamburger = document.getElementById('hamburger-btn');
    if (!sidebar || !backdrop || !hamburger) return;

    function openSidebar() {
        sidebar.classList.add('open');
        hamburger.classList.add('open');
        backdrop.classList.add('visible');
        document.body.style.overflow = 'hidden';
    }

    function closeSidebar() {
        sidebar.classList.remove('open');
        hamburger.classList.remove('open');
        backdrop.classList.remove('visible');
        document.body.style.overflow = '';
    }

    hamburger.addEventListener('click', function () {
        if (sidebar.classList.contains('open')) {
            closeSidebar();
        } else {
            openSidebar();
        }
    });

    backdrop.addEventListener('click', closeSidebar);

    sidebar.querySelectorAll('.ps-nav a').forEach(function (link) {
        link.addEventListener('click', closeSidebar);
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && sidebar.classList.contains('open')) {
            closeSidebar();
        }
    });
})();

document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.round-card').forEach(function (card) {
        card.addEventListener('click', function () {
            if (this.dataset.date && this.dataset.index) {
                window.location.href = '/rounds/' + this.dataset.date + '/' + this.dataset.index;
            }
        });
    });
});

(function () {
    var form = document.getElementById("settings-form");
    if (!form) return;

    function saveSettings() {
        var theme = document.querySelector(".theme-swatch[data-active]")?.dataset?.theme || "dark";
        var seasonStart = (document.getElementById("season-start")?.value || "01-01").split("-");
        var seasonEnd = (document.getElementById("season-end")?.value || "12-28").split("-");
        var data = {
            theme: theme,
            include_9hole: document.getElementById("include-9hole")?.checked !== false,
            auto_calc: document.getElementById("auto-calc")?.checked !== false,
            show_report: document.getElementById("show-report")?.checked !== false,
            season_enabled: document.getElementById("season-enabled")?.checked === true,
            season_start_month: parseInt(seasonStart[0]) || 1,
            season_start_day: parseInt(seasonStart[1]) || 1,
            season_end_month: parseInt(seasonEnd[0]) || 12,
            season_end_day: parseInt(seasonEnd[1]) || 28,
            handicap_target: document.getElementById("handicap-target")?.value || "",
        };
        console.log("Saving settings:", data);
        var xhr = new XMLHttpRequest();
        xhr.open("PUT", "/api/settings", false);
        xhr.setRequestHeader("Content-Type", "application/json");
        xhr.send(JSON.stringify(data));
    }

    document.querySelectorAll(".theme-swatch").forEach(function (swatch) {
        swatch.addEventListener("click", function () {
            document.querySelectorAll(".theme-swatch").forEach(function (s) {
                s.removeAttribute("data-active");
            });
            this.setAttribute("data-active", "true");
            document.body.className = "ps-" + this.dataset.theme;
            saveSettings();
        });
    });

    form.addEventListener("change", saveSettings);
})();

(function () {
    var wizard = document.getElementById("course-wizard");
    if (!wizard) return;

    var teeCount = 0;
    var holesGrid = {};

    var btnAddTee = document.getElementById("btn-add-tee");
    var teesContainer = document.getElementById("tees-container");
    var holesArea = document.getElementById("course-holes-area");

    if (!btnAddTee) {
        console.error("course-wizard: #btn-add-tee not found");
        return;
    }

    function _teeSetHTML(idx) {
        return '<div class="tee-set" data-tee-idx="' + idx + '">' +
            '<div class="tee-set-header">' +
            '<span class="tee-set-title">Tee #' + (idx + 1) + '</span>' +
            '<button class="btn tee-remove-btn" data-tee-idx="' + idx + '">&times;</button>' +
            '</div>' +
            '<div class="tee-fields">' +
            '<input type="text" class="step-input tee-name" placeholder="Tee name (e.g. Blue)">' +
            '<div class="tee-numbers">' +
            '<label>Yardage <input type="number" class="step-input tee-yardage" step="1" placeholder="6500"></label>' +
            '<label>Rating <input type="number" class="step-input tee-rating" step="0.1" placeholder="72.0"></label>' +
            '<label>Slope <input type="number" class="step-input tee-slope" step="1" placeholder="113"></label>' +
            '<label>Front Rating <input type="number" class="step-input tee-front-rating" step="0.1" placeholder="36.0"></label>' +
            '<label>Front Slope <input type="number" class="step-input tee-front-slope" step="1" placeholder="130"></label>' +
            '<label>Back Rating <input type="number" class="step-input tee-back-rating" step="0.1" placeholder="36.0"></label>' +
            '<label>Back Slope <input type="number" class="step-input tee-back-slope" step="1" placeholder="130"></label>' +
            '</div>' +
            '</div>' +
            '</div>';
    }

    function addTeeSet() {
        var html = _teeSetHTML(teeCount);
        teesContainer.insertAdjacentHTML("beforeend", html);
        var el = teesContainer.lastElementChild;
        el.querySelector(".tee-remove-btn").addEventListener("click", function () {
            el.remove();
            buildCourseHoles();
        });
        teeCount++;
        buildCourseHoles();
    }

    function _readHolesGrid() {
        document.querySelectorAll("#course-holes-area tr[data-hole]").forEach(function (row) {
            var hole = "h" + row.dataset.hole;
            var parEl = row.querySelector(".course-par");
            var idxEl = row.querySelector(".course-index");
            if (parEl) holesGrid[hole + "_par"] = parEl.value;
            if (idxEl) holesGrid[hole + "_index"] = idxEl.value;
            row.querySelectorAll(".course-yardage").forEach(function (yd, ti) {
                holesGrid[hole + "_yd_" + ti] = yd.value;
            });
        });
    }

    function buildCourseHoles() {
        _readHolesGrid();

        var currentTees = [];
        document.querySelectorAll(".tee-name").forEach(function (el) {
            var name = el.value.trim();
            if (name) currentTees.push(name);
        });

        if (currentTees.length === 0) {
            holesArea.innerHTML = '<p class="placeholder">Add at least one tee set above first.</p>';
            return;
        }

        var html = '<table class="data-table scorecard-input"><thead><tr>';
        html += '<th>Hole</th><th>Par</th><th>Index</th>';
        currentTees.forEach(function (t) {
            html += '<th>' + t + ' yds</th>';
        });
        html += '</tr></thead><tbody>';

        for (var i = 1; i <= 18; i++) {
            var hkey = "h" + i;
            html += '<tr data-hole="' + i + '">';
            html += '<td>' + i + '</td>';
            html += '<td><input type="number" class="hole-input course-par" min="1" max="7" value="' + (holesGrid[hkey + "_par"] || "") + '" size="2"></td>';
            html += '<td><input type="number" class="hole-input course-index" min="1" max="18" value="' + (holesGrid[hkey + "_index"] || "") + '" size="2"></td>';
            currentTees.forEach(function (t, ti) {
                var ykey = hkey + "_yd_" + ti;
                html += '<td><input type="number" class="hole-input course-yardage" min="1" max="999" value="' + (holesGrid[ykey] || "") + '" size="3"></td>';
            });
            html += '</tr>';
        }

        html += '</tbody></table>';
        holesArea.innerHTML = html;
    }

    btnAddTee.addEventListener("click", addTeeSet);

    addTeeSet();

    wizard.addEventListener("change", function (e) {
        if (e.target.classList.contains("tee-name")) {
            buildCourseHoles();
        }
    });

    // Draft save
    function saveCourseDraft() {
        var draft = {
            name: document.getElementById("course-name").value,
            location: {
                city: document.getElementById("course-city")?.value || "",
                state: document.getElementById("course-state")?.value || "",
                country: document.getElementById("course-country")?.value || "",
            },
            tees: {},
        };
        document.querySelectorAll(".tee-set").forEach(function (set, idx) {
            var teeName = set.querySelector(".tee-name")?.value || "";
            draft.tees[teeName || ("tee_" + idx)] = {
                name: teeName,
                rating: set.querySelector(".tee-rating")?.value || "",
                slope: set.querySelector(".tee-slope")?.value || "",
                yardage: set.querySelector(".tee-yardage")?.value || "",
                front_rating: set.querySelector(".tee-front-rating")?.value || "",
                front_slope: set.querySelector(".tee-front-slope")?.value || "",
                back_rating: set.querySelector(".tee-back-rating")?.value || "",
                back_slope: set.querySelector(".tee-back-slope")?.value || "",
            };
        });
        fetch("/api/drafts/course", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(draft),
        });
    }

    var draftTimer = null;
    wizard.addEventListener("change", function () {
        clearTimeout(draftTimer);
        draftTimer = setTimeout(saveCourseDraft, 500);
    });

    // Draft resume
    fetch("/api/drafts/course")
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data && data.name) {
                document.getElementById("draft-resume").style.display = "block";
                wizard.style.display = "none";
            }
        });

    document.getElementById("draft-resume-btn")?.addEventListener("click", function () {
        document.getElementById("draft-resume").style.display = "none";
        wizard.style.display = "block";
        fetch("/api/drafts/course")
            .then(function (r) { return r.json(); })
            .then(function (draft) {
                if (draft.name) document.getElementById("course-name").value = draft.name;
                if (draft.location) {
                    var loc = draft.location;
                    if (typeof loc === "string") {
                        document.getElementById("course-city") && (document.getElementById("course-city").value = loc);
                    } else {
                        document.getElementById("course-city") && (document.getElementById("course-city").value = loc.city || "");
                        document.getElementById("course-state") && (document.getElementById("course-state").value = loc.state || "");
                        document.getElementById("course-country") && (document.getElementById("course-country").value = loc.country || "");
                    }
                }
                if (draft.tees) {
                    var teeEntries = Object.entries(draft.tees);
                    // Ensure enough tee sets exist
                    while (document.querySelectorAll(".tee-set").length < teeEntries.length) {
                        addTeeSet();
                    }
                    var sets = document.querySelectorAll(".tee-set");
                    teeEntries.forEach(function (entry, idx) {
                        var set = sets[idx];
                        if (!set) return;
                        var tn = set.querySelector(".tee-name");
                        if (tn && !tn.value) tn.value = entry[0] || "";
                        var tee = entry[1];
                        set.querySelector(".tee-rating") && (set.querySelector(".tee-rating").value = tee.rating || "");
                        set.querySelector(".tee-slope") && (set.querySelector(".tee-slope").value = tee.slope || "");
                        set.querySelector(".tee-yardage") && (set.querySelector(".tee-yardage").value = tee.yardage || "");
                        set.querySelector(".tee-front-rating") && (set.querySelector(".tee-front-rating").value = tee.front_rating || "");
                        set.querySelector(".tee-front-slope") && (set.querySelector(".tee-front-slope").value = tee.front_slope || "");
                        set.querySelector(".tee-back-rating") && (set.querySelector(".tee-back-rating").value = tee.back_rating || "");
                        set.querySelector(".tee-back-slope") && (set.querySelector(".tee-back-slope").value = tee.back_slope || "");
                    });
                    buildCourseHoles();
                }
            });
    });

    document.getElementById("draft-discard-btn")?.addEventListener("click", function () {
        fetch("/api/drafts/course", { method: "DELETE" }).then(function () {
            document.getElementById("draft-resume").style.display = "none";
            wizard.style.display = "block";
        });
    });

    // Submit
    document.getElementById("submit-course").addEventListener("click", function () {
        var name = document.getElementById("course-name").value.trim();
        if (!name) {
            alert("Please enter a course name.");
            return;
        }

        var city = document.getElementById("course-city")?.value.trim() || "";
        var state = document.getElementById("course-state")?.value.trim() || "";
        var country = document.getElementById("course-country")?.value.trim() || "";
        if (!city || !state || !country) {
            alert("Please enter city, state/province, and country.");
            return;
        }

        var tees = {};
        document.querySelectorAll(".tee-set").forEach(function (set) {
            var teeName = set.querySelector(".tee-name")?.value?.trim();
            if (!teeName) return;
            tees[teeName] = {
                rating: set.querySelector(".tee-rating")?.value || "",
                slope: set.querySelector(".tee-slope")?.value || "",
                yardage: set.querySelector(".tee-yardage")?.value || "",
                front_rating: set.querySelector(".tee-front-rating")?.value || "",
                front_slope: set.querySelector(".tee-front-slope")?.value || "",
                back_rating: set.querySelector(".tee-back-rating")?.value || "",
                back_slope: set.querySelector(".tee-back-slope")?.value || "",
            };
        });

        var holes = {};
        var totalPar = 0;
        document.querySelectorAll("#course-holes-area tr[data-hole]").forEach(function (row) {
            var holeNum = row.dataset.hole;
            var parEl = row.querySelector(".course-par");
            var indexEl = row.querySelector(".course-index");
            var holeData = {
                par: parEl ? parEl.value : "",
                index: indexEl ? indexEl.value : "",
            };
            if (holeData.par) totalPar += parseInt(holeData.par) || 0;
            holes[holeNum] = holeData;
        });

        // Collect yardages per tee
        var teeNames = [];
        document.querySelectorAll(".tee-name").forEach(function (el) {
            var n = el.value.trim();
            if (n) teeNames.push(n);
        });

        // Build yardages for each tee from the hole grid
        var holesTbody = document.querySelector("#course-holes-area tbody");
        var rows = holesTbody ? holesTbody.querySelectorAll("tr[data-hole]") : [];
        rows.forEach(function (row) {
            var holeNum = row.dataset.hole;
            var yardageInputs = row.querySelectorAll(".course-yardage");
            yardageInputs.forEach(function (input, idx) {
                if (idx < teeNames.length) {
                    var teeName = teeNames[idx];
                    if (!tees[teeName].yardages) tees[teeName].yardages = {};
                    tees[teeName].yardages[holeNum] = input.value;
                }
            });
        });

        var payload = {
            name: name,
            location: {
                city: city,
                "state/province": state,
                country: country,
            },
            tees: tees,
            holes: holes,
            par: totalPar,
        };

        fetch("/api/courses", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.error) {
                alert(data.error);
                return;
            }
            fetch("/api/drafts/course", { method: "DELETE" }).then(function () {
                window.location.href = "/courses/" + encodeURIComponent(name);
            });
        });
    });
})();

(function () {
    var wizard = document.getElementById("round-wizard");
    if (!wizard) return;

    var STEP_ORDER = ['date', 'course', 'tee', 'holes', 'transport', 'entry_mode', 'holes_detail', 'notes'];
    var draftTimer = null;
    var scorecardData = {};

    function showStep(step) {
        var el = document.querySelector('.wizard-step[data-step="' + step + '"]');
        if (el) el.style.display = 'block';
    }

    function populateTees(courseName) {
        var course = window._courses[courseName];
        if (!course) return;
        var teeSelect = document.getElementById('round-tee');
        teeSelect.innerHTML = '<option value="">Select tees...</option>';
        (Object.keys(course.tees || {})).forEach(function (name) {
            var opt = document.createElement('option');
            opt.value = name;
            opt.textContent = name;
            teeSelect.appendChild(opt);
        });
    }

    function addGrossScoreInput() {
        if (document.getElementById('gross-score')) return;
        var area = document.getElementById('scorecard-area');
        area.innerHTML = '<div><label class="step-label">Gross Score</label><input type="number" class="step-input" id="gross-score" placeholder="e.g. 87" min="1" max="200"></div>';
    }

    function getScorecardRange() {
        var checked = document.querySelector('input[name="holes_played"]:checked');
        var val = checked ? checked.value : '18';
        if (val === 'front9') return [1,2,3,4,5,6,7,8,9];
        if (val === 'back9') return [10,11,12,13,14,15,16,17,18];
        return [1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18];
    }

    function _saveScorecardData() {
        document.querySelectorAll('#scorecard-area tr[data-hole]').forEach(function (row) {
            var num = row.dataset.hole;
            var gross = row.querySelector('.score-gross');
            var fwy = row.querySelector('.score-fwy');
            var gir = row.querySelector('.score-gir');
            var putts = row.querySelector('.score-putts');
            var pen = row.querySelector('.score-pen');
            if (!gross) return;
            scorecardData[num] = {
                gross: gross.value,
                fairway: fwy ? fwy.value : '',
                gir: gir ? gir.value : '',
                putts: putts ? putts.value : '',
                penalties: pen ? pen.value : '0',
            };
        });
    }

    function buildScorecardGrid() {
        var holesRange = getScorecardRange();
        var courseName = document.getElementById('round-course').value;
        var course = window._courses[courseName];
        var holesData = course ? course.holes || {} : {};

        var html = '<table class="data-table scorecard-input"><thead><tr>' +
            '<th>Hole</th><th>Par</th><th>SI</th><th>Gross</th><th>Fairway</th><th>GIR</th><th>Putts</th><th>Pen</th>' +
            '</tr></thead><tbody>';

        var holeRow = function (num) {
            var hole = holesData[String(num)] || {};
            var par = hole.par || '';
            var saved = scorecardData[num] || {};
            var r = '<tr data-hole="' + num + '">';
            r += '<td>' + num + '</td>';
            r += '<td class="hole-par">' + par + '</td>';
            r += '<td>' + (hole.index || hole.hole_index || '') + '</td>';
            r += '<td><input type="number" class="hole-input score-gross" min="1" max="20" value="' + (saved.gross || '') + '"></td>';
            if (par === '3') {
                r += '<td>\u2014</td>';
            } else {
                r += '<td><select class="hole-input score-fwy"><option value="">--</option><option>H</option><option>L</option><option>R</option><option>OBL</option><option>OBR</option><option>N</option></select></td>';
            }
            r += '<td><select class="hole-input score-gir"><option value="">--</option><option>H</option><option>L</option><option>R</option><option>S</option><option>LO</option><option>OBL</option><option>OBR</option><option>OBS</option><option>OBLO</option><option>N</option></select></td>';
            r += '<td><input type="number" class="hole-input score-putts" min="0" max="10" value="' + (saved.putts || '') + '"></td>';
            r += '<td><input type="number" class="hole-input score-pen" min="0" max="20" value="' + (saved.penalties || '0') + '"></td>';
            r += '</tr>';
            return r;
        };

        var outRow = function () {
            return '<tr class="subtotal-row"><td>OUT</td><td></td><td></td><td class="subtotal" id="sub-gross-out">\u2014</td><td></td><td></td><td class="subtotal" id="sub-putts-out">\u2014</td><td class="subtotal" id="sub-pen-out">\u2014</td></tr>';
        };
        var inRow = function () {
            return '<tr class="subtotal-row"><td>IN</td><td></td><td></td><td class="subtotal" id="sub-gross-in">\u2014</td><td></td><td></td><td class="subtotal" id="sub-putts-in">\u2014</td><td class="subtotal" id="sub-pen-in">\u2014</td></tr>';
        };
        var totRow = function () {
            return '<tr class="subtotal-row"><td>TOT</td><td></td><td></td><td class="subtotal" id="sub-gross-tot">\u2014</td><td></td><td></td><td class="subtotal" id="sub-putts-tot">\u2014</td><td class="subtotal" id="sub-pen-tot">\u2014</td></tr>';
        };

        if (holesRange.length === 18) {
            for (var i = 0; i < 18; i++) {
                html += holeRow(holesRange[i]);
                if (holesRange[i] === 9) html += outRow();
            }
            html += inRow();
            html += totRow();
        } else if (holesRange[0] === 1) {
            holesRange.forEach(function (num) { html += holeRow(num); });
            html += outRow();
        } else {
            holesRange.forEach(function (num) { html += holeRow(num); });
            html += inRow();
        }

        html += '</tbody></table>';
        document.getElementById('scorecard-area').innerHTML = html;

        document.querySelectorAll('#scorecard-area tr[data-hole]').forEach(function (row) {
            var grossInput = row.querySelector('.score-gross');
            var parEl = row.querySelector('.hole-par');
            if (grossInput && grossInput.value && parEl) {
                var par = parseInt(parEl.textContent);
                if (par) colorizeGross(grossInput, par);
            }
        });
        updateSubtotals();

        /* Also render mobile hole cards */
        var courseNameForHoles = document.getElementById('round-course').value;
        var courseForHoles = window._courses[courseNameForHoles];
        var holesDataForCards = courseForHoles ? courseForHoles.holes || {} : {};
        renderHoleCards(getScorecardRange(), holesDataForCards);
    }

    /* ── Shorthand parser ── */
    function parseShorthand(raw) {
        var parts = raw.trim().split(/\s+/);
        return {
            gross: parts[0] || '',
            fairway: parts[1] || '',
            gir: parts[2] || '',
            putts: parts[3] || '',
            penalties: parts[4] || '0',
        };
    }

    function buildShorthand(saved) {
        if (!saved.gross) return '';
        var parts = [saved.gross];
        if (saved.fairway) parts.push(saved.fairway);
        if (saved.gir) parts.push(saved.gir);
        if (saved.putts) parts.push(saved.putts);
        if (saved.penalties && saved.penalties !== '0') parts.push(saved.penalties);
        return parts.join(' ');
    }

    /* ── Mobile hole cards render ── */
    function renderHoleCards(range, holesData) {
        var container = document.getElementById('hole-cards-area');
        var progressBar = document.getElementById('hole-progress-bar');
        if (!container) return;

        var html = '';
        range.forEach(function (num) {
            var hole = holesData[String(num)] || {};
            var par = hole.par || '';
            var saved = scorecardData[num] || {};
            html += '<div class="hole-card" id="hole-card-' + num + '" data-hole="' + num + '">';
            html += '<div class="hole-card-header">';
            html += '<div class="hole-card-hole-num">' + num + '</div>';
            html += '<div class="hole-card-hole-info">';
            html += 'Par <span>' + par + '</span>';
            html += ' &middot; Index <span>' + (hole.index || '') + '</span>';
            html += '</div></div>';
            html += '<div class="hole-card-parsed" id="hole-parsed-' + num + '">';
            html += '<div class="hole-card-parsed-field"><div class="hole-card-parsed-label">Score</div><div class="hole-card-parsed-value" id="parsed-gross-' + num + '">' + (saved.gross || '&mdash;') + '</div></div>';
            html += '<div class="hole-card-parsed-field"><div class="hole-card-parsed-label">Fairway</div><div class="hole-card-parsed-value" id="parsed-fairway-' + num + '">' + (saved.fairway || '&mdash;') + '</div></div>';
            html += '<div class="hole-card-parsed-field"><div class="hole-card-parsed-label">GIR</div><div class="hole-card-parsed-value" id="parsed-gir-' + num + '">' + (saved.gir || '&mdash;') + '</div></div>';
            html += '<div class="hole-card-parsed-field"><div class="hole-card-parsed-label">Putts</div><div class="hole-card-parsed-value" id="parsed-putts-' + num + '">' + (saved.putts || '&mdash;') + '</div></div>';
            html += '</div>';
            html += '<div class="hole-card-input-area">';
            html += '<div class="hole-card-input-label">Enter shorthand &mdash; score fairway gir putts</div>';
            html += '<input type="text" class="hole-card-shorthand" id="shorthand-' + num + '" placeholder="e.g. 4 L N 2" value="' + buildShorthand(saved) + '" autocomplete="off">';
            html += '<div class="hole-card-hint">Score req. &middot; Fairway &middot; GIR &middot; Putts &middot; Pen (opt)</div>';
            html += '</div>';
            html += '<div class="hole-card-actions">';
            var idx = range.indexOf(num);
            if (idx > 0) {
                html += '<button class="hole-card-btn" onclick="window._navigateHole && window._navigateHole(' + range[idx - 1] + ')">Prev</button>';
            } else {
                html += '<button class="hole-card-btn" style="visibility:hidden">Prev</button>';
            }
            if (idx < range.length - 1) {
                html += '<button class="hole-card-btn hole-card-btn--next">Next Hole</button>';
            } else {
                html += '<button class="hole-card-btn hole-card-btn--next" id="save-round-mobile">Save Round</button>';
            }
            html += '</div>';
            html += '</div>';
        });
        container.innerHTML = html;

        /* Progress bar */
        var ph = '';
        range.forEach(function (n) {
            var saved = scorecardData[n] || {};
            var cls = saved.gross ? ' completed' : (n === range[0] ? ' current' : '');
            ph += '<div class="hole-progress-dot' + cls + '">' + n + '</div>';
        });
        if (progressBar) progressBar.innerHTML = ph;

        /* Attach event listeners */
        range.forEach(function (n) {
            var input = document.getElementById('shorthand-' + n);
            if (!input) return;
            input.addEventListener('input', function () {
                updateHoleCardFromShorthand(n);
            });
            input.addEventListener('keydown', function (e) {
                if (e.key === 'Enter' || (e.key === 'Tab')) {
                    e.preventDefault();
                    var nextIdx = range.indexOf(n) + 1;
                    if (nextIdx < range.length) {
                        navigateToHole(range[nextIdx]);
                    }
                }
            });
        });

        /* Wire Next Hole button click */
        range.forEach(function (n) {
            var btnRow = document.querySelector('#hole-card-' + n + ' .hole-card-btn--next');
            var saveBtnCheck = document.getElementById('save-round-mobile');
            if (btnRow && btnRow !== saveBtnCheck) {
                btnRow.addEventListener('click', function () {
                    var nextIdx = range.indexOf(n) + 1;
                    if (nextIdx < range.length) {
                        navigateToHole(range[nextIdx]);
                    }
                });
            }
        });

        var saveBtn = document.getElementById('save-round-mobile');
        if (saveBtn) {
            saveBtn.addEventListener('click', submitRound);
        }
    }

    function updateHoleCardFromShorthand(holeNum) {
        var input = document.getElementById('shorthand-' + holeNum);
        if (!input) return;
        var parsed = parseShorthand(input.value);
        var grossEl = document.getElementById('parsed-gross-' + holeNum);
        var fwyEl = document.getElementById('parsed-fairway-' + holeNum);
        var girEl = document.getElementById('parsed-gir-' + holeNum);
        var puttsEl = document.getElementById('parsed-putts-' + holeNum);
        if (grossEl) grossEl.textContent = parsed.gross || '\u2014';
        if (fwyEl) fwyEl.textContent = parsed.fairway || '\u2014';
        if (girEl) girEl.textContent = parsed.gir || '\u2014';
        if (puttsEl) puttsEl.textContent = parsed.putts || '\u2014';
        scorecardData[holeNum] = parsed;

        /* Sync to desktop table inputs */
        var desktopRow = document.querySelector('#scorecard-area tr[data-hole="' + holeNum + '"]');
        if (desktopRow) {
            var gEl = desktopRow.querySelector('.score-gross');
            var fEl = desktopRow.querySelector('.score-fwy');
            var giEl = desktopRow.querySelector('.score-gir');
            var pEl = desktopRow.querySelector('.score-putts');
            var penEl = desktopRow.querySelector('.score-pen');
            if (gEl) gEl.value = parsed.gross;
            if (fEl) fEl.value = parsed.fairway;
            if (giEl) giEl.value = parsed.gir;
            if (pEl) pEl.value = parsed.putts;
            if (penEl) penEl.value = parsed.penalties;
            updateSubtotals();
        }

        updateProgressDots();
    }

    function updateProgressDots() {
        var progressBar = document.getElementById('hole-progress-bar');
        if (!progressBar) return;
        var dots = progressBar.querySelectorAll('.hole-progress-dot');
        dots.forEach(function (dot) {
            var num = parseInt(dot.textContent);
            var saved = scorecardData[num] || {};
            dot.classList.remove('completed', 'current');
            if (saved.gross) {
                dot.classList.add('completed');
            }
        });
        var found = false;
        dots.forEach(function (dot) {
            if (!found && !dot.classList.contains('completed')) {
                dot.classList.add('current');
                found = true;
            }
        });
    }

    function navigateToHole(holeNum) {
        var card = document.getElementById('hole-card-' + holeNum);
        if (card) {
            card.scrollIntoView({ behavior: 'smooth', block: 'start' });
            var input = document.getElementById('shorthand-' + holeNum);
            if (input) {
                setTimeout(function () { input.focus(); }, 300);
            }
        }
    }
    function syncDesktopToMobile(holeNum) {
        var saved = scorecardData[holeNum] || {};
        var shorthandInput = document.getElementById('shorthand-' + holeNum);
        if (shorthandInput) {
            shorthandInput.value = buildShorthand(saved);
        }
        var gEl = document.getElementById('parsed-gross-' + holeNum);
        var fEl = document.getElementById('parsed-fairway-' + holeNum);
        var giEl = document.getElementById('parsed-gir-' + holeNum);
        var pEl = document.getElementById('parsed-putts-' + holeNum);
        if (gEl) gEl.textContent = saved.gross || '\u2014';
        if (fEl) fEl.textContent = saved.fairway || '\u2014';
        if (giEl) giEl.textContent = saved.gir || '\u2014';
        if (pEl) pEl.textContent = saved.putts || '\u2014';
        updateProgressDots();
    }
    window._navigateHole = navigateToHole;

    function colorizeGross(input, par) {
        var val = parseInt(input.value);
        if (!val || isNaN(val)) {
            input.style.backgroundColor = '';
            input.style.color = '';
            input.style.fontWeight = '';
            input.style.opacity = '';
            return;
        }
        var diff = val - par;
        input.style.color = '';
        input.style.fontWeight = '';
        input.style.backgroundColor = '';
        input.style.opacity = '';
        if (diff <= -2) {
            input.style.color = '#ffd700';
            input.style.fontWeight = 'bold';
        } else if (diff === -1) {
            input.style.color = '#90ee90';
            input.style.fontWeight = 'bold';
        } else if (diff === 1) {
            input.style.color = '#aaaaaa';
        } else if (diff >= 2) {
            input.style.color = '#ff4444';
            if (diff >= 3) {
                input.style.fontWeight = 'bold';
            }
        }
    }

    function colorizePutts(input) {
        var val = parseInt(input.value);
        if (!val || isNaN(val)) {
            input.style.color = '';
            input.style.fontWeight = '';
            return;
        }
        input.style.color = '';
        input.style.fontWeight = '';
        if (val === 1) {
            input.style.color = '#90ee90';
            input.style.fontWeight = 'bold';
        } else if (val >= 3) {
            input.style.color = '#ff4444';
        }
    }

    function colorizePen(input) {
        var val = parseInt(input.value);
        if (!val || isNaN(val)) {
            input.style.color = '';
            return;
        }
        input.style.color = val > 0 ? '#ff4444' : '';
    }

    function updateSubtotals() {
        var rows = document.querySelectorAll('#scorecard-area tr[data-hole]');
        var outGross = 0, inGross = 0, outPutts = 0, inPutts = 0, outPen = 0, inPen = 0;
        var hasOut = false, hasIn = false;

        rows.forEach(function (row) {
            var holeNum = parseInt(row.dataset.hole);
            var gross = parseInt(row.querySelector('.score-gross').value);
            var putts = parseInt(row.querySelector('.score-putts').value);
            var pen = parseInt(row.querySelector('.score-pen').value);

            if (gross && !isNaN(gross)) {
                if (holeNum <= 9) { outGross += gross; hasOut = true; }
                else { inGross += gross; hasIn = true; }
            }
            if (putts && !isNaN(putts)) {
                if (holeNum <= 9) outPutts += putts;
                else inPutts += putts;
            }
            if (pen && !isNaN(pen)) {
                if (holeNum <= 9) outPen += pen;
                else inPen += pen;
            }
        });

        function setText(id, val, has) {
            var el = document.getElementById(id);
            if (el) el.textContent = has ? String(val) : '\u2014';
        }

        setText('sub-gross-out', outGross, hasOut);
        setText('sub-gross-in', inGross, hasIn);
        setText('sub-gross-tot', outGross + inGross, hasOut || hasIn);
        setText('sub-putts-out', outPutts, hasOut);
        setText('sub-putts-in', inPutts, hasIn);
        setText('sub-putts-tot', outPutts + inPutts, hasOut || hasIn);
        setText('sub-pen-out', outPen, hasOut);
        setText('sub-pen-in', inPen, hasIn);
        setText('sub-pen-tot', outPen + inPen, hasOut || hasIn);
    }

    function isStepVisible(name) {
        var step = document.querySelector('[data-step="' + name + '"]');
        return step && step.style.display !== 'none' && step.offsetParent !== null;
    }

    function getDraft() {
        var draft = {
            date: document.getElementById('round-date').value,
            course: document.getElementById('round-course').value,
            tees: document.getElementById('round-tee').value,
            notes: document.getElementById('round-notes').value,
        };
        if (isStepVisible('holes')) {
            draft.holes_played = (document.querySelector('input[name="holes_played"]:checked') || {}).value || '';
        }
        if (isStepVisible('transport')) {
            draft.transport = (document.querySelector('input[name="transport"]:checked') || {}).value || '';
        }
        if (isStepVisible('entry_mode')) {
            draft.entry_mode = (document.querySelector('input[name="entry_mode"]:checked') || {}).value || '';
        }
        return draft;
    }

    function saveDraft() {
        fetch('/api/drafts/round', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(getDraft()),
        });
    }

    function getLastStep(draft) {
        if (draft.notes) return 'notes';
        if (draft.entry_mode) {
            if (draft.entry_mode === 'score_only') return 'notes';
            return 'holes_detail';
        }
        if (draft.transport !== undefined && draft.transport !== null && draft.transport !== '') return 'entry_mode';
        if (draft.holes_played) return 'transport';
        if (draft.tees) return 'holes';
        if (draft.course) return 'tee';
        if (draft.date) return 'course';
        return 'date';
    }

    function resumeFromDraft(draft) {
        if (draft.date) document.getElementById('round-date').value = draft.date;

        if (draft.course) {
            document.getElementById('round-course').value = draft.course;
            populateTees(draft.course);
        }

        if (draft.tees) document.getElementById('round-tee').value = draft.tees;

        if (draft.holes_played) {
            var radio = document.querySelector('input[name="holes_played"][value="' + draft.holes_played + '"]');
            if (radio) radio.checked = true;
        }

        if (draft.transport !== undefined && draft.transport !== null && draft.transport !== '') {
            var tRadio = document.querySelector('input[name="transport"][value="' + draft.transport + '"]');
            if (tRadio) tRadio.checked = true;
        }

        if (draft.entry_mode) {
            var eRadio = document.querySelector('input[name="entry_mode"][value="' + draft.entry_mode + '"]');
            if (eRadio) eRadio.checked = true;
        }

        if (draft.notes) document.getElementById('round-notes').value = draft.notes;

        var lastStep = getLastStep(draft);
        var idx = STEP_ORDER.indexOf(lastStep);
        for (var i = 0; i <= idx; i++) {
            showStep(STEP_ORDER[i]);
        }

        if (draft.entry_mode === 'detailed') {
            buildScorecardGrid();
        } else if (draft.entry_mode === 'score_only') {
            addGrossScoreInput();
        }
    }

    function submitRound() {
        var date = document.getElementById('round-date').value;
        var courseName = document.getElementById('round-course').value;
        var teeName = document.getElementById('round-tee').value;

        if (!date || !courseName || !teeName) {
            alert('Please fill in date, course, and tees.');
            return;
        }

        var holesPlayed = (document.querySelector('input[name="holes_played"]:checked') || {}).value || '18';
        var transport = (document.querySelector('input[name="transport"]:checked') || {}).value || '';
        var entryMode = (document.querySelector('input[name="entry_mode"]:checked') || {}).value || 'detailed';
        var notes = document.getElementById('round-notes').value;

        var payload = {
            date: date,
            course: courseName,
            tees: teeName,
            holes_played: holesPlayed,
            transport: transport,
            entry_mode: entryMode,
            notes: notes,
        };

        if (entryMode === 'detailed') {
            var holes = {};
            var allFilled = true;
            var total = 0;

            document.querySelectorAll('#scorecard-area tr[data-hole]').forEach(function (row) {
                var holeNum = row.dataset.hole;
                var gross = row.querySelector('.score-gross').value;
                var fwyEl = row.querySelector('.score-fwy');
                var girEl = row.querySelector('.score-gir');
                var putts = row.querySelector('.score-putts').value;
                var pen = row.querySelector('.score-pen').value;

                if (!gross) allFilled = false;
                total += parseInt(gross) || 0;

                holes[holeNum] = {
                    gross: gross || '',
                    fairway: fwyEl ? fwyEl.value : '',
                    gir: girEl ? girEl.value : '',
                    putts: putts || '',
                    penalties: pen || '0',
                };
            });

            if (!allFilled) {
                alert('Please enter a gross score for all holes.');
                return;
            }

            payload.holes = holes;
            payload.gross_total = String(total);
        } else {
            var grossScore = document.getElementById('gross-score').value;
            if (!grossScore) {
                alert('Please enter your gross score.');
                return;
            }
            payload.gross_total = grossScore;
        }

        fetch('/api/rounds', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.error) {
                alert(data.error);
                return;
            }
            fetch('/api/drafts/round', { method: 'DELETE' }).then(function () {
                window.location.href = '/rounds/' + data.date + '/' + data.index;
            });
        });
    }

    // --- Date step ---
    document.getElementById('round-date').addEventListener('blur', function () {
        if (this.value) showStep('course');
    });

    // --- Course step ---
    document.getElementById('round-course').addEventListener('change', function () {
        var val = this.value;
        if (!val) return;
        populateTees(val);
        document.getElementById('round-tee').value = '';
        showStep('tee');
    });

    // --- Tee step ---
    document.getElementById('round-tee').addEventListener('change', function () {
        if (this.value) showStep('holes');
    });

    // --- Holes played ---
    document.querySelectorAll('input[name="holes_played"]').forEach(function (radio) {
        radio.addEventListener('change', function () {
            _saveScorecardData();
            showStep('transport');
        });
    });

    // --- Transport ---
    document.querySelectorAll('input[name="transport"]').forEach(function (radio) {
        radio.addEventListener('change', function () {
            showStep('entry_mode');
        });
    });

    // --- Entry mode ---
    document.querySelectorAll('input[name="entry_mode"]').forEach(function (radio) {
        radio.addEventListener('change', function () {
            document.getElementById('scorecard-area').innerHTML = '';
            if (this.value === 'detailed') {
                buildScorecardGrid();
                showStep('holes_detail');
            } else {
                addGrossScoreInput();
                showStep('notes');
            }
        });
    });

    // --- Scorecard event delegation ---
    document.getElementById('scorecard-area').addEventListener('input', function (e) {
        if (e.target.classList.contains('score-gross')) {
            var row = e.target.closest('tr');
            var parEl = row ? row.querySelector('.hole-par') : null;
            var par = parseInt(parEl ? parEl.textContent : '');
            if (par) colorizeGross(e.target, par);
            updateSubtotals();
        } else if (e.target.classList.contains('score-putts')) {
            colorizePutts(e.target);
            updateSubtotals();
        } else if (e.target.classList.contains('score-pen')) {
            colorizePen(e.target);
            updateSubtotals();
        }
        _saveScorecardData();

        /* Sync back to mobile hole card */
        var row = e.target.closest('tr');
        if (row && row.dataset.hole) {
            syncDesktopToMobile(parseInt(row.dataset.hole));
        }
    });

    document.getElementById('scorecard-area').addEventListener('focusout', function (e) {
        if (!e.target.classList.contains('score-gross')) return;
        var allFilled = true;
        var inputs = document.querySelectorAll('#scorecard-area .score-gross');
        inputs.forEach(function (inp) {
            if (!inp.value) allFilled = false;
        });
        if (allFilled && inputs.length > 0) {
            showStep('notes');
        }
    });

    // --- Draft save (debounced) ---
    function debouncedDraftSave() {
        clearTimeout(draftTimer);
        draftTimer = setTimeout(saveDraft, 500);
    }

    wizard.addEventListener('change', debouncedDraftSave);
    wizard.addEventListener('input', debouncedDraftSave);

    // --- Submit ---
    document.getElementById('submit-round').addEventListener('click', submitRound);

    // --- Draft resume / discard ---
    fetch('/api/drafts/round')
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data && data.date) {
                document.getElementById('draft-resume').style.display = 'block';
                wizard.style.display = 'none';
            }
        });

    document.getElementById('draft-resume-btn').addEventListener('click', function () {
        document.getElementById('draft-resume').style.display = 'none';
        wizard.style.display = 'block';
        fetch('/api/drafts/round')
            .then(function (r) { return r.json(); })
            .then(function (draft) {
                resumeFromDraft(draft);
            });
    });

    document.getElementById('draft-discard-btn').addEventListener('click', function () {
        fetch('/api/drafts/round', { method: 'DELETE' }).then(function () {
            document.getElementById('draft-resume').style.display = 'none';
            wizard.style.display = 'block';
        });
    });
})();

// Chart filter chip interactivity
document.addEventListener('DOMContentLoaded', function() {
    var chartCard = document.querySelector('.ps-chart-card');
    if (!chartCard) return;

    var chips = chartCard.querySelectorAll('.ps-chip');
    var svg = chartCard.querySelector('svg');
    var allData = JSON.parse(chartCard.dataset.chartData || '{}');
    var tip = document.getElementById('chart-tip');

    if (!allData || !svg) return;

    function showTip(evt, value) {
        if (!tip) return;
        tip.textContent = value;
        tip.style.opacity = '1';
        var rect = chartCard.getBoundingClientRect();
        tip.style.left = (evt.clientX - rect.left + 12) + 'px';
        tip.style.top = (evt.clientY - rect.top - 28) + 'px';
    }

    function hideTip() {
        if (!tip) return;
        tip.style.opacity = '0';
    }

    function bindDataPoints() {
        var circles = svg.querySelectorAll('.ps-chart-dot, .ps-chart-dot-last');
        circles.forEach(function(c) {
            c.addEventListener('mouseenter', function(e) {
                showTip(e, this.dataset.value);
            });
            c.addEventListener('mouseleave', hideTip);
        });
    }

    function renderChart(data) {
        if (!data || !data.path) return;
        var parts = [];
        parts.push('<path d="' + data.area + '" fill="var(--ps-accent-dim)" />');
        parts.push('<path d="' + data.path + '" stroke="var(--ps-accent)" stroke-width="1.5" fill="none" />');
        data.points.forEach(function(pt) {
            parts.push('<circle class="ps-chart-dot" cx="' + pt.x + '" cy="' + pt.y + '" r="10" fill="transparent" style="pointer-events: all;" data-value="' + pt.v + '" />');
            parts.push('<circle cx="' + pt.x + '" cy="' + pt.y + '" r="2.4" fill="var(--ps-paper-2)" stroke="var(--ps-accent)" stroke-width="1.2" pointer-events="none" />');
        });
        var last = data.points[data.points.length - 1];
        var lastVal = data.hero_value || last.v;
        parts.push('<circle class="ps-chart-dot-last" cx="' + last.x + '" cy="' + last.y + '" r="10" fill="transparent" style="pointer-events: all;" data-value="' + lastVal + '" />');
        parts.push('<circle cx="' + last.x + '" cy="' + last.y + '" r="5.5" fill="var(--ps-accent)" pointer-events="none" />');
        var labelValue = data.hero_value || data.label_v;
        parts.push('<text x="' + data.label_x + '" y="' + data.label_y + '" font-family="JetBrains Mono, monospace" font-size="18" fill="var(--ps-accent)" text-anchor="end" font-weight="400">' + labelValue + '</text>');
        svg.innerHTML = parts.join('');
        bindDataPoints();
    }

    bindDataPoints();

    chips.forEach(function(chip) {
        chip.style.cursor = 'pointer';
        chip.addEventListener('click', function() {
            var range = this.dataset.range;
            chips.forEach(function(c) { c.classList.remove('is-on'); });
            this.classList.add('is-on');
            renderChart(allData[range] || {});
        });
    });
});
