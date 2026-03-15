const apiPath = document.documentElement.dataset.apiPath || "/api/current-display-state";
const skipApiPath = document.documentElement.dataset.skipApiPath || "/api/skip-category";
const pollIntervalMs = Number(document.documentElement.dataset.pollIntervalMs || 2000);

const elements = {
    time: document.getElementById("time-value"),
    slot: document.getElementById("slot-value"),
    category: document.getElementById("category-value"),
    setup: document.getElementById("setup-value"),
    punchline: document.getElementById("punchline-value"),
    refreshStatus: document.getElementById("refresh-status"),
    lastUpdated: document.getElementById("last-updated"),
    skipCategoryButton: document.getElementById("skip-category-button"),
    actionStatus: document.getElementById("action-status"),
};

function displayText(value) {
    if (value === null || value === undefined || value === "") {
        return "--";
    }
    return String(value);
}

function applyState(state) {
    elements.time.textContent = displayText(state.time);
    elements.slot.textContent = displayText(state.slot);
    elements.category.textContent = displayText(state.category);
    elements.setup.textContent = displayText(state.setup);
    elements.punchline.textContent = displayText(state.punchline);
    elements.refreshStatus.textContent = state.has_data ? "Live snapshot loaded" : "Waiting for runtime state";
    elements.lastUpdated.textContent = state.updated_at
        ? `Updated ${state.updated_at}`
        : "No snapshot saved yet";
}

function setActionStatus(message, state = "idle") {
    elements.actionStatus.textContent = message;
    elements.actionStatus.dataset.state = state;
}

async function refreshState() {
    try {
        const response = await fetch(apiPath, { cache: "no-store" });
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const state = await response.json();
        applyState(state);
    } catch (error) {
        elements.refreshStatus.textContent = "Refresh failed";
        elements.lastUpdated.textContent = error.message;
    }
}

async function skipCategory() {
    if (!elements.skipCategoryButton) {
        return;
    }

    elements.skipCategoryButton.disabled = true;
    setActionStatus("Requesting category skip...", "pending");

    try {
        const response = await fetch(skipApiPath, {
            method: "POST",
            cache: "no-store",
        });
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const result = await response.json();
        elements.refreshStatus.textContent = "Skip requested";
        setActionStatus(
            `Skip requested at ${displayText(result.requested_at)}`,
            "success",
        );
        await refreshState();
    } catch (error) {
        setActionStatus(`Skip failed: ${error.message}`, "error");
    } finally {
        elements.skipCategoryButton.disabled = false;
    }
}

if (elements.skipCategoryButton) {
    elements.skipCategoryButton.addEventListener("click", skipCategory);
}

refreshState();
window.setInterval(refreshState, pollIntervalMs);
