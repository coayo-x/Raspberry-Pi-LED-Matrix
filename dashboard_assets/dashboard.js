const currentDisplayApi =
    document.documentElement.dataset.currentDisplayApi || "/api/current-display-state";
const controlStateApi =
    document.documentElement.dataset.controlStateApi || "/api/control-state";
const skipApiPath =
    document.documentElement.dataset.skipApiPath || "/api/skip-category";
const switchApiPath =
    document.documentElement.dataset.switchApiPath || "/api/switch-category";
const customTextApi =
    document.documentElement.dataset.customTextApi || "/api/custom-text";
const stopCustomTextApi =
    document.documentElement.dataset.stopCustomTextApi ||
    "/api/admin/custom-text/stop";
const adminCustomTextForceApi =
    document.documentElement.dataset.adminCustomTextForceApi ||
    "/admin/custom-text/force";
const adminSnakeModeApi =
    document.documentElement.dataset.adminSnakeModeApi || "/api/admin/snake-mode";
const adminSnakeInputApi =
    document.documentElement.dataset.adminSnakeInputApi ||
    "/api/admin/snake-mode/input";
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
const lockCustomTextApi =
    document.documentElement.dataset.lockCustomTextApi || "/api/lock-custom-text";
const unlockCustomTextApi =
    document.documentElement.dataset.unlockCustomTextApi || "/api/unlock-custom-text";
const pollIntervalMs = Number(document.documentElement.dataset.pollIntervalMs || 2000);
const controlDefinitions = {
    skip_category: { action: "skip_category", label: "Skip Category" },
    switch_category: { action: "switch_category", label: "Switch Category" },
    custom_text: { action: "custom_text", label: "Custom Text" },
    snake_game: { action: "snake_game", label: "Snake Game Mode" },
};
const categoryFieldLabels = {
    joke: { primary: "Setup", secondary: "Punchline" },
    weather: { primary: "Location", secondary: "Details" },
    science: { primary: "Title", secondary: "Description" },
    pokemon: { primary: "Name", secondary: "Stats" },
    custom_text: { primary: "Text", secondary: "Style" },
    snake_game: { primary: "Mode", secondary: "State" },
};
const defaultCategoryFieldLabels = {
    primary: "Content",
    secondary: "Details",
};
const durationRange = {
    min: 0.1,
    max: 5,
};
const modalTransitionMs = 180;
const snakeMovementDirections = new Set(["up", "down", "left", "right"]);
const snakeMovementDedupWindowMs = 180;

const elements = {
    time: document.getElementById("time-value"),
    slot: document.getElementById("slot-value"),
    category: document.getElementById("category-value"),
    contentPrimaryLabel: document.getElementById("content-primary-label"),
    contentSecondaryLabel: document.getElementById("content-secondary-label"),
    setup: document.getElementById("setup-value"),
    punchline: document.getElementById("punchline-value"),
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
    customTextForm: document.getElementById("custom-text-form"),
    customTextInput: document.getElementById("custom-text-input"),
    customTextTextBrightness: document.getElementById(
        "custom-text-text-brightness",
    ),
    customTextTextBrightnessValue: document.getElementById(
        "custom-text-text-brightness-value",
    ),
    customTextBackgroundBrightness: document.getElementById(
        "custom-text-background-brightness",
    ),
    customTextBackgroundBrightnessValue: document.getElementById(
        "custom-text-background-brightness-value",
    ),
    customTextDuration: document.getElementById("custom-text-duration"),
    customTextFontFamily: document.getElementById("custom-text-font-family"),
    customTextFontSize: document.getElementById("custom-text-font-size"),
    customTextLockBanner: document.getElementById("custom-text-lock-banner"),
    customTextNote: document.getElementById("custom-text-note"),
    customTextSubmitButton: document.getElementById("custom-text-submit-button"),
    customTextStopButton: document.getElementById("custom-text-stop-button"),
    customTextStatus: document.getElementById("custom-text-status"),
    toolbarToggleButtons: Array.from(
        document.querySelectorAll("[data-toggle-style]"),
    ),
    alignmentButtons: Array.from(document.querySelectorAll("[data-alignment]")),
    colorButtons: Array.from(document.querySelectorAll("[data-color-name]")),
    aboutButton: document.getElementById("about-button"),
    aboutModal: document.getElementById("about-modal"),
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
    adminCustomTextLockState: document.getElementById(
        "admin-custom-text-lock-state",
    ),
    adminCustomTextForceState: document.getElementById(
        "admin-custom-text-force-state",
    ),
    adminSnakeModeState: document.getElementById("admin-snake-mode-state"),
    toggleSkipLockButton: document.getElementById("toggle-skip-lock-button"),
    toggleSwitchLockButton: document.getElementById("toggle-switch-lock-button"),
    toggleCustomTextLockButton: document.getElementById(
        "toggle-custom-text-lock-button",
    ),
    toggleCustomTextForceButton: document.getElementById(
        "toggle-custom-text-force-button",
    ),
    toggleSnakeModeButton: document.getElementById("toggle-snake-mode-button"),
    snakeControlPanel: document.getElementById("snake-control-panel"),
    snakeButtons: Array.from(document.querySelectorAll("[data-snake-direction]")),
    adminLogoutButton: document.getElementById("admin-logout-button"),
    adminActionStatus: document.getElementById("admin-action-status"),
};

let latestControlPayload = createGuestControlPayload(true);
const modalHideTimers = new WeakMap();
const customTextStyleState = {
    bold: false,
    italic: false,
    underline: false,
    alignment: "center",
    textBrightness: 100,
    backgroundBrightness: 100,
    textColor: "white",
    backgroundColor: "black",
};

const COLOR_HEX_MAP = {
    red: "#ff3b30",
    green: "#34c759",
    blue: "#0a84ff",
    yellow: "#ffd60a",
    magenta: "#ff2d55",
    cyan: "#64d2ff",
    white: "#f5f7fa",
    black: "#000000",
    orange: "#ff9f0a",
    purple: "#bf5af2",
};

// Image layers: each { id, element, posX, posY, drawW, drawH }
let imageLayers = [];
let nextLayerId = 0;
let selectedLayerId = null;

// Text layers: each { id, text, posX, posY, textColor }
let textLayers = [];
let nextTextLayerId = 0;
let selectedTextLayerId = null;

const dragState = {
    active: null,        // null | 'image' | 'textlayer' | 'resize'
    layerId: null,
    startMouseX: 0,
    startMouseY: 0,
    startPosX: 0,
    startPosY: 0,
    startDrawW: 0,
    startDrawH: 0,
    resizeCorner: null,  // 'nw'|'n'|'ne'|'e'|'se'|'s'|'sw'|'w'
};

// Handle sizes in canvas-space coords (canvas is 192×32 displayed 3× bigger)
const HANDLE_DRAW = 2;  // visual half-size in canvas px
const HANDLE_HIT  = 5;  // hit-test half-size in canvas px

const ledEditorElements = {
    canvas: document.getElementById("custom-text-preview-canvas"),
    addImageButton: document.getElementById("custom-text-add-image"),
    removeImageButton: document.getElementById("custom-text-remove-image"),
    imageFileInput: document.getElementById("custom-text-image-file"),
    imageControls: document.getElementById("led-image-controls"),
    imageScale: document.getElementById("image-scale"),
    imageScaleValue: document.getElementById("image-scale-value"),
    imagePosX: document.getElementById("image-pos-x"),
    imagePosXValue: document.getElementById("image-pos-x-value"),
    imagePosY: document.getElementById("image-pos-y"),
    imagePosYValue: document.getElementById("image-pos-y-value"),
    textPosX: document.getElementById("text-pos-x"),
    textPosXValue: document.getElementById("text-pos-x-value"),
    textPosY: document.getElementById("text-pos-y"),
    textPosYValue: document.getElementById("text-pos-y-value"),
    addTextButton: document.getElementById("custom-text-add-text"),
    removeTextButton: document.getElementById("custom-text-remove-text"),
    textBlockStatus: document.getElementById("text-block-status"),
};
const snakeInputRequestsInFlight = new Set();
const snakeMovementSentAt = new Map();
let lastSnakeInputRequestSequence = 0;
let lastAppliedSnakeInputRequestSequence = 0;

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
                    active_override: false,
                    override_expires_at: "",
                    override_remaining_seconds: 0,
                    override_text: "",
                    override: null,
                    force_enabled: false,
                    blocked_by_custom_text: false,
                    blocked_by_snake: false,
                    blocked_reason: "",
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
    return getModalElements().some(isModalOpen);
}

