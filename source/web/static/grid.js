(function () {
    var overlayEl = null;
    var gridRegion = document.querySelector("[data-grid-region]");
    if (!gridRegion) return;

    function createOverlay() {
        if (overlayEl) overlayEl.remove();
        overlayEl = document.createElement("div");
        overlayEl.id = "grid-overlay";
        overlayEl.style.cssText =
            "position:absolute;top:0;left:0;right:0;bottom:0;pointer-events:none;z-index:0;";
        gridRegion.style.position = "relative";
        gridRegion.appendChild(overlayEl);
    }

    function drawGrid() {
        if (!overlayEl) return;
        var panels = document.querySelectorAll("[data-grid-panel]");
        if (panels.length === 0) {
            overlayEl.innerHTML = "";
            return;
        }

        var regionRect = gridRegion.getBoundingClientRect();
        var offsetX = regionRect.left;
        var offsetY = regionRect.top;

        var horizontalLines = [];
        var verticalLines = [];
        var crosshairDots = [];

        var uniqueX = {};
        var uniqueY = {};

        panels.forEach(function (panel) {
            var r = panel.getBoundingClientRect();
            var left = r.left - offsetX;
            var right = r.right - offsetX;
            var top = r.top - offsetY;
            var bottom = r.bottom - offsetY;

            left = Math.round(left * 10) / 10;
            right = Math.round(right * 10) / 10;
            top = Math.round(top * 10) / 10;
            bottom = Math.round(bottom * 10) / 10;

            uniqueX[left] = true;
            uniqueX[right] = true;
            uniqueY[top] = true;
            uniqueY[bottom] = true;
        });

        var xPositions = Object.keys(uniqueX).map(Number).sort(function (a, b) { return a - b; });
        var yPositions = Object.keys(uniqueY).map(Number).sort(function (a, b) { return a - b; });

        yPositions.forEach(function (y) {
            horizontalLines.push(
                '<div style="position:absolute;left:0;right:0;top:' + y +
                'px;height:1px;background:var(--grid-major);"></div>'
            );
        });

        xPositions.forEach(function (x) {
            verticalLines.push(
                '<div style="position:absolute;top:0;bottom:0;left:' + x +
                'px;width:1px;background:var(--grid-major);"></div>'
            );
        });

        yPositions.forEach(function (y) {
            xPositions.forEach(function (x) {
                crosshairDots.push(
                    '<div style="position:absolute;top:' + y +
                    'px;left:' + x +
                    'px;width:3px;height:3px;background:var(--grid-crosshair);border-radius:50%;margin:-1.5px;"></div>'
                );
            });
        });

        overlayEl.innerHTML = horizontalLines.join("") + verticalLines.join("") + crosshairDots.join("");
    }

    createOverlay();
    drawGrid();

    var resizeTimer;
    window.addEventListener("resize", function () {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(drawGrid, 100);
    });
})();
