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
    var wizard = document.getElementById("round-wizard");
    if (!wizard) return;

    var coursesData = window._courses;
    var stepCourse = document.getElementById("round-course");
    var stepTee = document.getElementById("round-tee");
    var teeParent = document.querySelector('[data-step="tee"]');
    var holesParent = document.querySelector('[data-step="holes"]');
    var transportParent = document.querySelector('[data-step="transport"]');
    var entryParent = document.querySelector('[data-step="entry_mode"]');
    var detailParent = document.querySelector('[data-step="holes_detail"]');
    var notesParent = document.querySelector('[data-step="notes"]');

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
            html += '<td>' + (yds || "&mdash;") + '</td>';
            html += '<td><input type="number" class="hole-input hole-gross" min="1" max="20" size="2"></td>';
            html += '<td><select class="hole-input hole-fw"><option value="">&mdash;</option>'
                 +  '<option value="H">H</option><option value="L">L</option><option value="R">R</option>'
                 +  '<option value="OBL">OBL</option><option value="OBR">OBR</option>'
                 +  (par === 3 ? '<option value="N">N</option>' : '')
                 +  '</select></td>';
            html += '<td><select class="hole-input hole-gir"><option value="">&mdash;</option>'
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
        html += '<td class="total-gross">&mdash;</td><td></td><td></td>';
        html += '<td class="total-putts">&mdash;</td><td class="total-pen">&mdash;</td>';
        html += '</tr></tbody></table>';

        area.innerHTML = html;

        area.querySelectorAll(".hole-gross,.hole-putts,.hole-pen").forEach(function (el) {
            el.addEventListener("input", updateTotals);
        });

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
        if (tg) tg.textContent = gross || "\u2014";
        if (tp) tp.textContent = putts;
        if (tn) tn.textContent = pen;
    }

    var draftTimer = null;
    wizard.addEventListener("change", function () {
        clearTimeout(draftTimer);
        draftTimer = setTimeout(saveDraft, 500);
    });

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
})();

(function () {
    var wizard = document.getElementById("course-wizard");
    if (!wizard) return;

    var teeNames = [];
    var teeFields = {};

    var btnAddTee = document.getElementById("btn-add-tee");
    var teesContainer = document.getElementById("tees-container");
    var holesArea = document.getElementById("course-holes-area");

    function renderTeFields() {
        var html = "";
        teeNames.forEach(function (name, idx) {
            html += '<div class="tee-set" data-tee-idx="' + idx + '">';
            html += '<div class="tee-set-header">';
            html += '<span class="tee-set-title">Tee #' + (idx + 1) + '</span>';
            html += '<button class="btn tee-remove-btn" data-tee-idx="' + idx + '">&times;</button>';
            html += '</div>';
            html += '<div class="tee-fields">';
            html += '<input type="text" class="step-input tee-name" placeholder="Tee name (e.g. Blue)" value="' + (teeFields[name + "_name"] || "") + '">';
            html += '<div class="tee-numbers">';
            html += '<label>Rating <input type="number" class="step-input tee-rating" step="0.1" placeholder="72.0" value="' + (teeFields[name + "_rating"] || "") + '"></label>';
            html += '<label>Slope <input type="number" class="step-input tee-slope" step="1" placeholder="113" value="' + (teeFields[name + "_slope"] || "") + '"></label>';
            html += '<label>Yardage <input type="number" class="step-input tee-yardage" step="1" placeholder="6500" value="' + (teeFields[name + "_yardage"] || "") + '"></label>';
            html += '</div>';
            html += '</div>';
            html += '</div>';
        });
        teesContainer.innerHTML = html;

        document.querySelectorAll(".tee-remove-btn").forEach(function (btn) {
            btn.addEventListener("click", function () {
                var idx = parseInt(this.dataset.teeIdx);
                teeNames.splice(idx, 1);
                renderTeFields();
                buildCourseHoles();
            });
        });
    }

    function buildCourseHoles() {
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
            html += '<tr data-hole="' + i + '">';
            html += '<td>' + i + '</td>';
            html += '<td><input type="number" class="hole-input course-par" min="1" max="7" value="4" size="2"></td>';
            html += '<td><input type="number" class="hole-input course-index" min="1" max="18" value="' + i + '" size="2"></td>';
            currentTees.forEach(function () {
                html += '<td><input type="number" class="hole-input course-yardage" min="1" max="999" size="3"></td>';
            });
            html += '</tr>';
        }

        html += '</tbody></table>';
        holesArea.innerHTML = html;
    }

    btnAddTee.addEventListener("click", function () {
        var name = "tee_" + teeNames.length;
        teeNames.push(name);
        renderTeFields();
        buildCourseHoles();
    });

    // Add initial tee
    teeNames.push("tee_0");
    renderTeFields();
    buildCourseHoles();

    // Draft save
    function saveCourseDraft() {
        var draft = {
            name: document.getElementById("course-name").value,
            location: document.getElementById("course-location").value,
            tees: {},
        };
        document.querySelectorAll(".tee-set").forEach(function (set, idx) {
            var teeName = set.querySelector(".tee-name")?.value || "";
            draft.tees[teeName || ("tee_" + idx)] = {
                name: teeName,
                rating: set.querySelector(".tee-rating")?.value || "",
                slope: set.querySelector(".tee-slope")?.value || "",
                yardage: set.querySelector(".tee-yardage")?.value || "",
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
                if (draft.location) document.getElementById("course-location").value = draft.location;
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

        var tees = {};
        document.querySelectorAll(".tee-set").forEach(function (set) {
            var teeName = set.querySelector(".tee-name")?.value?.trim();
            if (!teeName) return;
            tees[teeName] = {
                rating: set.querySelector(".tee-rating")?.value || "",
                slope: set.querySelector(".tee-slope")?.value || "",
                yardage: set.querySelector(".tee-yardage")?.value || "",
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
            location: document.getElementById("course-location").value.trim(),
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
