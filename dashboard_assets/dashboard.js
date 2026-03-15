const apiPath = document.documentElement.dataset.apiPath || "/api/current-display-state";
const pollIntervalMs = Number(document.documentElement.dataset.pollIntervalMs || 2000);

const elements = {
    time: document.getElementById("time-value"),
    slot: document.getElementById("slot-value"),
    category: document.getElementById("category-value"),
    setup: document.getElementById("setup-value"),
    punchline: document.getElementById("punchline-value"),
    rawData: document.getElementById("raw-data"),
    refreshStatus: document.getElementById("refresh-status"),
    lastUpdated: document.getElementById("last-updated"),
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
    elements.rawData.textContent = JSON.stringify(state.data || {}, null, 2);
    elements.refreshStatus.textContent = state.has_data ? "Live snapshot loaded" : "Waiting for runtime state";
    elements.lastUpdated.textContent = state.updated_at
        ? `Updated ${state.updated_at}`
        : "No snapshot saved yet";
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

refreshState();
window.setInterval(refreshState, pollIntervalMs);
