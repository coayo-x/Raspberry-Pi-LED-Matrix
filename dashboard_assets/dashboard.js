const currentDisplayApi =
    document.documentElement.dataset.currentDisplayApi || "/api/current-display-state";
const controlStateApi =
    document.documentElement.dataset.controlStateApi || "/api/control-state";
const skipApiPath =
    document.documentElement.dataset.skipApiPath || "/api/skip-category";
const switchApiPath =
    document.documentElement.dataset.switchApiPath || "/api/switch-category";
const adminLoginApi =
    document.documentElement.dataset.adminLoginApi || "/api/admin/login";
const adminLogoutApi =
    document.documentElement.dataset.adminLogoutApi || "/api/admin/logout";
const adminControlLockApi =
    document.documentElement.dataset.adminControlLockApi || "/api/admin/control-lock";
const apiPath = document.documentElement.dataset.apiPath || "/api/current-display-state";
const skipApiPath = document.documentElement.dataset.skipApiPath || "/api/skip-category";
const switchApiPath = document.documentElement.dataset.switchApiPath || "/api/switch-category";
const pollIntervalMs = Number(document.documentElement.dataset.pollIntervalMs || 2000);

const elements = {
    time: document.getElementById("time-value"),
    slot: document.getElementById("slot-value"),
    category: document.getElementById("category-value"),
    setup: document.getElementById("setup-value"),
    punchline: document.getElementById("punchline-value"),
    refreshStatus: document.getElementById("refresh-status"),
    lastUpdated: document.getElementById("last-updated"),
    publicControlMode: document.getElementById("public-control-mode"),
    skipCategoryButton: document.getElementById("skip-category-button"),
    switchCategorySelect: document.getElementById("switch-category-select"),
    switchCategoryButton: document.getElementById("switch-category-button"),
    skipCategoryNote: document.getElementById("skip-category-note"),
    switchCategoryNote: document.getElementById("switch-category-note"),
    actionStatus: document.getElementById("action-status"),
    pokemonCard: document.getElementById("pokemon-card"),
    pokemonImage: document.getElementById("pokemon-image"),
    pokemonImageFallback: document.getElementById("pokemon-image-fallback"),
    pokemonName: document.getElementById("pokemon-name"),
    pokemonMeta: document.getElementById("pokemon-meta"),
    adminControlButton: document.getElementById("admin-control-button"),
    adminLoginModal: document.getElementById("admin-login-modal"),
    adminControlsModal: document.getElementById("admin-controls-modal"),
    modalCloseButtons: Array.from(document.querySelectorAll("[data-close-modal]")),
    adminDisabledMessage: document.getElementById("admin-disabled-message"),
    adminLoginCopy: document.getElementById("admin-login-copy"),
    adminLoginForm: document.getElementById("admin-login-form"),
    adminUsername: document.getElementById("admin-username"),
    adminPassword: document.getElementById("admin-password"),
    adminLoginButton: document.getElementById("admin-login-button"),
    adminLoginStatus: document.getElementById("admin-login-status"),
    adminPanel: document.getElementById("admin-panel"),
    adminControlsSummary: document.getElementById("admin-controls-summary"),
    adminSessionBadge: document.getElementById("admin-session-badge"),
    adminSkipLockState: document.getElementById("admin-skip-lock-state"),
    adminSwitchLockState: document.getElementById("admin-switch-lock-state"),
    toggleSkipLockButton: document.getElementById("toggle-skip-lock-button"),
    toggleSwitchLockButton: document.getElementById("toggle-switch-lock-button"),
    adminLogoutButton: document.getElementById("admin-logout-button"),
    adminActionStatus: document.getElementById("admin-action-status"),
};

let latestControlPayload = null;

    skipCategoryButton: document.getElementById("skip-category-button"),
    switchCategorySelect: document.getElementById("switch-category-select"),
    switchCategoryButton: document.getElementById("switch-category-button"),
    actionStatus: document.getElementById("action-status"),
};

function displayText(value) {
    if (value === null || value === undefined || value === "") {
        return "--";
    }
    return String(value);
}

function titleCase(value) {
    if (!value) {
        return "Unknown";
    }

    const text = String(value);
    return text.charAt(0).toUpperCase() + text.slice(1);
}

function setMessage(element, message, state = "idle") {
    if (!element) {
        return;
    }

    element.textContent = message;
    element.dataset.state = state;
}

