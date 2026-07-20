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

/**
 * Poll the Builder Agent's status every 10s and refresh the Builder
 * card in place. Sprint 006 asked for the card to "update automatically
 * when the Builder's state changes" — a plain hx-trigger poll (like the
 * one on #eventos) fetches but discards the response (hx-swap="none"),
 * so it would not actually satisfy that requirement. This is the
 * minor, backward-compatible improvement documented in the Sprint 006
 * delivery: a small fetch loop that writes the response into the
 * existing card fields by id. No-op on any page without the card.
 */
(function pollBuilderStatus() {
    const statusEl = document.getElementById("builder-status");
    if (!statusEl) return;

    async function refresh() {
        try {
            const res = await fetch("/api/builder/status");
            if (!res.ok) return;
            const data = await res.json();
            document.getElementById("builder-status").textContent = data.status;
            document.getElementById("builder-current-mission").textContent = data.current_mission_id || "—";
            document.getElementById("builder-completed-today").textContent = data.completed_today;
            document.getElementById("builder-failed-today").textContent = data.failed_today;
            document.getElementById("builder-current-handler").textContent = data.current_handler || "—";
            document.getElementById("builder-last-activity").textContent = data.last_activity || "—";
        } catch (err) {
            // Transient network error: the next poll will retry.
        }
    }

    refresh();
    setInterval(refresh, 10000);
})();