function syncBodyModalState() {
    document.body.classList.toggle("modal-open", hasOpenModal());
}

function getModalElements() {
    return [
        elements.aboutModal,
        elements.adminLoginModal,
        elements.adminControlsModal,
    ].filter(Boolean);
}

function isModalOpen(modal) {
    return Boolean(modal && !modal.hidden);
}

function clearModalHideTimer(modal) {
    const timer = modalHideTimers.get(modal);
    if (timer !== undefined) {
        window.clearTimeout(timer);
        modalHideTimers.delete(modal);
    }
}

function finalizeModalHide(modal) {
    clearModalHideTimer(modal);
    modal.hidden = true;
    modal.classList.remove("is-closing");
    modal.classList.remove("is-visible");
    syncBodyModalState();
}

function showModal(modal) {
    if (!modal) {
        return;
    }

    clearModalHideTimer(modal);
    modal.hidden = false;
    modal.classList.remove("is-closing");
    window.requestAnimationFrame(() => {
        modal.classList.add("is-visible");
    });
    syncBodyModalState();
}

function hideModal(modal, { immediate = false } = {}) {
    if (!modal) {
        return;
    }

    if (modal.hidden) {
        syncBodyModalState();
        return;
    }

    clearModalHideTimer(modal);
    modal.classList.remove("is-visible");
    if (immediate) {
        finalizeModalHide(modal);
        return;
    }

    modal.classList.add("is-closing");
    modalHideTimers.set(
        modal,
        window.setTimeout(() => {
            finalizeModalHide(modal);
        }, modalTransitionMs),
    );
    syncBodyModalState();
}

function closeAllModals() {
    hideModal(elements.aboutModal, { immediate: true });
    hideModal(elements.adminLoginModal, { immediate: true });
    hideModal(elements.adminControlsModal, { immediate: true });
}

function openAboutModal() {
    hideModal(elements.adminLoginModal, { immediate: true });
    hideModal(elements.adminControlsModal, { immediate: true });
    showModal(elements.aboutModal);
    elements.aboutModal?.querySelector("[data-close-modal]")?.focus();
}

