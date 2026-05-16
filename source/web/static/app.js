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
    var form = document.getElementById("settings-form");
    if (!form) return;

    function saveSettings() {
        var theme = document.querySelector(".theme-swatch[data-active]")?.dataset?.theme || "green";
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
        fetch("/api/settings", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data),
        });
    }

    document.querySelectorAll(".theme-swatch").forEach(function (swatch) {
        swatch.addEventListener("click", function () {
            document.querySelectorAll(".theme-swatch").forEach(function (s) {
                s.removeAttribute("data-active");
            });
            this.setAttribute("data-active", "true");
            document.body.className = "theme-" + this.dataset.theme;
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