function describeResultError(error, fallbackMessage) {
    const payload = error?.result;
    if (payload?.error) {
        if (payload.retry_after_seconds) {
            return `${payload.error} Retry in ${payload.retry_after_seconds}s.`;
        }
        return payload.error;
    }

    if (error?.message) {
        return `${fallbackMessage}: ${error.message}`;
    }

    return fallbackMessage;
}

async function parseJsonResponse(response) {
    try {
        return await response.json();
    } catch {
        return null;
    }
}

async function fetchJson(url, options = {}) {
    const response = await fetch(url, {
        cache: "no-store",
        credentials: "same-origin",
        ...options,
    });
    const payload = await parseJsonResponse(response);
    if (!response.ok) {
        const error = new Error(payload?.error || `HTTP ${response.status}`);
        error.status = response.status;
        error.result = payload;
        throw error;
    }
    return payload;
}

function hasOpenModal() {
    return (
        Boolean(elements.adminLoginModal && !elements.adminLoginModal.hidden) ||
        Boolean(elements.adminControlsModal && !elements.adminControlsModal.hidden)
    );
}

function syncBodyModalState() {
    document.body.classList.toggle("modal-open", hasOpenModal());
}

function showModal(modal) {
    if (!modal) {
        return;
    }
    modal.hidden = false;
    syncBodyModalState();
}

function hideModal(modal) {
    if (!modal) {
        return;
    }
    modal.hidden = true;
    syncBodyModalState();
}

function closeAllModals() {
    hideModal(elements.adminLoginModal);
    hideModal(elements.adminControlsModal);
}

function openLoginModal() {
    hideModal(elements.adminControlsModal);
    showModal(elements.adminLoginModal);
    if (
        elements.adminUsername &&
        elements.adminLoginForm &&
        !elements.adminLoginForm.hidden
    ) {
        elements.adminUsername.focus();
    }
}

function openControlsModal() {
    if (!latestControlPayload?.auth?.authenticated) {
        openLoginModal();
        return;
    }

    hideModal(elements.adminLoginModal);
    showModal(elements.adminControlsModal);
}

function openAdminControlFlow() {
    if (latestControlPayload?.auth?.authenticated) {
        openControlsModal();
        return;
    }
    openLoginModal();
}

function showPokemonFallback(message) {
    if (elements.pokemonImage) {
        elements.pokemonImage.hidden = true;
        elements.pokemonImage.removeAttribute("src");
    }
    if (elements.pokemonImageFallback) {
        elements.pokemonImageFallback.hidden = false;
        elements.pokemonImageFallback.textContent = message;
    }
}

function renderPokemonCard(state) {
    const data = state?.data || {};
    const isPokemon = state?.category === "pokemon";
    if (!elements.pokemonCard) {
        return;
    }

    elements.pokemonCard.hidden = !isPokemon;
    if (!isPokemon) {
        return;
    }

    const name = data.name || state.setup || "Unknown Pokemon";
    const types = Array.isArray(data.types) ? data.types.filter(Boolean) : [];
    const metaParts = [];
    if (types.length > 0) {
        metaParts.push(types.join(" / "));
    }
    if (data.hp !== undefined && data.hp !== null && data.hp !== "") {
        metaParts.push(`HP ${data.hp}`);
    }
    if (data.attack !== undefined && data.attack !== null && data.attack !== "") {
        metaParts.push(`ATK ${data.attack}`);
    }
    if (data.defense !== undefined && data.defense !== null && data.defense !== "") {
        metaParts.push(`DEF ${data.defense}`);
    }

    elements.pokemonName.textContent = displayText(name);
    elements.pokemonMeta.textContent =
        metaParts.length > 0
            ? metaParts.join(" | ")
            : "Pokemon data loaded without artwork metadata.";

    const imageUrl = data.image_url;
    if (!imageUrl) {
        showPokemonFallback("Artwork unavailable");
        return;
    }

    if (elements.pokemonImage) {
        elements.pokemonImage.hidden = false;
        elements.pokemonImage.alt = `${name} artwork`;
        if (elements.pokemonImage.src !== imageUrl) {
            elements.pokemonImage.src = imageUrl;
        }
    }
    if (elements.pokemonImageFallback) {
        elements.pokemonImageFallback.hidden = true;
    }
}

