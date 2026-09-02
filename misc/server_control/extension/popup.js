/**
 * Chrome extension popup for the AREQA server-control Worker.
 *
 * The extension calls only the Cloudflare Worker API. Render API credentials
 * remain Worker secrets; this popup stores only CONTROL_TOKEN in Chrome
 * extension storage.
 */

const STORAGE_KEYS = {
  controlToken: 'controlToken',
  lastStatusPayload: 'lastStatusPayload',
  lastStatusUpdatedAt: 'lastStatusUpdatedAt',
};

const DEFAULT_WORKER_URL = 'https://areqa-server-control.areqa-server-control.workers.dev';
const POLL_MS = 1000;
const RESUME_TIMEOUT_MS = 180000;
const SUSPEND_DURATION_MS = 10000;

let state = {
  workerUrl: '',
  controlToken: '',
  appUrl: '',
  busy: false,
  pollTimer: null,
};

const els = {
  clearButton: document.getElementById('clearButton'),
  settingsPanel: document.getElementById('settingsPanel'),
  tokenInput: document.getElementById('tokenInput'),
  saveButton: document.getElementById('saveButton'),
  statusGrid: document.getElementById('statusGrid'),
  resumeButton: document.getElementById('resumeButton'),
  suspendButton: document.getElementById('suspendButton'),
  refreshButton: document.getElementById('refreshButton'),
  openButton: document.getElementById('openButton'),
  message: document.getElementById('message'),
  updatedAt: document.getElementById('updatedAt'),
};

/**
 * Initializes popup state from Chrome storage.
 *
 * Side Effects:
 *   Reads extension-local settings and updates the DOM. No network call is made
 *   until the user clicks Refresh, Resume All, or Suspend All.
 */
async function init() {
  const stored = await chrome.storage.local.get([
    STORAGE_KEYS.controlToken,
    STORAGE_KEYS.lastStatusPayload,
    STORAGE_KEYS.lastStatusUpdatedAt,
  ]);
  state.workerUrl = DEFAULT_WORKER_URL;
  state.controlToken = typeof stored[STORAGE_KEYS.controlToken] === 'string'
    ? stored[STORAGE_KEYS.controlToken]
    : '';

  els.tokenInput.value = state.controlToken;
  renderAuthState();
  if (state.controlToken) {
    renderCachedStatus(stored[STORAGE_KEYS.lastStatusPayload], stored[STORAGE_KEYS.lastStatusUpdatedAt]);
  }
}

/**
 * Persists popup configuration.
 *
 * Side Effects:
 *   Stores the control token in extension-local storage.
 */
async function saveSettings() {
  const controlToken = els.tokenInput.value.trim();

  if (!controlToken) {
    setMessage('Control token is required.', 'error');
    return;
  }

  await chrome.storage.local.set({
    [STORAGE_KEYS.controlToken]: controlToken,
  });
  state.workerUrl = DEFAULT_WORKER_URL;
  state.controlToken = controlToken;
  renderAuthState();
  setMessage('Unlocked. Use Refresh, Resume All, or Suspend All.', 'ok');
}

/**
 * Clears saved popup configuration.
 *
 * Side Effects:
 *   Removes extension-local settings and stops action polling.
 */
async function clearSettings() {
  stopActionPolling();
  await chrome.storage.local.remove([
    STORAGE_KEYS.controlToken,
    STORAGE_KEYS.lastStatusPayload,
    STORAGE_KEYS.lastStatusUpdatedAt,
  ]);
  state.workerUrl = DEFAULT_WORKER_URL;
  state.controlToken = '';
  state.appUrl = '';
  els.tokenInput.value = '';
  els.statusGrid.innerHTML = '';
  renderAuthState();
  setMessage('Settings cleared.');
}

/**
 * Applies locked/unlocked UI state.
 */
function renderAuthState() {
  const configured = Boolean(state.workerUrl && state.controlToken);
  els.settingsPanel.hidden = configured;
  els.clearButton.hidden = !configured;
  setBusy(false);

  if (!configured) {
    setMessage('Enter your control token first.');
  } else {
    setMessage('Ready. Use Refresh, Resume All, or Suspend All.');
  }
}

