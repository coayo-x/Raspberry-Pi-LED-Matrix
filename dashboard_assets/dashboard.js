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
const lockSkipApi =
    document.documentElement.dataset.lockSkipApi || "/api/lock-skip";
const unlockSkipApi =
    document.documentElement.dataset.unlockSkipApi || "/api/unlock-skip";
const lockSwitchApi =
    document.documentElement.dataset.lockSwitchApi || "/api/lock-switch";
const unlockSwitchApi =
    document.documentElement.dataset.unlockSwitchApi || "/api/unlock-switch";
const pollIntervalMs = Number(document.documentElement.dataset.pollIntervalMs || 2000);
const controlDefinitions = {
    skip_category: { action: "skip_category", label: "Skip Category" },
    switch_category: { action: "switch_category", label: "Switch Category" },
};
const categoryFieldLabels = {
    joke: { primary: "Setup", secondary: "Punchline" },
    weather: { primary: "Location", secondary: "Details" },
    science: { primary: "Title", secondary: "Description" },
    pokemon: { primary: "Name", secondary: "Stats" },
};
const defaultCategoryFieldLabels = {
    primary: "Content",
    secondary: "Details",
};

const elements = {
    time: document.getElementById("time-value"),
    slot: document.getElementById("slot-value"),
    category: document.getElementById("category-value"),
    contentPrimaryLabel: document.getElementById("content-primary-label"),
    contentSecondaryLabel: document.getElementById("content-secondary-label"),
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

let latestControlPayload = createGuestControlPayload(true);

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

function createGuestControlPayload(configured = true) {
    return {
        auth: {
            configured,
            authenticated: false,
            username: "",
            expires_at: "",
        },
        controls: Object.fromEntries(
            Object.values(controlDefinitions).map((control) => [
                control.action,
                {
                    action: control.action,
                    label: control.label,
                    locked: false,
                    action_locked: false,
                    admin_override: false,
                    cooldown_seconds: 0,
                    cooldown_remaining_seconds: 0,
                    request_count: 0,
                    handled_count: 0,
                    pending_request_count: 0,
                    last_requested_at: "",
                    last_accepted_at: "",
                    available: true,
                    status: "ready",
                    requested_category: null,
                },
            ]),
        ),
    };
}

function getCategoryFieldLabels(category) {
    return (
        categoryFieldLabels[String(category || "").toLowerCase()] ||
        defaultCategoryFieldLabels
    );
}

function applyCategoryFieldLabels(category) {
    const labels = getCategoryFieldLabels(category);
    if (elements.contentPrimaryLabel) {
        elements.contentPrimaryLabel.textContent = labels.primary;
    }
    if (elements.contentSecondaryLabel) {
        elements.contentSecondaryLabel.textContent = labels.secondary;
    }
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

    refreshControlState()
        .catch(() => null)
        .finally(() => {
            if (latestControlPayload?.auth?.authenticated) {
                openControlsModal();
                return;
            }
            openLoginModal();
        });
}

function setGuestControlState(configured = true) {
    applyControlPayload(createGuestControlPayload(configured));
}

function applyUnauthorizedControlState(error) {
    setGuestControlState(error?.result?.configured !== false);
}

function handleUnauthorizedAdminAction(error, statusElement, fallbackMessage) {
    if (error?.status !== 401) {
        return false;
    }

    applyUnauthorizedControlState(error);
    setMessage(statusElement, describeResultError(error, fallbackMessage), "error");
    openLoginModal();
    return true;
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
    applyCategoryFieldLabels(state.category);
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

function getControlLockMessage(control) {
    if (!control) {
        return "Control state unavailable.";
    }

    return control.action === "skip_category"
        ? "Skip locked by admin."
        : "Switch locked by admin.";
}

function buildControlNote(control, auth) {
    if (!control) {
        return "Control state unavailable.";
    }

    if (control.locked && !control.admin_override) {
        return getControlLockMessage(control);
    }

    if (control.admin_override) {
        return `${getControlLockMessage(control)} Admin override active.`;
    }

    if (control.cooldown_remaining_seconds > 0) {
        return `Cooldown active: ${control.cooldown_remaining_seconds}s remaining.`;
    }

    if (control.pending_request_count > 0) {
        return "Accepted. Waiting for runtime handoff.";
    }

    return "Controls are active.";
}

function syncPublicActionStatus(auth, controls, previousPayload) {
    if (!elements.actionStatus) {
        return;
    }

    const previousAuth = previousPayload?.auth;
    const previousSkip = previousPayload?.controls?.skip_category;
    const previousSwitch = previousPayload?.controls?.switch_category;
    const nextSkip = controls?.skip_category;
    const nextSwitch = controls?.switch_category;
    const lockStateChanged =
        previousSkip?.locked !== nextSkip?.locked ||
        previousSkip?.admin_override !== nextSkip?.admin_override ||
        previousSwitch?.locked !== nextSwitch?.locked ||
        previousSwitch?.admin_override !== nextSwitch?.admin_override;
    const authStateChanged =
        previousAuth?.configured !== auth?.configured ||
        previousAuth?.authenticated !== auth?.authenticated;
    if (
        !lockStateChanged &&
        !authStateChanged &&
        elements.actionStatus.dataset.state &&
        elements.actionStatus.dataset.state !== "idle"
    ) {
        return;
    }

    const skipLocked = Boolean(nextSkip?.locked && !nextSkip?.admin_override);
    const switchLocked = Boolean(nextSwitch?.locked && !nextSwitch?.admin_override);
    const skipOverride = Boolean(nextSkip?.admin_override);
    const switchOverride = Boolean(nextSwitch?.admin_override);

    if (skipLocked && switchLocked) {
        setMessage(
            elements.actionStatus,
            "Skip and switch locked by admin.",
            "error",
        );
        return;
    }

    if (skipLocked) {
        setMessage(elements.actionStatus, "Skip locked by admin.", "error");
        return;
    }

    if (switchLocked) {
        setMessage(elements.actionStatus, "Switch locked by admin.", "error");
        return;
    }

    if (skipOverride && switchOverride) {
        setMessage(
            elements.actionStatus,
            "Admin override active for skip and switch locks.",
            "idle",
        );
        return;
    }

    if (skipOverride) {
        setMessage(
            elements.actionStatus,
            "Skip locked by admin. Admin override active.",
            "idle",
        );
        return;
    }

    if (switchOverride) {
        setMessage(
            elements.actionStatus,
            "Switch locked by admin. Admin override active.",
            "idle",
        );
        return;
    }

    const hasAvailableAction =
        Boolean(controls?.skip_category?.available) ||
        Boolean(controls?.switch_category?.available);
    setMessage(
        elements.actionStatus,
        hasAvailableAction
            ? "Controls are active."
            : "Waiting for controls to become available.",
        "idle",
    );
}

function applyPublicControlState(control, button, noteElement, auth) {
    if (!control || !button || !noteElement) {
        return;
    }

    noteElement.textContent = buildControlNote(control, auth);
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
    const nextPayload =
        payload || createGuestControlPayload(latestControlPayload?.auth?.configured);
    const previousPayload = latestControlPayload;
    latestControlPayload = nextPayload;
    const auth = nextPayload.auth || createGuestControlPayload(true).auth;
    const controls =
        nextPayload.controls || createGuestControlPayload(auth.configured).controls;
    const isAdmin = Boolean(auth.authenticated);
    const skipControl = controls.skip_category;
    const switchControl = controls.switch_category;
    const publicLockedCount = [skipControl, switchControl].filter(
        (control) => Boolean(control?.locked && !control?.admin_override),
    ).length;
    const adminOverride = [skipControl, switchControl].some((control) =>
        Boolean(control?.admin_override),
    );

    applyPublicControlState(
        skipControl,
        elements.skipCategoryButton,
        elements.skipCategoryNote,
        auth,
    );
    applyPublicControlState(
        switchControl,
        elements.switchCategoryButton,
        elements.switchCategoryNote,
        auth,
    );

    if (elements.switchCategorySelect) {
        elements.switchCategorySelect.disabled = !switchControl?.available;
    }

    if (elements.publicControlMode) {
        elements.publicControlMode.textContent = publicLockedCount === 2
            ? "Locked"
            : publicLockedCount === 1
                ? "Partial Lock"
            : adminOverride
                ? "Admin Override"
                : "Active";
    }

    syncPublicActionStatus(auth, controls, previousPayload);

    if (!auth.configured) {
        elements.adminDisabledMessage.hidden = false;
        elements.adminLoginForm.hidden = true;
        elements.adminPanel.hidden = true;
        elements.adminLoginCopy.textContent =
            "Local admin credentials are not configured on this dashboard host.";
        elements.adminControlsSummary.textContent =
            "Configure local admin credentials to manage dashboard control locks.";
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
        "Sign in with the configured admin account to manage dashboard control locks.";

    if (isAdmin) {
        elements.adminPanel.hidden = false;
        elements.adminSessionBadge.textContent = `${displayText(auth.username)} active`;
        const lockedControls = [skipControl, switchControl]
            .filter((control) => Boolean(control?.locked))
            .map((control) => control.label);
        const lockSummary =
            lockedControls.length > 0
                ? `${lockedControls.join(" and ")} locked for public use.`
                : "Skip and switch controls are available to the public.";
        elements.adminControlsSummary.textContent = auth.expires_at
            ? `Admin session active until ${auth.expires_at}. ${lockSummary}`
            : `Admin session active. ${lockSummary}`;
        setMessage(
            elements.adminLoginStatus,
            `Signed in as ${displayText(auth.username)}.`,
            "success",
        );
    } else {
        elements.adminPanel.hidden = true;
        elements.adminSessionBadge.textContent = "Signed out";
        elements.adminControlsSummary.textContent =
            "Sign in to lock or unlock dashboard controls.";
        if (
            !elements.adminLoginStatus.dataset.state ||
            elements.adminLoginStatus.dataset.state === "success"
        ) {
            setMessage(elements.adminLoginStatus, "Admin session inactive.", "idle");
        }
        hideModal(elements.adminControlsModal);
    }

    applyAdminLockState(
        skipControl,
        elements.toggleSkipLockButton,
        elements.adminSkipLockState,
    );
    applyAdminLockState(
        switchControl,
        elements.toggleSwitchLockButton,
        elements.adminSwitchLockState,
    );
    elements.toggleSkipLockButton.disabled = !isAdmin;
    elements.toggleSwitchLockButton.disabled = !isAdmin;
    elements.adminLogoutButton.disabled = !isAdmin;
}

async function refreshDashboard() {
    await Promise.all([
        refreshSnapshotState(),
        refreshControlState().catch(() => null),
    ]);
}

async function refreshSnapshotState() {
    try {
        const state = await fetchJson(currentDisplayApi);
        applySnapshotState(state);
    } catch (error) {
        elements.refreshStatus.textContent = "Snapshot refresh failed";
        elements.lastUpdated.textContent = error.message;
    }
}

async function refreshControlState() {
    try {
        const payload = await fetchJson(controlStateApi);
        applyControlPayload(payload);
        return payload;
    } catch (error) {
        if (error?.status === 401) {
            applyUnauthorizedControlState(error);
            return latestControlPayload;
        }

        setMessage(
            elements.actionStatus,
            describeResultError(error, "Control state unavailable"),
            "error",
        );
        setMessage(
            elements.adminActionStatus,
            describeResultError(error, "Admin state unavailable"),
            "error",
        );
        throw error;
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
        if (
            handleUnauthorizedAdminAction(
                error,
                elements.actionStatus,
                "Skip request failed",
            )
        ) {
            return;
        }
        setMessage(
            elements.actionStatus,
            describeResultError(error, "Skip request failed"),
            "error",
        );
    } finally {
        await refreshDashboard();
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
        if (
            handleUnauthorizedAdminAction(
                error,
                elements.actionStatus,
                "Switch request failed",
            )
        ) {
            return;
        }
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
        await refreshControlState();
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
        if (error?.status === 401) {
            applyUnauthorizedControlState(error);
            closeAllModals();
        }
        setMessage(
            elements.adminActionStatus,
            describeResultError(error, "Sign-out failed"),
            "error",
        );
    } finally {
        if (elements.adminLoginForm) {
            elements.adminLoginForm.reset();
        }
        await refreshControlState().catch(() => null);
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
    const isSkipAction = action === "skip_category";
    const lockApi = isSkipAction ? lockSkipApi : lockSwitchApi;
    const unlockApi = isSkipAction ? unlockSkipApi : unlockSwitchApi;
    setMessage(
        elements.adminActionStatus,
        `${nextLocked ? "Locking" : "Unlocking"} ${control.label}...`,
        "pending",
    );

    try {
        const result = await fetchJson(nextLocked ? lockApi : unlockApi, {
            method: "POST",
        });
        setMessage(
            elements.adminActionStatus,
            `${result.control.label} ${result.control.locked ? "locked" : "unlocked"}.`,
            "success",
        );
    } catch (error) {
        if (
            handleUnauthorizedAdminAction(
                error,
                elements.adminActionStatus,
                "Lock update failed",
            )
        ) {
            return;
        }
        setMessage(
            elements.adminActionStatus,
            describeResultError(error, "Lock update failed"),
            "error",
        );
    } finally {
        await refreshControlState().catch(() => null);
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
applyControlPayload(latestControlPayload);
refreshDashboard().catch(() => {});
window.setInterval(() => {
    refreshDashboard().catch(() => {});
}, pollIntervalMs);