function applySnapshotState(state) {
function applyState(state) {
    elements.time.textContent = displayText(state.time);
    elements.slot.textContent = displayText(state.slot);
    elements.category.textContent = displayText(state.category);
    elements.setup.textContent = displayText(state.setup);
    elements.punchline.textContent = displayText(state.punchline);
    elements.refreshStatus.textContent = state.has_data
        ? "Live snapshot loaded"
        : "Waiting for runtime state";
    elements.lastUpdated.textContent = state.updated_at
        ? `Updated ${state.updated_at}`
        : "No snapshot saved yet";
    renderPokemonCard(state);
}

function buildControlNote(control) {
    if (!control) {
        return "Control state unavailable.";
    }

    if (control.locked && !control.admin_override) {
        return "Locked by admin.";
    }

    if (control.admin_override) {
        return "Publicly locked. Admin override active.";
    }

    if (control.cooldown_remaining_seconds > 0) {
        return `Cooldown active: ${control.cooldown_remaining_seconds}s remaining.`;
    }

    if (control.pending_request_count > 0) {
        return "Accepted. Waiting for runtime handoff.";
    }

    return "Ready.";
}

function applyPublicControlState(control, button, noteElement) {
    if (!control || !button || !noteElement) {
        return;
    }

    noteElement.textContent = buildControlNote(control);
    button.disabled = !control.available;
}

function applyAdminLockState(control, button, labelElement) {
    if (!control || !button || !labelElement) {
        return;
    }

    labelElement.textContent = control.locked
        ? "Locked for public use."
        : "Public access is open.";
    button.textContent = control.locked
        ? `Unlock ${control.label}`
        : `Lock ${control.label}`;
    button.disabled = false;
}

function applyControlPayload(payload) {
    latestControlPayload = payload;
    const auth = payload?.auth || {};
    const controls = payload?.controls || {};
    const isAdmin = Boolean(auth.authenticated);
    const anyPublicLock = Object.values(controls).some(
        (control) => control && control.locked,
    );

    applyPublicControlState(
        controls.skip_category,
        elements.skipCategoryButton,
        elements.skipCategoryNote,
    );
    applyPublicControlState(
        controls.switch_category,
        elements.switchCategoryButton,
        elements.switchCategoryNote,
    );

    if (elements.switchCategorySelect) {
        const switchControl = controls.switch_category;
        elements.switchCategorySelect.disabled = !switchControl?.available;
    }

    if (elements.publicControlMode) {
        elements.publicControlMode.textContent = isAdmin
            ? "Admin Session"
            : anyPublicLock
              ? "Restricted"
              : "Open";
    }

    if (!auth.configured) {
        elements.adminDisabledMessage.hidden = false;
        elements.adminLoginForm.hidden = true;
        elements.adminPanel.hidden = true;
        elements.adminLoginCopy.textContent =
            "Local admin credentials are not configured on this dashboard host.";
        elements.adminControlsSummary.textContent =
            "Configure local admin credentials to use protected controls.";
        elements.adminSessionBadge.textContent = "Unavailable";
        elements.toggleSkipLockButton.disabled = true;
        elements.toggleSwitchLockButton.disabled = true;
        elements.adminLogoutButton.disabled = true;
        setMessage(
            elements.adminLoginStatus,
            "Admin auth is disabled until credentials are configured.",
            "error",
        );
        hideModal(elements.adminControlsModal);
        return;
    }

    elements.adminDisabledMessage.hidden = true;
    elements.adminLoginForm.hidden = false;
    elements.adminLoginCopy.textContent =
        "Sign in with the configured admin account to access protected controls.";

    if (isAdmin) {
        elements.adminPanel.hidden = false;
        elements.adminSessionBadge.textContent = `${displayText(auth.username)} active`;
        elements.adminControlsSummary.textContent = auth.expires_at
            ? `Admin session active until ${auth.expires_at}.`
            : "Admin session active.";
        setMessage(
            elements.adminLoginStatus,
            `Signed in as ${displayText(auth.username)}.`,
            "success",
        );
    } else {
        elements.adminPanel.hidden = true;
        elements.adminSessionBadge.textContent = "Signed out";
        elements.adminControlsSummary.textContent =
            "Sign in to manage public control locks.";
            "Sign in to manage access locks.";
        if (
            !elements.adminLoginStatus.dataset.state ||
            elements.adminLoginStatus.dataset.state === "success"
        ) {
            setMessage(elements.adminLoginStatus, "Admin session inactive.", "idle");
        }
        hideModal(elements.adminControlsModal);
    }

    applyAdminLockState(
        controls.skip_category,
        elements.toggleSkipLockButton,
        elements.adminSkipLockState,
    );
    applyAdminLockState(
        controls.switch_category,
        elements.toggleSwitchLockButton,
        elements.adminSwitchLockState,
    );

    elements.toggleSkipLockButton.disabled = !isAdmin;
    elements.toggleSwitchLockButton.disabled = !isAdmin;
    elements.adminLogoutButton.disabled = !isAdmin;
}

async function refreshDashboard() {
    const [stateResult, controlResult] = await Promise.allSettled([
        fetchJson(currentDisplayApi),
        fetchJson(controlStateApi),
    ]);

    if (stateResult.status === "fulfilled") {
        applySnapshotState(stateResult.value);
    } else {
        elements.refreshStatus.textContent = "Snapshot refresh failed";
        elements.lastUpdated.textContent = stateResult.reason.message;
    }

    if (controlResult.status === "fulfilled") {
        applyControlPayload(controlResult.value);
    } else {
        setMessage(
            elements.actionStatus,
            describeResultError(controlResult.reason, "Control state unavailable"),
            "error",
        );
        setMessage(
            elements.adminActionStatus,
            describeResultError(controlResult.reason, "Admin state unavailable"),
            "error",
        );
    elements.refreshStatus.textContent = state.has_data ? "Live snapshot loaded" : "Waiting for runtime state";
    elements.lastUpdated.textContent = state.updated_at
        ? `Updated ${state.updated_at}`
        : "No snapshot saved yet";
}

function setActionStatus(message, state = "idle") {
    elements.actionStatus.textContent = message;
    elements.actionStatus.dataset.state = state;
}

function formatCategoryLabel(category) {
    if (!category) {
        return "Unknown";
    }

    return String(category).charAt(0).toUpperCase() + String(category).slice(1);
}

async function parseJsonResponse(response) {
    try {
        return await response.json();
    } catch {
        return null;
    }
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
    setMessage(elements.actionStatus, "Requesting category skip...", "pending");

    try {
        const result = await fetchJson(skipApiPath, { method: "POST" });
        setMessage(
            elements.actionStatus,
            `Skip accepted at ${displayText(result.requested_at)}.`,
            "success",
        );
    } catch (error) {
        setMessage(
            elements.actionStatus,
            describeResultError(error, "Skip request failed"),
            "error",
        );
    } finally {
        await refreshDashboard();
    setActionStatus("Requesting category skip...", "pending");

    try {
        const response = await fetch(skipApiPath, {
            method: "POST",
            cache: "no-store",
        });
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const result = await parseJsonResponse(response);
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

async function switchCategory() {
    if (!elements.switchCategoryButton || !elements.switchCategorySelect) {
        return;
    }

    const category = elements.switchCategorySelect.value;
    elements.switchCategoryButton.disabled = true;
    elements.switchCategorySelect.disabled = true;
    setMessage(
        elements.actionStatus,
        `Requesting switch to ${titleCase(category)}...`,
        "pending",
    );

    try {
        const result = await fetchJson(switchApiPath, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ category }),
        });
        setMessage(
            elements.actionStatus,
            `Switch accepted: ${titleCase(result.category)}.`,
            "success",
        );
    } catch (error) {
        setMessage(
            elements.actionStatus,
            describeResultError(error, "Switch request failed"),
            "error",
        );
    } finally {
        await refreshDashboard();
    }
}

async function signInAdmin(event) {
    event.preventDefault();
    const username = elements.adminUsername?.value?.trim() || "";
    const password = elements.adminPassword?.value || "";
    if (!username || !password) {
        setMessage(
            elements.adminLoginStatus,
            "Username and password are required.",
            "error",
        );
        return;
    }

    elements.adminLoginButton.disabled = true;
    setMessage(elements.adminLoginStatus, "Signing in...", "pending");

    try {
        const result = await fetchJson(adminLoginApi, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username, password }),
        });
        if (elements.adminPassword) {
            elements.adminPassword.value = "";
        }
        setMessage(
            elements.adminLoginStatus,
            `Signed in as ${displayText(result.username)}.`,
            "success",
        );
        await refreshDashboard();
        openControlsModal();
    } catch (error) {
        setMessage(
            elements.adminLoginStatus,
            describeResultError(error, "Sign-in failed"),
            "error",
        );
        if (elements.adminPassword) {
            elements.adminPassword.value = "";
        }
    } finally {
        elements.adminLoginButton.disabled = false;
    }
}

