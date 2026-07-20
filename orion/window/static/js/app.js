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

/**
 * Poll the COO Agent's status and metrics every 10s and refresh both the
 * COO card and the Executive Summary section in place, for the same
 * reason as pollBuilderStatus above: hx-swap="none" polling would fetch
 * but discard the response. Two endpoints are combined (status + metrics)
 * because the COO card and Executive Summary both depend on metrics that
 * are recalculated on demand rather than stored on the COO's own state.
 * No-op on any page without the COO card.
 */
(function pollCOOStatus() {
    const statusEl = document.getElementById("coo-status");
    if (!statusEl) return;

    async function refresh() {
        try {
            const [statusRes, metricsRes] = await Promise.all([
                fetch("/api/coo/status"),
                fetch("/api/coo/metrics"),
            ]);
            if (!statusRes.ok || !metricsRes.ok) return;
            const status = await statusRes.json();
            const metrics = await metricsRes.json();

            document.getElementById("coo-status").textContent = status.status;
            document.getElementById("coo-assignments-today").textContent = status.assignments_today;
            document.getElementById("coo-last-assignment").textContent = status.last_assignment || "\u2014";
            document.getElementById("coo-builders-available").textContent = metrics.builders_available;
            document.getElementById("coo-builders-busy").textContent = metrics.builders_busy;
            document.getElementById("coo-pending-missions").textContent = metrics.queue_size;
            document.getElementById("coo-average-mission-time").textContent = metrics.average_execution_seconds;

            const execTotal = document.getElementById("exec-total-missions");
            if (execTotal) {
                execTotal.textContent = metrics.missions_total;
                document.getElementById("exec-ready").textContent = metrics.missions_ready;
                document.getElementById("exec-running").textContent = metrics.missions_running;
                document.getElementById("exec-review").textContent = metrics.missions_review;
                document.getElementById("exec-done-today").textContent = metrics.missions_done_today;
                document.getElementById("exec-failed-today").textContent = metrics.missions_failed_today;
                document.getElementById("exec-avg-completion").textContent = metrics.average_execution_seconds;
                document.getElementById("exec-queue-size").textContent = metrics.queue_size;
            }
        } catch (err) {
            // Transient network error: the next poll will retry.
        }
    }

    refresh();
    setInterval(refresh, 10000);
})();
