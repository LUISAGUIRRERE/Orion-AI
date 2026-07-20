/**
 * The Window — minimal client-side behavior.
 * Keeps the top bar clock live. No build step, no framework.
 */
(function updateClock() {
    const clockEl = document.getElementById("clock");
    if (!clockEl) return;

    function tick() {
        const now = new Date();
        const date = now.toISOString().slice(0, 10);
        const time = now.toISOString().slice(11, 16);
        clockEl.textContent = date + " · " + time + " UTC";
    }

    tick();
    setInterval(tick, 60000);
})();