function openLoginModal() {
    hideModal(elements.aboutModal, { immediate: true });
    hideModal(elements.adminControlsModal, { immediate: true });
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

    hideModal(elements.aboutModal, { immediate: true });
    hideModal(elements.adminLoginModal, { immediate: true });
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

function getCategoryChangeBlockedMessage(control) {
    return (
        control?.blocked_reason ||
        "Cannot change category while custom text is active"
    );
}

function getCustomTextLockMessage() {
    return "Custom text is currently locked by admin.";
}

function getCustomTextLockBannerMessage(control) {
    if (!control?.locked) {
        return "";
    }

    if (control.admin_override) {
        return "Custom text is locked for public use. Admin override is active.";
    }

    return getCustomTextLockMessage();
}

function buildControlNote(control) {
    if (!control) {
        return "Control state unavailable.";
    }

    if (control.blocked_by_custom_text) {
        return getCategoryChangeBlockedMessage(control);
    }

    if (control.blocked_by_snake) {
        return (
            control.blocked_reason ||
            "Cannot change display content while snake game mode is active"
        );
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
        previousSkip?.blocked_by_custom_text !== nextSkip?.blocked_by_custom_text ||
        previousSkip?.blocked_by_snake !== nextSkip?.blocked_by_snake ||
        previousSkip?.admin_override !== nextSkip?.admin_override ||
        previousSwitch?.locked !== nextSwitch?.locked ||
        previousSwitch?.blocked_by_custom_text !== nextSwitch?.blocked_by_custom_text ||
        previousSwitch?.blocked_by_snake !== nextSwitch?.blocked_by_snake ||
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
    const customTextBlocking = Boolean(
        nextSkip?.blocked_by_custom_text || nextSwitch?.blocked_by_custom_text,
    );
    const snakeBlocking = Boolean(
        nextSkip?.blocked_by_snake || nextSwitch?.blocked_by_snake,
    );
    const skipOverride = Boolean(nextSkip?.admin_override);
    const switchOverride = Boolean(nextSwitch?.admin_override);

    if (customTextBlocking) {
        setMessage(
            elements.actionStatus,
            getCategoryChangeBlockedMessage(nextSkip || nextSwitch),
            "error",
        );
        return;
    }

    if (snakeBlocking) {
        setMessage(
            elements.actionStatus,
            getCategoryChangeBlockedMessage(nextSkip || nextSwitch),
            "error",
        );
        return;
    }

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

function applyAdminForceState(control, button, labelElement) {
    if (!button || !labelElement) {
        return;
    }

    const forceEnabled = Boolean(control?.force_enabled);
    const hasOverride = Boolean(control?.override);
    labelElement.textContent = forceEnabled
        ? hasOverride
            ? "Enabled. Custom text stays on screen until disabled."
            : "Enabled. Waiting for custom text content."
        : "Disabled. Custom text follows its normal timer.";
    button.textContent = forceEnabled ? "Disable Force" : "Enable Force";
    button.disabled = false;
}

function applyAdminSnakeState(control, button, labelElement) {
    if (!button || !labelElement) {
        return;
    }

    const enabled = Boolean(control?.enabled);
    const status = String(control?.status || (enabled ? "waiting" : "idle"));
    const score = Number(control?.score || 0);
    const level = Math.max(1, Number(control?.level || 1));
    labelElement.textContent = enabled
        ? status === "playing"
            ? `Active. Level ${level}. Score ${score}.`
            : status === "paused"
                ? `Paused. Level ${level}. Score ${score}.`
            : status === "level_intro"
                ? `Level ${level} starting. Score ${score}.`
            : status === "game_over"
                ? `Game over on level ${level}. Score ${score}.`
                : "Active. Waiting for the first control input."
        : "Disabled. Normal rotation controls the matrix.";
    button.textContent = enabled ? "Stop Snake" : "Enable Snake";
    button.disabled = false;

    if (elements.snakeControlPanel) {
        elements.snakeControlPanel.hidden =
            !enabled || !latestControlPayload?.auth?.authenticated;
    }
    elements.snakeButtons.forEach((snakeButton) => {
        snakeButton.disabled =
            !enabled || !latestControlPayload?.auth?.authenticated;
    });
}

function getSnakeDirectionForKey(key) {
    const normalized = String(key || "").toLowerCase();
    return {
        arrowup: "up",
        w: "up",
        arrowdown: "down",
        s: "down",
        arrowleft: "left",
        a: "left",
        arrowright: "right",
        d: "right",
        " ": "pause",
        spacebar: "pause",
        "1": "cheat_level_1",
        "2": "cheat_level_2",
        "3": "cheat_level_3",
        "4": "cheat_level_4",
        "5": "cheat_level_5",
        "6": "cheat_level_6",
        "7": "cheat_level_7",
        "8": "cheat_level_8",
        "9": "cheat_level_9",
        "0": "cheat_level_10",
    }[normalized];
}

function isTextEntryTarget(target) {
    const tagName = target?.tagName?.toLowerCase();
    return (
        target?.isContentEditable ||
        tagName === "input" ||
        tagName === "textarea" ||
        tagName === "select"
    );
}

function canSendSnakeInputFromKeyboard(event) {
    return Boolean(
        latestControlPayload?.auth?.authenticated &&
            latestControlPayload?.controls?.snake_game?.enabled &&
            !isTextEntryTarget(event.target),
    );
}

function isMovementSnakeDirection(direction) {
    return snakeMovementDirections.has(direction);
}

function wasMovementDirectionSentRecently(direction) {
    if (!isMovementSnakeDirection(direction)) {
        return false;
    }

    const sentAt = snakeMovementSentAt.get(direction);
    return (
        typeof sentAt === "number" &&
        Date.now() - sentAt < snakeMovementDedupWindowMs
    );
}

function applySnakeInputResult(result, requestSequence) {
    if (
        !result ||
        !latestControlPayload?.controls?.snake_game ||
        requestSequence < lastAppliedSnakeInputRequestSequence
    ) {
        return;
    }

    lastAppliedSnakeInputRequestSequence = requestSequence;
    applyControlPayload({
        ...latestControlPayload,
        controls: {
            ...latestControlPayload.controls,
            snake_game: {
                ...latestControlPayload.controls.snake_game,
                ...result,
            },
        },
    });
}

function syncCustomTextStyleButtons() {
    elements.toolbarToggleButtons.forEach((button) => {
        const styleKey = button.dataset.toggleStyle;
        const active = Boolean(customTextStyleState[styleKey]);
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-pressed", String(active));
    });

    elements.alignmentButtons.forEach((button) => {
        const active = button.dataset.alignment === customTextStyleState.alignment;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-pressed", String(active));
    });

    const activeTextColor = getSelectedTextLayer()?.textColor ?? customTextStyleState.textColor;
    elements.colorButtons.forEach((button) => {
        const target = button.dataset.colorTarget;
        const colorName = button.dataset.colorName;
        const active =
            (target === "text" && colorName === activeTextColor) ||
            (target === "background" && colorName === customTextStyleState.backgroundColor);
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-pressed", String(active));
    });
}

function applyBrightnessToHex(hex, factor) {
    const clamped = Math.max(0.1, Math.min(1.25, factor));
    const r = Math.min(255, Math.round(parseInt(hex.slice(1, 3), 16) * clamped));
    const g = Math.min(255, Math.round(parseInt(hex.slice(3, 5), 16) * clamped));
    const b = Math.min(255, Math.round(parseInt(hex.slice(5, 7), 16) * clamped));
    return `rgb(${r},${g},${b})`;
}

function getCanvasFontFamily(family) {
    return { sans: "sans-serif", serif: "serif", mono: "monospace" }[family] || "sans-serif";
}

function renderCustomTextPreview(forExport = false) {
    const canvas = ledEditorElements.canvas;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    const W = 192;
    const H = 32;

    // 1. Background — fills entire 192×32 canvas
    const bgHex = COLOR_HEX_MAP[customTextStyleState.backgroundColor] || "#000000";
    const bgFactor = customTextStyleState.backgroundBrightness / 100;
    ctx.fillStyle = applyBrightnessToHex(bgHex, bgFactor);
    ctx.fillRect(0, 0, W, H);

    // 2. Image layers in order
    for (const layer of imageLayers) {
        const b = getLayerDrawBounds(layer);
        ctx.drawImage(layer.element, b.x, b.y, b.w, b.h);
    }

    // 3. Text layers (drawn above images, in order)
    for (const tLayer of textLayers) {
        const text = tLayer.text;
        if (!text) continue;
        const fontSize = Math.max(6, Math.min(24, parseInt(elements.customTextFontSize?.value || "16", 10)));
        const fontWeight = customTextStyleState.bold ? "bold" : "normal";
        const fontStyle = customTextStyleState.italic ? "italic" : "normal";
        const fontFamily = getCanvasFontFamily(elements.customTextFontFamily?.value);
        ctx.font = `${fontStyle} ${fontWeight} ${fontSize}px ${fontFamily}`;
        ctx.textBaseline = "alphabetic";
        const textHex = COLOR_HEX_MAP[tLayer.textColor] || COLOR_HEX_MAP[customTextStyleState.textColor] || "#f5f7fa";
        const textFactor = customTextStyleState.textBrightness / 100;
        ctx.fillStyle = applyBrightnessToHex(textHex, textFactor);
        const alignment = customTextStyleState.alignment;
        let baseX;
        if (alignment === "center") {
            ctx.textAlign = "center";
            baseX = W / 2;
        } else if (alignment === "right") {
            ctx.textAlign = "right";
            baseX = W - 2;
        } else {
            ctx.textAlign = "left";
            baseX = 4;
        }
        const textX = baseX + tLayer.posX;
        const centerY = Math.max(0, (H - fontSize) / 2);
        const textY = Math.max(0, centerY + tLayer.posY);
        ctx.fillText(text, textX, textY + fontSize);
        if (customTextStyleState.underline) {
            const measured = ctx.measureText(text);
            const lineY = textY + fontSize + 2;
            const lineX =
                alignment === "center"
                    ? textX - measured.width / 2
                    : alignment === "right"
                        ? textX - measured.width
                        : textX;
            ctx.strokeStyle = ctx.fillStyle;
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(lineX, lineY);
            ctx.lineTo(lineX + measured.width, lineY);
            ctx.stroke();
        }
    }

    // 4. Editor-only: selection outlines (excluded from export)
    if (!forExport) {
        // Image layer: selection outline + resize handles
        const selected = getSelectedLayer();
        if (selected) {
            const b = getLayerDrawBounds(selected);
            ctx.save();
            ctx.strokeStyle = "rgba(100,210,255,0.9)";
            ctx.lineWidth = 0.5;
            ctx.setLineDash([2, 2]);
            ctx.strokeRect(b.x - 0.5, b.y - 0.5, b.w + 1, b.h + 1);
            ctx.setLineDash([]);
            ctx.fillStyle = "rgba(100,210,255,1)";
            for (const [cx, cy] of [
                [b.x,           b.y],
                [b.x + b.w / 2, b.y],
                [b.x + b.w,     b.y],
                [b.x + b.w,     b.y + b.h / 2],
                [b.x + b.w,     b.y + b.h],
                [b.x + b.w / 2, b.y + b.h],
                [b.x,           b.y + b.h],
                [b.x,           b.y + b.h / 2],
            ]) {
                ctx.fillRect(cx - HANDLE_DRAW, cy - HANDLE_DRAW, HANDLE_DRAW * 2, HANDLE_DRAW * 2);
            }
            ctx.restore();
        }
        // Text layer: selection outline
        if (selectedTextLayerId !== null) {
            const selTLayer = textLayers.find(l => l.id === selectedTextLayerId);
            if (selTLayer) {
                const tb = getTextLayerBounds(selTLayer);
                if (tb) {
                    ctx.save();
                    ctx.strokeStyle = "rgba(255,220,80,0.9)";
                    ctx.lineWidth = 0.5;
                    ctx.setLineDash([2, 2]);
                    ctx.strokeRect(tb.x - 0.5, tb.y - 0.5, tb.w + 1, tb.h + 1);
                    ctx.setLineDash([]);
                    ctx.restore();
                }
            }
        }
    }
}

function exportCanvasAsPng() {
    const canvas = ledEditorElements.canvas;
    if (!canvas) return null;
    renderCustomTextPreview(true);   // draw without handles
    const dataUrl = canvas.toDataURL("image/png");
    renderCustomTextPreview(false);  // restore handles
    return dataUrl;
}

function handleImageFileSelect(event) {
    const file = event.target.files?.[0];
    if (!file) {
        return;
    }

    if (file.type === "image/svg+xml" || !file.type.startsWith("image/")) {
        setMessage(elements.customTextStatus, "Only raster image files are supported (PNG, JPEG, etc.).", "error");
        if (ledEditorElements.imageFileInput) {
            ledEditorElements.imageFileInput.value = "";
        }
        return;
    }

    const reader = new FileReader();
    reader.onload = (e) => {
        const img = new Image();
        img.onload = () => {
            // Compute centered position for this image at fit-scale 100%
            const W = 192;
            const H = 32;
            const iw = img.naturalWidth;
            const ih = img.naturalHeight;
            const fitScale = Math.min(W / iw, H / ih);
            const drawW = Math.round(iw * fitScale);
            const drawH = Math.round(ih * fitScale);
            const posX = Math.round((W - drawW) / 2);
            const posY = Math.round((H - drawH) / 2);

            const layer = { id: nextLayerId++, element: img, posX, posY, drawW, drawH };
            imageLayers.push(layer);
            selectedLayerId = layer.id;

            if (ledEditorElements.imageControls) ledEditorElements.imageControls.hidden = false;
            if (ledEditorElements.removeImageButton) ledEditorElements.removeImageButton.hidden = false;
            syncSlidersToSelected();
            renderCustomTextPreview();
        };
        img.onerror = () => {
            setMessage(elements.customTextStatus, "Failed to load the selected image.", "error");
            if (ledEditorElements.imageFileInput) {
                ledEditorElements.imageFileInput.value = "";
            }
        };
        img.src = e.target.result;
    };
    reader.onerror = () => {
        setMessage(elements.customTextStatus, "Failed to read the image file.", "error");
        if (ledEditorElements.imageFileInput) {
            ledEditorElements.imageFileInput.value = "";
        }
    };
    reader.readAsDataURL(file);
}

function removeUploadedImage() {
    if (imageLayers.length === 0) return;

    // Remove selected layer, or last layer if none selected
    const removeId = selectedLayerId !== null
        ? selectedLayerId
        : imageLayers[imageLayers.length - 1].id;
    imageLayers = imageLayers.filter(l => l.id !== removeId);

    // Select the last remaining layer, or deselect
    selectedLayerId = imageLayers.length > 0
        ? imageLayers[imageLayers.length - 1].id
        : null;

    if (imageLayers.length === 0) {
        if (ledEditorElements.imageControls) ledEditorElements.imageControls.hidden = true;
        if (ledEditorElements.removeImageButton) ledEditorElements.removeImageButton.hidden = true;
        if (ledEditorElements.imageFileInput) ledEditorElements.imageFileInput.value = "";
    }

    syncSlidersToSelected();
    renderCustomTextPreview();
}

function syncLedEditorValues() {
    const layer = getSelectedLayer();
    if (ledEditorElements.imageScaleValue) {
        ledEditorElements.imageScaleValue.textContent = layer
            ? `${getLayerEffectiveScalePct(layer)}%`
            : "--";
    }
    if (ledEditorElements.imagePosXValue) {
        ledEditorElements.imagePosXValue.textContent = layer ? String(layer.posX) : "--";
    }
    if (ledEditorElements.imagePosYValue) {
        ledEditorElements.imagePosYValue.textContent = layer ? String(layer.posY) : "--";
    }
    const textLayer = getSelectedTextLayer();
    if (ledEditorElements.textPosXValue) {
        ledEditorElements.textPosXValue.textContent = textLayer ? String(textLayer.posX) : "0";
    }
    if (ledEditorElements.textPosYValue) {
        ledEditorElements.textPosYValue.textContent = textLayer ? String(textLayer.posY) : "0";
    }
}

function getLayerById(id) {
    return imageLayers.find(l => l.id === id) ?? null;
}

function getSelectedLayer() {
    return selectedLayerId !== null ? getLayerById(selectedLayerId) : null;
}

function getLayerDrawBounds(layer) {
    return { x: layer.posX, y: layer.posY, w: layer.drawW, h: layer.drawH };
}

function getLayerFitScale(layer) {
    const iw = layer.element.naturalWidth;
    const ih = layer.element.naturalHeight;
    return Math.min(192 / iw, 32 / ih);
}

function getLayerEffectiveScalePct(layer) {
    const fitScale = getLayerFitScale(layer);
    return Math.round((layer.drawW / (layer.element.naturalWidth * fitScale)) * 100);
}

function getHandleAtPoint(pt, bounds) {
    const { x, y, w, h } = bounds;
    for (const [name, cx, cy] of [
        ["nw", x,          y],
        ["n",  x + w / 2,  y],
        ["ne", x + w,      y],
        ["e",  x + w,      y + h / 2],
        ["se", x + w,      y + h],
        ["s",  x + w / 2,  y + h],
        ["sw", x,          y + h],
        ["w",  x,          y + h / 2],
    ]) {
        if (Math.abs(pt.x - cx) <= HANDLE_HIT && Math.abs(pt.y - cy) <= HANDLE_HIT) {
            return name;
        }
    }
    return null;
}

function syncSlidersToSelected() {
    const layer = getSelectedLayer();
    if (layer) {
        if (ledEditorElements.imageScale) {
            ledEditorElements.imageScale.value = String(Math.max(5, Math.min(1000, getLayerEffectiveScalePct(layer))));
        }
        if (ledEditorElements.imagePosX) ledEditorElements.imagePosX.value = String(Math.max(-192, Math.min(192, layer.posX)));
        if (ledEditorElements.imagePosY) ledEditorElements.imagePosY.value = String(Math.max(-32, Math.min(32, layer.posY)));
    }
    syncLedEditorValues();
}

function getCanvasPoint(event) {
    const canvas = ledEditorElements.canvas;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    return {
        x: (event.clientX - rect.left) * scaleX,
        y: (event.clientY - rect.top) * scaleY,
    };
}

function getTextLayerBounds(layer) {
    const text = layer.text;
    if (!text) return null;
    const canvas = ledEditorElements.canvas;
    if (!canvas) return null;
    const W = 192;
    const H = 32;
    const fontSize = Math.max(6, Math.min(24, parseInt(elements.customTextFontSize?.value || "16", 10)));
    const fontWeight = customTextStyleState.bold ? "bold" : "normal";
    const fontStyle = customTextStyleState.italic ? "italic" : "normal";
    const fontFamily = getCanvasFontFamily(elements.customTextFontFamily?.value);
    const ctx = canvas.getContext("2d");
    ctx.save();
    ctx.font = `${fontStyle} ${fontWeight} ${fontSize}px ${fontFamily}`;
    const alignment = customTextStyleState.alignment;
    let baseX;
    if (alignment === "center") baseX = W / 2;
    else if (alignment === "right") baseX = W - 2;
    else baseX = 4;
    const textX = baseX + layer.posX;
    const centerY = (H - fontSize) / 2;
    const textY = Math.max(0, centerY + layer.posY);
    const tw = ctx.measureText(text).width;
    ctx.restore();
    let left;
    if (alignment === "center") left = textX - tw / 2;
    else if (alignment === "right") left = textX - tw;
    else left = textX;
    return { x: left - 2, y: textY - 2, w: tw + 4, h: fontSize + 6 };
}

function getSelectedTextLayer() {
    return selectedTextLayerId !== null
        ? (textLayers.find(l => l.id === selectedTextLayerId) ?? null)
        : null;
}

function syncTextLayerUI() {
    const layer = getSelectedTextLayer();
    const isPrimary = layer?.id === 0;
    const hasNonPrimary = textLayers.some(l => l.id !== 0);

    if (ledEditorElements.removeTextButton) {
        ledEditorElements.removeTextButton.hidden = !hasNonPrimary || !layer || isPrimary;
    }

    // Sync textarea to selected layer text
    if (layer && elements.customTextInput) {
        elements.customTextInput.value = layer.text;
    }

    // Update status label
    if (ledEditorElements.textBlockStatus) {
        ledEditorElements.textBlockStatus.textContent = layer && !isPrimary
            ? `Editing: Text Block ${textLayers.indexOf(layer) + 1}`
            : "Editing: Main message";
    }

    // Sync text color UI to selected layer
    syncCustomTextStyleButtons();

    if (layer) {
        if (ledEditorElements.textPosX) {
            ledEditorElements.textPosX.value = String(Math.max(-96, Math.min(96, layer.posX)));
        }
        if (ledEditorElements.textPosY) {
            ledEditorElements.textPosY.value = String(Math.max(-16, Math.min(16, layer.posY)));
        }
    }
    syncLedEditorValues();
}

function addTextLayer() {
    const currentColor = getSelectedTextLayer()?.textColor ?? customTextStyleState.textColor;
    const layer = { id: nextTextLayerId++, text: "New text", posX: 0, posY: 0, textColor: currentColor };
    textLayers.push(layer);
    selectedLayerId = null;
    selectedTextLayerId = layer.id;
    syncTextLayerUI();
    renderCustomTextPreview();
}

function removeTextLayer() {
    const layer = getSelectedTextLayer();
    if (!layer || layer.id === 0) return;
    textLayers = textLayers.filter(l => l.id !== layer.id);
    selectedTextLayerId = 0;
    syncTextLayerUI();
    renderCustomTextPreview();
}

function hitTest(pt, bounds) {
    if (!bounds) return false;
    return pt.x >= bounds.x && pt.x <= bounds.x + bounds.w
        && pt.y >= bounds.y && pt.y <= bounds.y + bounds.h;
}

function resizeCursorForHandle(handle) {
    if (handle === "nw" || handle === "se") return "nwse-resize";
    if (handle === "ne" || handle === "sw") return "nesw-resize";
    if (handle === "n"  || handle === "s")  return "ns-resize";
    if (handle === "e"  || handle === "w")  return "ew-resize";
    return "nwse-resize";
}

function onCanvasMouseDown(event) {
    if (event.button !== 0) return;
    const pt = getCanvasPoint(event);

    // 1. Check resize handles on currently selected layer (highest priority)
    const selected = getSelectedLayer();
    if (selected) {
        const bounds = getLayerDrawBounds(selected);
        const handle = getHandleAtPoint(pt, bounds);
        if (handle) {
            dragState.active = "resize";
            dragState.layerId = selected.id;
            dragState.startMouseX = pt.x;
            dragState.startMouseY = pt.y;
            dragState.startPosX = selected.posX;
            dragState.startPosY = selected.posY;
            dragState.startDrawW = bounds.w;
            dragState.startDrawH = bounds.h;
            dragState.resizeCorner = handle;
            event.preventDefault();
            return;
        }
    }

    // 2. Text layers — topmost (last in array) gets priority
    for (let i = textLayers.length - 1; i >= 0; i--) {
        const tLayer = textLayers[i];
        if (hitTest(pt, getTextLayerBounds(tLayer))) {
            selectedLayerId = null;
            selectedTextLayerId = tLayer.id;
            dragState.active = "textlayer";
            dragState.layerId = tLayer.id;
            dragState.startMouseX = pt.x;
            dragState.startMouseY = pt.y;
            dragState.startPosX = tLayer.posX;
            dragState.startPosY = tLayer.posY;
            syncTextLayerUI();
            renderCustomTextPreview();
            event.preventDefault();
            return;
        }
    }

    // 3. Image layers — topmost (last in array) gets priority
    for (let i = imageLayers.length - 1; i >= 0; i--) {
        const layer = imageLayers[i];
        if (hitTest(pt, getLayerDrawBounds(layer))) {
            selectedLayerId = layer.id;
            selectedTextLayerId = null;
            dragState.active = "image";
            dragState.layerId = layer.id;
            dragState.startMouseX = pt.x;
            dragState.startMouseY = pt.y;
            dragState.startPosX = layer.posX;
            dragState.startPosY = layer.posY;
            syncSlidersToSelected();
            syncTextLayerUI();
            renderCustomTextPreview();
            event.preventDefault();
            return;
        }
    }

    // 4. Click on empty canvas → deselect all
    selectedLayerId = null;
    selectedTextLayerId = null;
    syncSlidersToSelected();
    syncTextLayerUI();
    renderCustomTextPreview();
}

function onCanvasHover(event) {
    const canvas = ledEditorElements.canvas;
    if (!canvas) return;
    if (dragState.active === "resize") {
        canvas.style.cursor = resizeCursorForHandle(dragState.resizeCorner);
        return;
    }
    if (dragState.active) {
        canvas.style.cursor = "grabbing";
        return;
    }
    const pt = getCanvasPoint(event);

    // Check resize handles on selected layer
    const selected = getSelectedLayer();
    if (selected) {
        const handle = getHandleAtPoint(pt, getLayerDrawBounds(selected));
        if (handle) {
            canvas.style.cursor = resizeCursorForHandle(handle);
            return;
        }
    }

    // Check text layers
    for (let i = textLayers.length - 1; i >= 0; i--) {
        if (hitTest(pt, getTextLayerBounds(textLayers[i]))) {
            canvas.style.cursor = "grab";
            return;
        }
    }

    // Check any image layer
    for (let i = imageLayers.length - 1; i >= 0; i--) {
        if (hitTest(pt, getLayerDrawBounds(imageLayers[i]))) {
            canvas.style.cursor = "grab";
            return;
        }
    }

    canvas.style.cursor = "crosshair";
}

function onWindowMouseMove(event) {
    if (!dragState.active) return;
    const canvas = ledEditorElements.canvas;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const currentX = (event.clientX - rect.left) * scaleX;
    const currentY = (event.clientY - rect.top) * scaleY;
    const deltaX = Math.round(currentX - dragState.startMouseX);
    const deltaY = Math.round(currentY - dragState.startMouseY);

    if (dragState.active === "image") {
        const layer = getLayerById(dragState.layerId);
        if (layer) {
            layer.posX = dragState.startPosX + deltaX;
            layer.posY = dragState.startPosY + deltaY;
            syncSlidersToSelected();
        }
    } else if (dragState.active === "resize") {
        const layer = getLayerById(dragState.layerId);
        if (layer) {
            const handle = dragState.resizeCorner;
            const startW = dragState.startDrawW;
            const startH = dragState.startDrawH;
            let newW = startW;
            let newH = startH;
            let newPosX = dragState.startPosX;
            let newPosY = dragState.startPosY;

            if (handle === "e") {
                newW = Math.max(4, startW + deltaX);
            } else if (handle === "w") {
                newW = Math.max(4, startW - deltaX);
                newPosX = dragState.startPosX + (startW - newW);
            } else if (handle === "s") {
                newH = Math.max(4, startH + deltaY);
            } else if (handle === "n") {
                newH = Math.max(4, startH - deltaY);
                newPosY = dragState.startPosY + (startH - newH);
            } else {
                // Corner: proportional resize driven by horizontal delta
                const dw = (handle === "se" || handle === "ne") ? deltaX : -deltaX;
                newW = Math.max(4, startW + dw);
                const ratio = newW / startW;
                newH = Math.max(4, Math.round(startH * ratio));
                if (handle === "nw" || handle === "sw") {
                    newPosX = dragState.startPosX + (startW - newW);
                }
                if (handle === "nw" || handle === "ne") {
                    newPosY = dragState.startPosY + (startH - newH);
                }
            }

            layer.drawW = newW;
            layer.drawH = newH;
            layer.posX = newPosX;
            layer.posY = newPosY;
            syncSlidersToSelected();
        }
    } else if (dragState.active === "textlayer") {
        const tLayer = textLayers.find(l => l.id === dragState.layerId) ?? null;
        if (tLayer) {
            tLayer.posX = dragState.startPosX + deltaX;
            tLayer.posY = dragState.startPosY + deltaY;
            if (ledEditorElements.textPosX) {
                ledEditorElements.textPosX.value = String(Math.max(-96, Math.min(96, tLayer.posX)));
            }
            if (ledEditorElements.textPosY) {
                ledEditorElements.textPosY.value = String(Math.max(-16, Math.min(16, tLayer.posY)));
            }
            syncLedEditorValues();
        }
    }
    renderCustomTextPreview();
}

function onWindowMouseUp() {
    if (dragState.active) {
        dragState.active = null;
        dragState.layerId = null;
        dragState.resizeCorner = null;
        if (ledEditorElements.canvas) {
            ledEditorElements.canvas.style.cursor = "crosshair";
        }
    }
}

function setCustomTextInputsEnabled(enabled) {
    const controls = [
        elements.customTextInput,
        elements.customTextTextBrightness,
        elements.customTextBackgroundBrightness,
        elements.customTextDuration,
        elements.customTextFontFamily,
        elements.customTextFontSize,
        elements.customTextSubmitButton,
        ...elements.toolbarToggleButtons,
        ...elements.alignmentButtons,
        ...elements.colorButtons,
        ledEditorElements.addImageButton,
        ledEditorElements.removeImageButton,
        ledEditorElements.imageScale,
        ledEditorElements.imagePosX,
        ledEditorElements.imagePosY,
        ledEditorElements.textPosX,
        ledEditorElements.textPosY,
        ledEditorElements.addTextButton,
        ledEditorElements.removeTextButton,
    ];

    controls.forEach((control) => {
        if (control) {
            control.disabled = !enabled;
        }
    });
}

function formatBrightnessValue(value) {
    const numeric = Number(value);
    return Number.isFinite(numeric)
        ? Math.min(100, Math.max(10, Math.round(numeric)))
        : 100;
}

function syncCustomTextBrightnessValues() {
    const textBrightness = formatBrightnessValue(
        customTextStyleState.textBrightness,
    );
    const backgroundBrightness = formatBrightnessValue(
        customTextStyleState.backgroundBrightness,
    );
    customTextStyleState.textBrightness = textBrightness;
    customTextStyleState.backgroundBrightness = backgroundBrightness;

    if (elements.customTextTextBrightness) {
        elements.customTextTextBrightness.value = String(textBrightness);
    }
    if (elements.customTextTextBrightnessValue) {
        elements.customTextTextBrightnessValue.textContent = `${textBrightness}%`;
    }
    if (elements.customTextBackgroundBrightness) {
        elements.customTextBackgroundBrightness.value = String(
            backgroundBrightness,
        );
    }
    if (elements.customTextBackgroundBrightnessValue) {
        elements.customTextBackgroundBrightnessValue.textContent =
            `${backgroundBrightness}%`;
    }
}

function buildCustomTextNote(control) {
    if (!control) {
        return "Custom Text state unavailable.";
    }

    const noteParts = [];
    if (control.locked && !control.admin_override) {
        return getCustomTextLockMessage();
    }

    if (control.locked && control.admin_override) {
        noteParts.push(`${getCustomTextLockMessage()} Admin override active.`);
    }

    if (control.cooldown_remaining_seconds > 0) {
        noteParts.push(
            `Cooldown active: ${control.cooldown_remaining_seconds}s remaining.`,
        );
    }

    if (control.force_enabled) {
        noteParts.push(
            control.override
                ? "Force mode enabled. Custom text stays on screen until disabled."
                : "Force mode enabled, but no custom text is saved. Normal rotation continues.",
        );
    } else if (control.active_override) {
        if (control.override_expires_at) {
            noteParts.push(`Override active until ${control.override_expires_at}.`);
        } else {
            noteParts.push("Override is active on the matrix.");
        }
    }

    if (noteParts.length > 0) {
        return noteParts.join(" ");
    }

    return "Ready to send a temporary matrix override.";
}

function applyCustomTextControlState(control) {
    const nextControl =
        control || createGuestControlPayload().controls.custom_text;
    const isPublicLocked = Boolean(nextControl.locked && !nextControl.admin_override);
    const isAdmin = Boolean(latestControlPayload?.auth?.authenticated);
    const hasDisplayableOverride = Boolean(nextControl.override);

    if (elements.customTextLockBanner) {
        elements.customTextLockBanner.hidden = !nextControl.locked;
        elements.customTextLockBanner.textContent =
            getCustomTextLockBannerMessage(nextControl);
    }
    if (elements.customTextNote) {
        elements.customTextNote.textContent = buildCustomTextNote(nextControl);
    }
    if (elements.customTextSubmitButton) {
        elements.customTextSubmitButton.textContent = "Display Text";
    }
    if (elements.customTextStopButton) {
        elements.customTextStopButton.hidden = !isAdmin;
        elements.customTextStopButton.disabled =
            !isAdmin || !hasDisplayableOverride;
        elements.customTextStopButton.textContent = "Stop Custom Text";
    }
    setCustomTextInputsEnabled(Boolean(nextControl.available));

    if (isPublicLocked) {
        setMessage(elements.customTextStatus, getCustomTextLockMessage(), "error");
        return;
    }

    if (
        elements.customTextStatus &&
        elements.customTextStatus.textContent === getCustomTextLockMessage()
    ) {
        if (nextControl.force_enabled && hasDisplayableOverride) {
            setMessage(
                elements.customTextStatus,
                "Force mode enabled. Custom text stays on screen until disabled.",
                "success",
            );
        } else if (nextControl.force_enabled) {
            setMessage(
                elements.customTextStatus,
                "Force mode enabled, but no custom text is saved yet.",
                "idle",
            );
        } else if (nextControl.active_override && nextControl.override_expires_at) {
            setMessage(
                elements.customTextStatus,
                `Temporary override active until ${nextControl.override_expires_at}.`,
                "success",
            );
        } else {
            setMessage(
                elements.customTextStatus,
                "Ready to send a temporary matrix override.",
                "idle",
            );
        }
    }
}

function formatDurationValue(value) {
    const numeric = Number(value);
    const clamped = Number.isFinite(numeric)
        ? Math.min(durationRange.max, Math.max(durationRange.min, numeric))
        : durationRange.max;
    return clamped % 1 === 0 ? String(clamped) : clamped.toFixed(1);
}

function toggleCustomTextStyle(styleKey) {
    if (!(styleKey in customTextStyleState)) {
        return;
    }

    customTextStyleState[styleKey] = !customTextStyleState[styleKey];
    syncCustomTextStyleButtons();
}

function setCustomTextAlignment(alignment) {
    customTextStyleState.alignment = alignment;
    syncCustomTextStyleButtons();
}

function setCustomTextColor(target, colorName) {
    if (target === "text") {
        const layer = getSelectedTextLayer();
        if (layer) {
            layer.textColor = colorName;
        } else {
            customTextStyleState.textColor = colorName;
        }
    } else if (target === "background") {
        customTextStyleState.backgroundColor = colorName;
    }
    syncCustomTextStyleButtons();
}

async function submitCustomText(event) {
    event.preventDefault();
    if (!elements.customTextInput || !elements.customTextDuration) {
        return;
    }

    const control = latestControlPayload?.controls?.custom_text;
    if (control?.locked && !control?.admin_override) {
        setMessage(elements.customTextStatus, getCustomTextLockMessage(), "error");
        applyCustomTextControlState(control);
        return;
    }

    const text = (textLayers[0]?.text ?? elements.customTextInput.value).trim();
    if (!text) {
        setMessage(elements.customTextStatus, "Message text is required.", "error");
        elements.customTextInput.focus();
        return;
    }

    const durationMinutes = Number(elements.customTextDuration.value);
    if (
        !Number.isFinite(durationMinutes) ||
        durationMinutes < durationRange.min ||
        durationMinutes > durationRange.max
    ) {
        setMessage(
            elements.customTextStatus,
            `Duration must be between ${durationRange.min} and ${durationRange.max} minutes.`,
            "error",
        );
        elements.customTextDuration.focus();
        return;
    }

    setCustomTextInputsEnabled(false);
    setMessage(
        elements.customTextStatus,
        "Sending temporary override to the matrix...",
        "pending",
    );

    try {
        const requestBody = {
            text,
            duration_minutes: durationMinutes,
            style: {
                bold: customTextStyleState.bold,
                italic: customTextStyleState.italic,
                underline: customTextStyleState.underline,
                font_family: elements.customTextFontFamily?.value || "sans",
                font_size: Number(elements.customTextFontSize?.value || 16),
                text_brightness: formatBrightnessValue(
                    customTextStyleState.textBrightness,
                ),
                background_brightness: formatBrightnessValue(
                    customTextStyleState.backgroundBrightness,
                ),
                text_color: customTextStyleState.textColor,
                background_color: customTextStyleState.backgroundColor,
                alignment: customTextStyleState.alignment,
            },
        };

        if (imageLayers.length > 0 || textLayers.length > 1) {
            const pngDataUrl = exportCanvasAsPng();
            if (pngDataUrl) {
                requestBody.rendered_frame = pngDataUrl;
            }
        }

        const result = await fetchJson(customTextApi, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(requestBody),
        });
        const expiresAt =
            result.override?.expires_at ||
            result.override_expires_at ||
            result.requested_at;
        setMessage(
            elements.customTextStatus,
            result.force_enabled
                ? "Force mode enabled. Custom text stays on screen until disabled."
                : expiresAt
                    ? `Temporary override active until ${expiresAt}.`
                    : "Temporary override is active on the matrix.",
            "success",
        );
    } catch (error) {
        setMessage(
            elements.customTextStatus,
            describeResultError(error, "Custom text request failed"),
            "error",
        );
    } finally {
        await refreshDashboard().catch(() => null);
        applyCustomTextControlState(latestControlPayload?.controls?.custom_text);
    }
}

async function stopCustomText() {
    const control = latestControlPayload?.controls?.custom_text;
    if (!latestControlPayload?.auth?.authenticated) {
        setMessage(
            elements.customTextStatus,
            "Dashboard authentication is required.",
            "error",
        );
        openLoginModal();
        return;
    }

    if (!control?.override) {
        setMessage(elements.customTextStatus, "No custom text to stop.", "error");
        applyCustomTextControlState(control);
        return;
    }

    if (elements.customTextStopButton) {
        elements.customTextStopButton.disabled = true;
    }
    setMessage(elements.customTextStatus, "Stopping custom text...", "pending");

    try {
        const result = await fetchJson(stopCustomTextApi, {
            method: "POST",
        });
        setMessage(
            elements.customTextStatus,
            result.message || "Custom text stopped.",
            result.stopped ? "success" : "error",
        );
    } catch (error) {
        if (
            handleUnauthorizedAdminAction(
                error,
                elements.customTextStatus,
                "Stop request failed",
            )
        ) {
            return;
        }
        setMessage(
            elements.customTextStatus,
            describeResultError(error, "Stop request failed"),
            "error",
        );
    } finally {
        await refreshDashboard().catch(() => null);
        applyCustomTextControlState(latestControlPayload?.controls?.custom_text);
    }
}

async function toggleCustomTextForce() {
    const control = latestControlPayload?.controls?.custom_text;
    if (!control) {
        setMessage(
            elements.adminActionStatus,
            "Custom text state is not loaded yet.",
            "error",
        );
        return;
    }

    const nextEnabled = !control.force_enabled;
    if (elements.toggleCustomTextForceButton) {
        elements.toggleCustomTextForceButton.disabled = true;
    }
    setMessage(
        elements.adminActionStatus,
        `${nextEnabled ? "Enabling" : "Disabling"} Force Custom Text...`,
        "pending",
    );

    try {
        const result = await fetchJson(adminCustomTextForceApi, {
            method: "POST",
        });
        setMessage(
            elements.adminActionStatus,
            `Force Custom Text ${result.enabled ? "enabled" : "disabled"}.`,
            "success",
        );
    } catch (error) {
        if (
            handleUnauthorizedAdminAction(
                error,
                elements.adminActionStatus,
                "Force mode update failed",
            )
        ) {
            return;
        }
        setMessage(
            elements.adminActionStatus,
            describeResultError(error, "Force mode update failed"),
            "error",
        );
    } finally {
        await refreshDashboard().catch(() => null);
    }
}

async function toggleSnakeMode() {
    const control = latestControlPayload?.controls?.snake_game;
    if (!latestControlPayload?.auth?.authenticated) {
        setMessage(
            elements.adminActionStatus,
            "Dashboard authentication is required.",
            "error",
        );
        openLoginModal();
        return;
    }

    const nextEnabled = !control?.enabled;
    if (elements.toggleSnakeModeButton) {
        elements.toggleSnakeModeButton.disabled = true;
    }
    setMessage(
        elements.adminActionStatus,
        `${nextEnabled ? "Enabling" : "Stopping"} Snake Game Mode...`,
        "pending",
    );

    try {
        const result = await fetchJson(adminSnakeModeApi, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ enabled: nextEnabled }),
        });
        setMessage(
            elements.adminActionStatus,
            result.enabled
                ? "Snake Game Mode enabled. Press any control to start."
                : "Snake Game Mode stopped. Normal rotation will resume.",
            "success",
        );
    } catch (error) {
        if (
            handleUnauthorizedAdminAction(
                error,
                elements.adminActionStatus,
                "Snake mode update failed",
            )
        ) {
            return;
        }
        setMessage(
            elements.adminActionStatus,
            describeResultError(error, "Snake mode update failed"),
            "error",
        );
    } finally {
        await refreshDashboard().catch(() => null);
    }
}

