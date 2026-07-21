/**
 * The Window <-> ORION Runtime API integration (BETA 007).
 *
 * The Window itself never executes a mission (see orion.window.routes'
 * own docstring: "no execution-trigger API route, by design"). This
 * file is the one place The Window talks to the Runtime API
 * (orion.runtime.api, port 8090 by default -- see
 * orion.runtime.config.RuntimeConfig, same convention assumed here)
 * over plain fetch()/EventSource, never by shelling out to a script.
 *
 * Two independent, no-op-if-absent behaviors:
 *   1. "Nueva misión" button on /missions -> POST {runtimeBase}/missions.
 *   2. Live timeline on /missions/<id> -> GET {runtimeBase}/events (SSE),
 *      filtered client-side to this page's mission_id, so the page
 *      "se actualiza sola sin refresh" per this Sprint's requirement.
 */
(function () {
    "use strict";

    // Same host as The Window itself, but the Runtime API's own port
    // (RuntimeConfig.port defaults to 8090; The Window's own server
    // owns 8080 -- see orion.runtime.config's module docstring). No
    // config knob for this yet; if a deployment moves the Runtime API
    // to a different host/port, this is the one line to change.
    function runtimeBase() {
        return window.location.protocol + "//" + window.location.hostname + ":8090";
    }

    // --- 1. "Nueva misión" (missions.html) ---------------------------------
    (function newMissionForm() {
        const openBtn = document.getElementById("new-mission-btn");
        const form = document.getElementById("new-mission-form");
        const cancelBtn = document.getElementById("new-mission-cancel");
        const statusEl = document.getElementById("new-mission-status");
        if (!openBtn || !form) return;

        openBtn.addEventListener("click", function () {
            form.hidden = !form.hidden;
        });
        if (cancelBtn) {
            cancelBtn.addEventListener("click", function () {
                form.hidden = true;
                statusEl.textContent = "";
            });
        }

        form.addEventListener("submit", async function (evt) {
            evt.preventDefault();
            const title = document.getElementById("new-mission-title").value.trim();
            if (!title) return;
            const description = document.getElementById("new-mission-description").value.trim();
            const projectId = document.getElementById("new-mission-project").value.trim();

            statusEl.textContent = "Enviando al Runtime...";
            try {
                const res = await fetch(runtimeBase() + "/missions", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        title: title,
                        description: description,
                        project_id: projectId,
                        tags: [],
                    }),
                });
                if (!res.ok) {
                    statusEl.textContent =
                        "El Runtime respondio con un error (" + res.status + "). " +
                        "Verifica que 'orion runtime start' este corriendo en el puerto 8090.";
                    return;
                }
                const data = await res.json();
                statusEl.textContent = "Mision " + data.mission_id + " encolada (" + data.queue_status + ").";
                setTimeout(function () {
                    window.location = "/missions/" + data.mission_id;
                }, 800);
            } catch (err) {
                statusEl.textContent =
                    "No se pudo contactar al Runtime en " + runtimeBase() +
                    ". Verifica que 'orion runtime start' este corriendo.";
            }
        });
    })();

    // --- 2. Live timeline via SSE (mission_detail.html) ---------------------
    (function liveMissionTimeline() {
        const root = document.getElementById("mission-detail");
        if (!root) return;
        const missionId = root.getAttribute("data-mission-id");
        if (!missionId) return;

        const indicator = document.getElementById("live-indicator");
        const statusValueEl = document.getElementById("mission-status-value");
        const timelineBody = document.getElementById("timeline-body");

        let source;
        try {
            source = new EventSource(runtimeBase() + "/events");
        } catch (err) {
            return; // EventSource unsupported or Runtime unreachable -- page still works, just static.
        }

        source.onopen = function () {
            if (indicator) indicator.classList.add("connected");
        };
        source.onerror = function () {
            if (indicator) indicator.classList.remove("connected");
        };

        source.onmessage = function (evt) {
            let payload;
            try {
                payload = JSON.parse(evt.data);
            } catch (err) {
                return;
            }
            if (payload.mission_id !== missionId) return;

            if (timelineBody) {
                const emptyRow = timelineBody.querySelector("td[colspan]");
                if (emptyRow) emptyRow.closest("tr").remove();

                const row = document.createElement("tr");
                const cells = [payload.timestamp, payload.type, payload.message, payload.source];
                cells.forEach(function (text) {
                    const td = document.createElement("td");
                    td.textContent = text || "—";
                    row.appendChild(td);
                });
                timelineBody.appendChild(row);
            }

            if (statusValueEl && payload.type === "status_changed") {
                // "Estado cambiado de X a Y." -- extract Y without a
                // second round-trip to the Mission Framework.
                const match = /a\s+([A-Z_]+)\.?$/.exec(payload.message || "");
                if (match) statusValueEl.textContent = match[1];
            }
        };
    })();
})();