/**
 * Renders the most recent cached status without calling the Worker API.
 *
 * Args:
 *   payload: Previously saved Worker status payload.
 *   updatedAt: Local timestamp captured when the payload was saved.
 */
function renderCachedStatus(payload, updatedAt) {
  if (!payload || !Array.isArray(payload.services)) return;
  state.appUrl = payload.appUrl || '';
  els.statusGrid.innerHTML = payload.services.map(serviceCard).join('');
  els.updatedAt.textContent = updatedAt
    ? 'Last updated: ' + new Date(updatedAt).toLocaleTimeString()
    : 'Last status restored';
  setBusy(false);
}

/**
 * Stores the latest status payload for the next popup open.
 *
 * Args:
 *   payload: Worker response containing service summaries.
 */
async function cacheStatus(payload) {
  if (!payload || !Array.isArray(payload.services)) return;
  await chrome.storage.local.set({
    [STORAGE_KEYS.lastStatusPayload]: payload,
    [STORAGE_KEYS.lastStatusUpdatedAt]: new Date().toISOString(),
  });
}

/**
 * Enables or disables interactive controls.
 *
 * Args:
 *   busy: Whether a network request is currently running.
 */
function setBusy(busy) {
  state.busy = busy;
  const disabled = busy || !state.workerUrl || !state.controlToken;
  els.resumeButton.disabled = disabled;
  els.suspendButton.disabled = disabled;
  els.refreshButton.disabled = disabled;
  els.openButton.disabled = disabled || !state.appUrl;
  els.saveButton.disabled = busy;
}

/**
 * Renders a user-facing status message.
 *
 * Args:
 *   text: Message text.
 *   kind: Optional visual state.
 */
function setMessage(text, kind = '') {
  els.message.textContent = text;
  els.message.className = 'message' + (kind ? ' ' + kind : '');
}

/**
 * Calls the Worker JSON API.
 *
 * Args:
 *   path: API path beginning with `/`.
 *   options: Fetch options.
 *
 * Returns:
 *   Parsed JSON response.
 *
 * Raises:
 *   Error: When the Worker returns a non-2xx response.
 */