async function sendSnakeInput(direction) {
    if (!direction) {
        return;
    }

    if (!latestControlPayload?.auth?.authenticated) {
        setMessage(
            elements.adminActionStatus,
            "Dashboard authentication is required.",
            "error",
        );
        openLoginModal();
        return;
    }

    if (!latestControlPayload?.controls?.snake_game?.enabled) {
        setMessage(
            elements.adminActionStatus,
            "Enable Snake Game Mode before sending controls.",
            "error",
        );
        return;
    }

    if (snakeInputRequestsInFlight.has(direction)) {
        return;
    }

    if (wasMovementDirectionSentRecently(direction)) {
        return;
    }

    const requestSequence = ++lastSnakeInputRequestSequence;
    snakeInputRequestsInFlight.add(direction);
    if (isMovementSnakeDirection(direction)) {
        snakeMovementSentAt.set(direction, Date.now());
    }

    try {
        const result = await fetchJson(adminSnakeInputApi, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ direction }),
        });
        applySnakeInputResult(result, requestSequence);
    } catch (error) {
        if (
            handleUnauthorizedAdminAction(
                error,
                elements.adminActionStatus,
                "Snake control failed",
            )
        ) {
            return;
        }
        setMessage(
            elements.adminActionStatus,
            describeResultError(error, "Snake control failed"),
            "error",
        );
        refreshControlState().catch(() => null);
    } finally {
        snakeInputRequestsInFlight.delete(direction);
    }
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
    const customTextControl = controls.custom_text;
    const snakeControl = controls.snake_game;
    const customTextBlocking = Boolean(
        skipControl?.blocked_by_custom_text || switchControl?.blocked_by_custom_text,
    );
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
    );
    applyPublicControlState(
        switchControl,
        elements.switchCategoryButton,
        elements.switchCategoryNote,
    );
    applyCustomTextControlState(customTextControl);

    if (elements.switchCategorySelect) {
        elements.switchCategorySelect.disabled = !switchControl?.available;
    }

    if (elements.publicControlMode) {
        const publicModeLabel =
            snakeControl?.enabled
                ? "Snake Mode"
                : customTextControl?.force_enabled && customTextControl?.override
                ? "Force Mode"
                : customTextBlocking
                    ? "Custom Text Active"
                    : publicLockedCount === 2
                        ? "Locked"
                        : publicLockedCount === 1
                            ? "Partial Lock"
                            : adminOverride
                                ? "Admin Override"
                                : "Active";
        elements.publicControlMode.textContent = publicModeLabel;
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
        elements.toggleCustomTextLockButton.disabled = true;
        elements.toggleCustomTextForceButton.disabled = true;
        elements.toggleSnakeModeButton.disabled = true;
        elements.snakeButtons.forEach((button) => {
            button.disabled = true;
        });
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
        const lockedControls = [skipControl, switchControl, customTextControl]
            .filter((control) => Boolean(control?.locked))
            .map((control) => control.label);
        const lockSummary =
            lockedControls.length > 0
                ? `${lockedControls.join(" and ")} locked for public use.`
                : "Skip, switch, and custom text controls are available to the public.";
        const forceSummary = customTextControl?.force_enabled
            ? customTextControl?.override
                ? " Force mode is enabled for custom text."
                : " Force mode is enabled and waiting for custom text content."
            : "";
        const snakeSummary = snakeControl?.enabled
            ? " Snake Game Mode is active."
            : "";
        elements.adminControlsSummary.textContent = auth.expires_at
            ? `Admin session active until ${auth.expires_at}. ${lockSummary}${forceSummary}${snakeSummary}`
            : `Admin session active. ${lockSummary}${forceSummary}${snakeSummary}`;
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
    applyAdminLockState(
        customTextControl,
        elements.toggleCustomTextLockButton,
        elements.adminCustomTextLockState,
    );
    applyAdminForceState(
        customTextControl,
        elements.toggleCustomTextForceButton,
        elements.adminCustomTextForceState,
    );
    applyAdminSnakeState(
        snakeControl,
        elements.toggleSnakeModeButton,
        elements.adminSnakeModeState,
    );
    elements.toggleSkipLockButton.disabled = !isAdmin;
    elements.toggleSwitchLockButton.disabled = !isAdmin;
    elements.toggleCustomTextLockButton.disabled = !isAdmin;
    elements.toggleCustomTextForceButton.disabled = !isAdmin;
    elements.toggleSnakeModeButton.disabled = !isAdmin;
    elements.snakeButtons.forEach((button) => {
        button.disabled = !isAdmin || !snakeControl?.enabled;
    });
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
    } catch {
        return;
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

    const apiByAction = {
        skip_category: { lock: lockSkipApi, unlock: unlockSkipApi },
        switch_category: { lock: lockSwitchApi, unlock: unlockSwitchApi },
        custom_text: { lock: lockCustomTextApi, unlock: unlockCustomTextApi },
    };
    const endpoints = apiByAction[action];
    if (!endpoints) {
        setMessage(
            elements.adminActionStatus,
            "Unsupported control lock action.",
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
        const result = await fetchJson(nextLocked ? endpoints.lock : endpoints.unlock, {
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
    getModalElements().forEach((modal) => {
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
            const snakeDirection = getSnakeDirectionForKey(event.key);
            if (snakeDirection && canSendSnakeInputFromKeyboard(event)) {
                event.preventDefault();
                if (event.repeat) {
                    return;
                }
                sendSnakeInput(snakeDirection);
            }
            return;
        }

        if (isModalOpen(elements.aboutModal)) {
            hideModal(elements.aboutModal);
            return;
        }

        if (isModalOpen(elements.adminControlsModal)) {
            hideModal(elements.adminControlsModal);
            return;
        }

        if (isModalOpen(elements.adminLoginModal)) {
            hideModal(elements.adminLoginModal);
        }
    });
}

if (elements.pokemonImage) {
    elements.pokemonImage.addEventListener("error", () => {
        showPokemonFallback("Artwork unavailable");
    });
}

if (elements.customTextDuration) {
    elements.customTextDuration.addEventListener("blur", () => {
        elements.customTextDuration.value = formatDurationValue(
            elements.customTextDuration.value || durationRange.max,
        );
    });
}

if (elements.customTextTextBrightness) {
    elements.customTextTextBrightness.addEventListener("input", () => {
        customTextStyleState.textBrightness =
            elements.customTextTextBrightness.value;
        syncCustomTextBrightnessValues();
        renderCustomTextPreview();
    });
}

if (elements.customTextBackgroundBrightness) {
    elements.customTextBackgroundBrightness.addEventListener("input", () => {
        customTextStyleState.backgroundBrightness =
            elements.customTextBackgroundBrightness.value;
        syncCustomTextBrightnessValues();
        renderCustomTextPreview();
    });
}

elements.toolbarToggleButtons.forEach((button) => {
    button.addEventListener("click", () => {
        toggleCustomTextStyle(button.dataset.toggleStyle);
        renderCustomTextPreview();
    });
});

elements.alignmentButtons.forEach((button) => {
    button.addEventListener("click", () => {
        setCustomTextAlignment(button.dataset.alignment);
        renderCustomTextPreview();
    });
});

elements.colorButtons.forEach((button) => {
    button.addEventListener("click", () => {
        setCustomTextColor(
            button.dataset.colorTarget,
            button.dataset.colorName,
        );
        renderCustomTextPreview();
    });
});

if (elements.customTextForm) {
    elements.customTextForm.addEventListener("submit", submitCustomText);
}

if (elements.customTextStopButton) {
    elements.customTextStopButton.addEventListener("click", stopCustomText);
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

if (elements.aboutButton) {
    elements.aboutButton.addEventListener("click", openAboutModal);
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

if (elements.toggleCustomTextLockButton) {
    elements.toggleCustomTextLockButton.addEventListener("click", () =>
        toggleControlLock("custom_text"),
    );
}

if (elements.toggleCustomTextForceButton) {
    elements.toggleCustomTextForceButton.addEventListener(
        "click",
        toggleCustomTextForce,
    );
}

if (elements.toggleSnakeModeButton) {
    elements.toggleSnakeModeButton.addEventListener("click", toggleSnakeMode);
}

elements.snakeButtons.forEach((button) => {
    button.addEventListener("click", () => {
        sendSnakeInput(button.dataset.snakeDirection);
    });
});

if (ledEditorElements.canvas) {
    ledEditorElements.canvas.addEventListener("mousedown", onCanvasMouseDown);
    ledEditorElements.canvas.addEventListener("mousemove", onCanvasHover);
}
window.addEventListener("mousemove", onWindowMouseMove);
window.addEventListener("mouseup", onWindowMouseUp);

if (ledEditorElements.addImageButton) {
    ledEditorElements.addImageButton.addEventListener("click", () => {
        if (ledEditorElements.imageFileInput) {
            ledEditorElements.imageFileInput.click();
        }
    });
}

if (ledEditorElements.removeImageButton) {
    ledEditorElements.removeImageButton.addEventListener("click", removeUploadedImage);
}

if (ledEditorElements.imageFileInput) {
    ledEditorElements.imageFileInput.addEventListener("change", handleImageFileSelect);
}

if (ledEditorElements.imageScale) {
    ledEditorElements.imageScale.addEventListener("input", () => {
        const layer = getSelectedLayer();
        if (layer) {
            const fitScale = getLayerFitScale(layer);
            const userScale = Number(ledEditorElements.imageScale.value) / 100;
            layer.drawW = Math.max(1, Math.round(layer.element.naturalWidth * fitScale * userScale));
            layer.drawH = Math.max(1, Math.round(layer.element.naturalHeight * fitScale * userScale));
            syncLedEditorValues();
            renderCustomTextPreview();
        }
    });
}

if (ledEditorElements.imagePosX) {
    ledEditorElements.imagePosX.addEventListener("input", () => {
        const layer = getSelectedLayer();
        if (layer) {
            layer.posX = Number(ledEditorElements.imagePosX.value);
            syncLedEditorValues();
            renderCustomTextPreview();
        }
    });
}

if (ledEditorElements.imagePosY) {
    ledEditorElements.imagePosY.addEventListener("input", () => {
        const layer = getSelectedLayer();
        if (layer) {
            layer.posY = Number(ledEditorElements.imagePosY.value);
            syncLedEditorValues();
            renderCustomTextPreview();
        }
    });
}

if (ledEditorElements.textPosX) {
    ledEditorElements.textPosX.addEventListener("input", () => {
        const layer = getSelectedTextLayer();
        if (layer) {
            layer.posX = Number(ledEditorElements.textPosX.value);
            syncLedEditorValues();
            renderCustomTextPreview();
        }
    });
}

if (ledEditorElements.textPosY) {
    ledEditorElements.textPosY.addEventListener("input", () => {
        const layer = getSelectedTextLayer();
        if (layer) {
            layer.posY = Number(ledEditorElements.textPosY.value);
            syncLedEditorValues();
            renderCustomTextPreview();
        }
    });
}

if (elements.customTextInput) {
    elements.customTextInput.addEventListener("input", () => {
        const layer = getSelectedTextLayer();
        if (layer) {
            layer.text = elements.customTextInput.value;
        }
        renderCustomTextPreview();
    });
}

if (elements.customTextFontFamily) {
    elements.customTextFontFamily.addEventListener("change", renderCustomTextPreview);
}

if (elements.customTextFontSize) {
    elements.customTextFontSize.addEventListener("change", renderCustomTextPreview);
}

if (ledEditorElements.addTextButton) {
    ledEditorElements.addTextButton.addEventListener("click", addTextLayer);
}

if (ledEditorElements.removeTextButton) {
    ledEditorElements.removeTextButton.addEventListener("click", removeTextLayer);
}

// Initialize primary text layer
textLayers = [{ id: nextTextLayerId++, text: "", posX: 0, posY: 0, textColor: customTextStyleState.textColor }];
selectedTextLayerId = 0;

syncCustomTextBrightnessValues();
syncCustomTextStyleButtons();
syncLedEditorValues();
syncTextLayerUI();
renderCustomTextPreview();
bindModalInteractions();
applyControlPayload(latestControlPayload);
refreshDashboard().catch(() => {});
window.setInterval(() => {
    refreshDashboard().catch(() => {});
}, pollIntervalMs);