async function signOutAdmin() {
    elements.adminLogoutButton.disabled = true;
    setMessage(elements.adminActionStatus, "Signing out...", "pending");

    try {
        await fetchJson(adminLogoutApi, { method: "POST" });
        setMessage(elements.adminActionStatus, "Admin session ended.", "success");
        closeAllModals();
    } catch (error) {
        setMessage(
            elements.adminActionStatus,
            describeResultError(error, "Sign-out failed"),
            "error",
        );
    } finally {
        if (elements.adminLoginForm) {
            elements.adminLoginForm.reset();
        }
        await refreshDashboard();
    }
}

async function toggleControlLock(action) {
    const control = latestControlPayload?.controls?.[action];
    if (!control) {
        setMessage(
            elements.adminActionStatus,
            "Control state is not loaded yet.",
            "error",
        );
        return;
    }

    const nextLocked = !control.locked;
    setMessage(
        elements.adminActionStatus,
        `${nextLocked ? "Locking" : "Unlocking"} ${control.label}...`,
        "pending",
    );

    try {
        const result = await fetchJson(adminControlLockApi, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action, locked: nextLocked }),
        });
        setMessage(
            elements.adminActionStatus,
            `${result.control.label} ${result.control.locked ? "locked" : "unlocked"}.`,
            "success",
        );
    } catch (error) {
        setMessage(
            elements.adminActionStatus,
            describeResultError(error, "Lock update failed"),
            "error",
        );
    } finally {
        await refreshDashboard();
    }
}