async function apiFetch(path, options = {}) {
  const response = await fetch(state.workerUrl + path, {
    ...options,
    headers: {
      Authorization: 'Bearer ' + state.controlToken,
      ...(options.headers || {}),
    },
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(payload?.error?.message || 'Request failed with ' + response.status);
  }
  return payload;
}

/**
 * Refreshes backend/frontend service status once.
 *
 * Args:
 *   options: Controls quiet and busy-state behavior.
 *
 * Returns:
 *   Worker status payload, or null when the refresh failed.
 */
async function refreshStatus(options = {}) {
  const quiet = Boolean(options.quiet);
  const allowWhileBusy = Boolean(options.allowWhileBusy);
  if (!state.workerUrl || !state.controlToken || (state.busy && !allowWhileBusy)) return null;

  if (!quiet) setMessage('Refreshing status...');
  if (!allowWhileBusy) setBusy(true);

  try {
    const payload = await apiFetch('/api/status');
    state.appUrl = payload.appUrl || '';
    els.statusGrid.innerHTML = payload.services.map(serviceCard).join('');
    els.updatedAt.textContent = 'Last updated: ' + new Date().toLocaleTimeString();
    await cacheStatus(payload);
    if (!quiet) setMessage('Status refreshed.', 'ok');
    return payload;
  } catch (error) {
    setMessage(error.message, 'error');
    return null;
  } finally {
    if (!allowWhileBusy) setBusy(false);
  }
}

/**
 * Runs a Render action through the Worker.
 *
 * Args:
 *   action: `resume` or `suspend`.
 */
async function runAction(action) {
  if (!state.workerUrl || !state.controlToken || state.busy) return;
  setMessage(action === 'resume' ? 'Starting AREQA services...' : 'Suspending AREQA services...');
  setBusy(true);

  try {
    const payload = await apiFetch('/api/' + action, { method: 'POST' });
    state.appUrl = payload.appUrl || state.appUrl;
    els.statusGrid.innerHTML = payload.services.map(serviceCard).join('');
    els.updatedAt.textContent = 'Last updated: ' + new Date().toLocaleTimeString();
    await cacheStatus(payload);
    setMessage(
      payload.ok
        ? (action === 'resume' ? 'Resume requested. Checking every second...' : 'Suspend requested. Checking for 10 seconds...')
        : 'Some services returned an error.',
      payload.ok ? 'ok' : 'error',
    );
    if (payload.ok) startActionPolling(action);
  } catch (error) {
    setMessage(error.message, 'error');
  } finally {
    setBusy(false);
  }
}

/**
 * Polls after a resume/suspend action only.
 *
 * Args:
 *   action: Action that determines terminal condition and timeout.
 */
function startActionPolling(action) {
  stopActionPolling();
  const deadline = Date.now() + (action === 'resume' ? RESUME_TIMEOUT_MS : SUSPEND_DURATION_MS);

  state.pollTimer = setInterval(async () => {
    const payload = await refreshStatus({ quiet: true, allowWhileBusy: true });
    const services = payload?.services || [];

    if (action === 'resume' && everyServiceHasState(services, 'active')) {
      stopActionPolling();
      setMessage('AREQA services are active.', 'ok');
      return;
    }

    if (action === 'resume' && services.some((service) => service.state === 'failed')) {
      stopActionPolling();
      setMessage('At least one service failed to deploy.', 'error');
      return;
    }

    if (action === 'suspend' && everyServiceHasState(services, 'suspended')) {
      stopActionPolling();
      setMessage('AREQA services are suspended.', 'ok');
      return;
    }

    if (Date.now() >= deadline) {
      stopActionPolling();
      setMessage(
        action === 'resume'
          ? 'AREQA is still starting. Use Refresh to check again.'
          : 'Suspend check finished. Use Refresh to verify later.',
      );
    }
  }, POLL_MS);
}

/**
 * Stops action-scoped polling.
 */
function stopActionPolling() {
  if (state.pollTimer) {
    clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
}

/**
 * Checks if every configured service is in the expected state.
 *
 * Args:
 *   services: Service status summaries from the Worker.
 *   expectedState: Target state.
 *
 * Returns:
 *   True when both backend and frontend match the target state.
 */
function everyServiceHasState(services, expectedState) {
  return Array.isArray(services)
    && services.length === 2
    && services.every((service) => service.state === expectedState);
}

/**
 * Renders one service card.
 *
 * Args:
 *   service: Service summary from the Worker.
 *
 * Returns:
 *   Escaped HTML for the card.
 */
function serviceCard(service) {
  const stateName = service.state || 'unknown';
  const detail = [
    'service: ' + (service.serviceStatus || 'unknown'),
    'deploy: ' + (service.latestDeployStatus || 'unknown'),
  ].join(' · ');
  return '<article class="service">' +
    '<div class="service-top">' +
      '<div class="service-name">' + escapeHtml(service.label || service.name || 'service') + '</div>' +
      '<div class="pill ' + escapeHtml(stateName) + '">' + escapeHtml(stateName) + '</div>' +
    '</div>' +
    '<div class="details">' + escapeHtml(detail) + '</div>' +
  '</article>';
}

/**
 * Escapes text for HTML insertion.
 *
 * Args:
 *   value: Unknown display value.
 *
 * Returns:
 *   HTML-escaped string.
 */
function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  })[char]);
}

els.saveButton.addEventListener('click', saveSettings);
els.clearButton.addEventListener('click', clearSettings);
els.refreshButton.addEventListener('click', () => refreshStatus());
els.resumeButton.addEventListener('click', () => runAction('resume'));
els.suspendButton.addEventListener('click', () => runAction('suspend'));
els.openButton.addEventListener('click', () => {
  if (state.appUrl) chrome.tabs.create({ url: state.appUrl });
});

init();
