(function () {
    var overlayEl = null;

    function createOverlay() {
        if (overlayEl) overlayEl.remove();
        overlayEl = document.createElement("div");
        overlayEl.id = "grid-overlay";
        overlayEl.style.cssText =
            "position:fixed;top:0;left:0;width:100vw;height:100vh;pointer-events:none;z-index:-1;overflow:hidden;opacity:0;transition:opacity 0.5s ease;";
        document.body.appendChild(overlayEl);
    }

    function drawGrid() {
        if (!overlayEl) return;
        var panels = document.querySelectorAll("[data-grid-panel], .recent-rounds");
        if (panels.length === 0) {
            overlayEl.innerHTML = "";
            return;
        }

        var horizontalLines = [];
        var verticalLines = [];

        var uniqueX = {};
        var uniqueY = {};

        panels.forEach(function (panel) {
            var r = panel.getBoundingClientRect();
            var left = Math.round(r.left * 10) / 10;
            var right = Math.round(r.right * 10) / 10;
            var top = Math.round(r.top * 10) / 10;
            var bottom = Math.round(r.bottom * 10) / 10;

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
                'px;height:2px;background:var(--grid-major);"></div>'
            );
        });

        xPositions.forEach(function (x) {
            verticalLines.push(
                '<div style="position:absolute;top:0;bottom:0;left:' + x +
                'px;width:2px;background:var(--grid-major);"></div>'
            );
        });

        var dotGrid = [];
        var dotSpacing = 20;
        var viewportWidth = window.innerWidth;
        var viewportHeight = window.innerHeight;

        for (var x = 0; x <= viewportWidth; x += dotSpacing) {
            for (var y = 0; y <= viewportHeight; y += dotSpacing) {
                dotGrid.push(
                    '<div style="position:absolute;top:' + y +
                    'px;left:' + x +
                    'px;width:1px;height:1px;background:var(--grid-bg);"></div>'
                );
            }
        }

        overlayEl.innerHTML = dotGrid.join("") + horizontalLines.join("") + verticalLines.join("");
    }

    createOverlay();

    var lastAnimated = document.querySelector(".recent-rounds");
    if (lastAnimated) {
        lastAnimated.addEventListener("animationend", function () {
            drawGrid();
            overlayEl.style.opacity = "1";
        }, { once: true });
    }

    var resizeTimer;
    window.addEventListener("resize", function () {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(drawGrid, 100);
    });

    window.addEventListener("scroll", drawGrid, { passive: true });
})();