function bindModalInteractions() {
    [elements.adminLoginModal, elements.adminControlsModal].forEach((modal) => {
        if (!modal) {
            return;
        }
        modal.addEventListener("click", (event) => {
            if (event.target === modal) {
                hideModal(modal);
            }
        });
    });

    elements.modalCloseButtons.forEach((button) => {
        button.addEventListener("click", () => {
            const modalId = button.dataset.closeModal;
            const modal = document.getElementById(modalId);
            hideModal(modal);
        });
    });

    document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") {
            return;
        }

        if (!elements.adminControlsModal.hidden) {
            hideModal(elements.adminControlsModal);
            return;
        }

        if (!elements.adminLoginModal.hidden) {
            hideModal(elements.adminLoginModal);
        }
    });
}

if (elements.pokemonImage) {
    elements.pokemonImage.addEventListener("error", () => {
        showPokemonFallback("Artwork unavailable");
    });
}

    setActionStatus(`Switching to ${formatCategoryLabel(category)}...`, "pending");

    try {
        const response = await fetch(switchApiPath, {
            method: "POST",
            cache: "no-store",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ category }),
        });
        const result = await parseJsonResponse(response);
        if (!response.ok) {
            throw new Error(result?.error || `HTTP ${response.status}`);
        }

        elements.refreshStatus.textContent = "Switch requested";
        setActionStatus(
            `Switch requested: ${formatCategoryLabel(result.category)}`,
            "success",
        );
        await refreshState();
    } catch (error) {
        setActionStatus(`Switch failed: ${error.message}`, "error");
    } finally {
        elements.switchCategoryButton.disabled = false;
    }
}

if (elements.skipCategoryButton) {
    elements.skipCategoryButton.addEventListener("click", skipCategory);
}

if (elements.switchCategoryButton) {
    elements.switchCategoryButton.addEventListener("click", switchCategory);
}

if (elements.adminControlButton) {
    elements.adminControlButton.addEventListener("click", openAdminControlFlow);
}

if (elements.adminLoginForm) {
    elements.adminLoginForm.addEventListener("submit", signInAdmin);
}

if (elements.adminLogoutButton) {
    elements.adminLogoutButton.addEventListener("click", signOutAdmin);
}

if (elements.toggleSkipLockButton) {
    elements.toggleSkipLockButton.addEventListener("click", () =>
        toggleControlLock("skip_category"),
    );
}

if (elements.toggleSwitchLockButton) {
    elements.toggleSwitchLockButton.addEventListener("click", () =>
        toggleControlLock("switch_category"),
    );
}

bindModalInteractions();
refreshDashboard();
window.setInterval(() => {
    refreshDashboard().catch(() => {});
}, pollIntervalMs);
refreshState();
window.setInterval(refreshState, pollIntervalMs);
