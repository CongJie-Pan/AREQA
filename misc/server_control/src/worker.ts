/**
 * AREQA Render service control Worker.
 *
 * This Cloudflare Worker serves a compact mobile control page and exposes a
 * token-protected JSON API for checking and changing the Render state of only
 * the AREQA backend and frontend services. Render credentials stay in Worker
 * secrets and are never sent to browsers.
 */

interface Env {
  RENDER_API_KEY: string;
  RENDER_BACKEND_SERVICE_ID: string;
  RENDER_FRONTEND_SERVICE_ID: string;
  CONTROL_TOKEN: string;
  AREQA_APP_URL?: string;
}

type ServiceLabel = 'backend' | 'frontend';
type ControlAction = 'resume' | 'suspend';

interface RenderServiceSummary {
  label: ServiceLabel;
  id: string;
  name: string;
  state: 'active' | 'suspended' | 'deploying' | 'failed' | 'unknown';
  serviceStatus: string | null;
  latestDeployStatus: string | null;
  updatedAt: string | null;
}

interface ApiErrorBody {
  error: {
    code: string;
    message: string;
  };
}

const RENDER_API_BASE = 'https://api.render.com/v1';
const JSON_HEADERS = {
  'Content-Type': 'application/json; charset=utf-8',
  'Cache-Control': 'no-store',
};

/**
 * Handles all control page and API requests.
 *
 * Args:
 *   request: Incoming Cloudflare Worker request.
 *   env: Worker secret and configuration bindings.
 *
 * Returns:
 *   A Response containing HTML for the control page or JSON for API calls.
 *
 * Side Effects:
 *   Calls the Render API for service status, resume, and suspend operations.
 *   Emits safe operational logs with stable event names and service labels
 *   only; credentials, tokens, and raw upstream payloads are never logged.
 */
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    try {
      if (url.pathname === '/') {
        return htmlResponse(renderControlPage(env.AREQA_APP_URL ?? ''));
      }

      if (url.pathname === '/api/status' && request.method === 'GET') {
        const auth = requireControlToken(request, env);
        if (auth) return auth;
        const services = await fetchAllServiceSummaries(env);
        return jsonResponse({ services, appUrl: env.AREQA_APP_URL ?? null });
      }

      if (url.pathname === '/api/resume' && request.method === 'POST') {
        return handleAction(request, env, 'resume');
      }

      if (url.pathname === '/api/suspend' && request.method === 'POST') {
        return handleAction(request, env, 'suspend');
      }

      return jsonError('NOT_FOUND', 'Route not found.', 404);
    } catch (error) {
      console.error('server_control.unhandled_error', {
        reason: error instanceof Error ? error.message : String(error),
      });
      return jsonError('INTERNAL_ERROR', 'Unexpected server control error.', 500);
    }
  },
};

/**
 * Runs a resume or suspend action against the AREQA backend and frontend only.
 *
 * Args:
 *   request: Incoming POST request containing the control token.
 *   env: Worker secret bindings for Render credentials and service IDs.
 *   action: Render service action to apply.
 *
 * Returns:
 *   JSON with per-service action outcomes and refreshed service summaries.
 */
async function handleAction(
  request: Request,
  env: Env,
  action: ControlAction,
): Promise<Response> {
  const auth = requireControlToken(request, env);
  if (auth) return auth;

  console.info('server_control.action_started', { action, serviceCount: 2 });
  const results = await Promise.all(getConfiguredServices(env).map(async (service) => {
    try {
      await callRenderApi(env, `/services/${service.id}/${action}`, { method: 'POST' });
      console.info('server_control.action_service_succeeded', {
        action,
        label: service.label,
      });
      return { label: service.label, ok: true };
    } catch (error) {
      console.warn('server_control.action_service_failed', {
        action,
        label: service.label,
        reason: error instanceof Error ? error.message : String(error),
      });
      return {
        label: service.label,
        ok: false,
        error: error instanceof Error ? error.message : String(error),
      };
    }
  }));

  const services = await fetchAllServiceSummaries(env);
  const ok = results.every((result) => result.ok);
  return jsonResponse({ ok, action, results, services }, ok ? 200 : 502);
}

/**
 * Validates the browser-provided control token.
 *
 * Args:
 *   request: Incoming request.
 *   env: Worker bindings containing CONTROL_TOKEN.
 *
 * Returns:
 *   A 401 Response when authentication fails, otherwise null.
 */
function requireControlToken(request: Request, env: Env): Response | null {
  const providedToken = extractControlToken(request);
  if (!env.CONTROL_TOKEN || providedToken !== env.CONTROL_TOKEN) {
    console.warn('server_control.auth_rejected', {
      hasToken: Boolean(providedToken),
      configured: Boolean(env.CONTROL_TOKEN),
    });
    return jsonError('UNAUTHORIZED', 'Invalid control token.', 401);
  }
  return null;
}

/**
 * Extracts the control token from browser-compatible headers.
 *
 * Args:
 *   request: Incoming API request.
 *
 * Returns:
 *   Token string from Authorization Bearer or X-Control-Token headers.
 */
function extractControlToken(request: Request): string | null {
  const authorization = request.headers.get('Authorization');
  if (authorization?.startsWith('Bearer ')) {
    return authorization.slice('Bearer '.length).trim();
  }
  return request.headers.get('X-Control-Token');
}

/**
 * Returns the two Render services this controller owns.
 *
 * Args:
 *   env: Worker bindings containing Render service IDs.
 *
 * Returns:
 *   Backend and frontend service descriptors.
 */
function getConfiguredServices(env: Env): Array<{ label: ServiceLabel; id: string }> {
  return [
    { label: 'backend', id: env.RENDER_BACKEND_SERVICE_ID },
    { label: 'frontend', id: env.RENDER_FRONTEND_SERVICE_ID },
  ];
}

/**
 * Fetches current status summaries for the AREQA backend and frontend.
 *
 * Args:
 *   env: Worker bindings containing Render credentials and service IDs.
 *
 * Returns:
 *   Summaries suitable for browser display.
 */
async function fetchAllServiceSummaries(env: Env): Promise<RenderServiceSummary[]> {
  return Promise.all(getConfiguredServices(env).map((service) => fetchServiceSummary(env, service)));
}

/**
 * Fetches and normalizes one Render service status.
 *
 * Args:
 *   env: Worker bindings containing Render credentials.
 *   service: Label and ID of the configured Render service.
 *
 * Returns:
 *   A normalized service summary. Render response fields are intentionally read
 *   defensively because the public API shape differs slightly between service
 *   types and versions.
 */
async function fetchServiceSummary(
  env: Env,
  service: { label: ServiceLabel; id: string },
): Promise<RenderServiceSummary> {
  try {
    const [servicePayload, deployPayload] = await Promise.all([
      callRenderApi(env, `/services/${service.id}`),
      callRenderApi(env, `/services/${service.id}/deploys?limit=1`),
    ]);

    const latestDeploy = firstArrayItem(deployPayload);
    const serviceStatus = readString(servicePayload, ['status', 'service.status', 'suspended']);
    const latestDeployStatus = readString(latestDeploy, ['status', 'deploy.status']);

    return {
      label: service.label,
      id: service.id,
      name: readString(servicePayload, ['name', 'service.name']) ?? service.label,
      state: normalizeServiceState(servicePayload, serviceStatus, latestDeployStatus),
      serviceStatus,
      latestDeployStatus,
      updatedAt: readString(servicePayload, [
        'updatedAt',
        'updated_at',
        'service.updatedAt',
        'service.updated_at',
      ]),
    };
  } catch (error) {
    console.warn('server_control.status_service_failed', {
      label: service.label,
      reason: error instanceof Error ? error.message : String(error),
    });
    return {
      label: service.label,
      id: service.id,
      name: service.label,
      state: 'unknown',
      serviceStatus: null,
      latestDeployStatus: null,
      updatedAt: null,
    };
  }
}

/**
 * Calls the Render API with Worker-held credentials.
 *
 * Args:
 *   env: Worker bindings containing RENDER_API_KEY.
 *   path: Render API path beginning with `/`.
 *   init: Optional fetch options.
 *
 * Returns:
 *   Parsed JSON response, or null for an empty successful response.
 *
 * Raises:
 *   Error: When Render returns a non-2xx response or invalid JSON.
 */
async function callRenderApi(env: Env, path: string, init: RequestInit = {}): Promise<unknown> {
  const response = await fetch(`${RENDER_API_BASE}${path}`, {
    ...init,
    headers: {
      Accept: 'application/json',
      Authorization: `Bearer ${env.RENDER_API_KEY}`,
      ...(init.headers ?? {}),
    },
  });

  const text = await response.text();
  if (!response.ok) {
    throw new Error(`Render API returned ${response.status}`);
  }
  if (!text) return null;

  try {
    return JSON.parse(text);
  } catch {
    throw new Error('Render API returned invalid JSON');
  }
}

/**
 * Normalizes Render service and deploy fields into UI states.
 *
 * Args:
 *   servicePayload: Raw Render service payload.
 *   serviceStatus: Best-effort service status string.
 *   latestDeployStatus: Best-effort latest deploy status string.
 *
 * Returns:
 *   A compact state for the control page.
 */
function normalizeServiceState(
  servicePayload: unknown,
  serviceStatus: string | null,
  latestDeployStatus: string | null,
): RenderServiceSummary['state'] {
  const suspendedValue = readUnknown(servicePayload, ['suspended', 'service.suspended']);
  const suspenders = readUnknown(servicePayload, ['suspenders', 'service.suspenders']);
  const status = `${serviceStatus ?? ''}`.toLowerCase();
  const deployStatus = `${latestDeployStatus ?? ''}`.toLowerCase();

  if (
    suspendedValue === true ||
    status === 'suspended' ||
    (Array.isArray(suspenders) && suspenders.length > 0)
  ) {
    return 'suspended';
  }

  if (deployStatus.includes('failed') || deployStatus === 'canceled') {
    return 'failed';
  }

  if (
    deployStatus.includes('progress') ||
    deployStatus === 'created' ||
    status.includes('deploy')
  ) {
    return 'deploying';
  }

  if (status === 'active' || deployStatus === 'live') {
    return 'active';
  }

  return 'unknown';
}

/**
 * Reads the first item from Render list payload variants.
 *
 * Args:
 *   payload: Raw JSON returned by Render.
 *
 * Returns:
 *   First array item when available, otherwise null.
 */
function firstArrayItem(payload: unknown): unknown {
  if (Array.isArray(payload)) return payload[0] ?? null;
  const items = readUnknown(payload, ['items', 'deploys']);
  return Array.isArray(items) ? items[0] ?? null : null;
}

/**
 * Reads a string from the first matching dotted path.
 *
 * Args:
 *   source: Unknown object to inspect.
 *   paths: Dotted property paths to try.
 *
 * Returns:
 *   String value when present, otherwise null.
 */
function readString(source: unknown, paths: string[]): string | null {
  for (const path of paths) {
    const value = readUnknown(source, [path]);
    if (typeof value === 'string' && value.length > 0) return value;
    if (typeof value === 'boolean') return String(value);
  }
  return null;
}

/**
 * Reads the first available value from dotted object paths.
 *
 * Args:
 *   source: Unknown object to inspect.
 *   paths: Dotted property paths to try.
 *
 * Returns:
 *   The matched value, or null when no path exists.
 */
function readUnknown(source: unknown, paths: string[]): unknown {
  for (const path of paths) {
    const value = path.split('.').reduce<unknown>((current, segment) => {
      if (current && typeof current === 'object' && segment in current) {
        return (current as Record<string, unknown>)[segment];
      }
      return undefined;
    }, source);
    if (value !== undefined && value !== null) return value;
  }
  return null;
}

/**
 * Creates a JSON response.
 *
 * Args:
 *   body: Serializable response body.
 *   status: HTTP status code.
 *
 * Returns:
 *   JSON Response with no-store caching.
 */
function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: JSON_HEADERS,
  });
}

/**
 * Creates a JSON error response.
 *
 * Args:
 *   code: Stable machine-readable error code.
 *   message: Human-readable error message.
 *   status: HTTP status code.
 *
 * Returns:
 *   JSON error Response with no-store caching.
 */
function jsonError(code: string, message: string, status: number): Response {
  const body: ApiErrorBody = { error: { code, message } };
  return jsonResponse(body, status);
}

/**
 * Creates an HTML response for the control page.
 *
 * Args:
 *   html: HTML document string.
 *
 * Returns:
 *   HTML Response with no-store caching.
 */
function htmlResponse(html: string): Response {
  return new Response(html, {
    headers: {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-store',
    },
  });
}

/**
 * Renders the one-page mobile control UI.
 *
 * Args:
 *   appUrl: Optional AREQA application URL used by the Open AREQA button.
 *
 * Returns:
 *   Complete HTML document. The inline script calls only this Worker API, never
 *   Render directly, so Render credentials remain server-side.
 */
function renderControlPage(appUrl: string): string {
  const safeAppUrl = JSON.stringify(appUrl);
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="theme-color" content="#111827">
  <title>AREQA Control</title>
  <style>
    :root {
      color-scheme: dark;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #0f172a;
      color: #f8fafc;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background: #0f172a;
    }
    main {
      width: min(100%, 480px);
      min-height: 100vh;
      margin: 0 auto;
      padding: 24px 18px calc(28px + env(safe-area-inset-bottom));
      display: flex;
      flex-direction: column;
      gap: 18px;
    }
    header {
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: 16px;
    }
    h1 {
      margin: 0;
      font-size: 28px;
      line-height: 1.05;
      letter-spacing: 0;
    }
    .subtitle {
      margin: 8px 0 0;
      color: #cbd5e1;
      font-size: 14px;
    }
    .status-grid {
      display: grid;
      gap: 12px;
    }
    .service {
      border: 1px solid #334155;
      border-radius: 8px;
      padding: 16px;
      background: #111827;
    }
    .service-top {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }
    .service-name {
      font-size: 15px;
      font-weight: 700;
      text-transform: capitalize;
    }
    .pill {
      min-width: 92px;
      border-radius: 999px;
      padding: 7px 10px;
      text-align: center;
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      border: 1px solid #475569;
      color: #e2e8f0;
      background: #1e293b;
    }
    .pill.active { border-color: #22c55e; color: #bbf7d0; background: #052e16; }
    .pill.suspended { border-color: #64748b; color: #cbd5e1; background: #1e293b; }
    .pill.deploying { border-color: #f59e0b; color: #fde68a; background: #451a03; }
    .pill.failed { border-color: #ef4444; color: #fecaca; background: #450a0a; }
    .details {
      margin-top: 10px;
      color: #94a3b8;
      font-size: 12px;
      line-height: 1.5;
      word-break: break-word;
    }
    .actions {
      display: grid;
      gap: 10px;
    }
    .row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }
    button, a.button {
      width: 100%;
      min-height: 48px;
      border: 1px solid #475569;
      border-radius: 8px;
      padding: 12px 14px;
      color: #f8fafc;
      background: #1e293b;
      font: inherit;
      font-weight: 700;
      text-align: center;
      text-decoration: none;
      cursor: pointer;
    }
    button.primary { border-color: #2563eb; background: #1d4ed8; }
    button.danger { border-color: #dc2626; background: #991b1b; }
    button:disabled {
      cursor: not-allowed;
      opacity: 0.62;
    }
    .token-panel {
      border: 1px solid #334155;
      border-radius: 8px;
      padding: 16px;
      background: #111827;
    }
    label {
      display: block;
      margin-bottom: 8px;
      color: #cbd5e1;
      font-size: 13px;
      font-weight: 700;
    }
    input {
      width: 100%;
      min-height: 46px;
      border: 1px solid #475569;
      border-radius: 8px;
      padding: 11px 12px;
      color: #f8fafc;
      background: #020617;
      font: inherit;
    }
    .message {
      min-height: 22px;
      color: #cbd5e1;
      font-size: 13px;
      line-height: 1.5;
    }
    .message.error { color: #fecaca; }
    .message.ok { color: #bbf7d0; }
    footer {
      margin-top: auto;
      color: #64748b;
      font-size: 12px;
      line-height: 1.5;
    }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>AREQA Control</h1>
        <p class="subtitle">Backend and frontend only</p>
      </div>
      <button id="lockButton" type="button">Lock</button>
    </header>

    <section id="tokenPanel" class="token-panel" hidden>
      <label for="tokenInput">Control token</label>
      <input id="tokenInput" type="password" autocomplete="current-password" placeholder="Enter CONTROL_TOKEN">
      <div style="height: 10px"></div>
      <button id="saveTokenButton" class="primary" type="button">Unlock</button>
    </section>

    <section class="status-grid" id="statusGrid"></section>

    <section class="actions">
      <button id="resumeButton" class="primary" type="button">Resume All</button>
      <button id="suspendButton" class="danger" type="button">Suspend All</button>
      <div class="row">
        <button id="refreshButton" type="button">Refresh</button>
        <a id="openButton" class="button" href="#" target="_blank" rel="noopener noreferrer">Open AREQA</a>
      </div>
    </section>

    <div id="message" class="message"></div>
    <footer id="updatedAt">Not refreshed yet</footer>
  </main>

  <script>
    const configuredAppUrl = ${safeAppUrl};
    const tokenKey = 'areqa-control-token';
    const pollMs = 5000;
    let token = localStorage.getItem(tokenKey) || '';
    let busy = false;
    let pollTimer = null;

    const els = {
      tokenPanel: document.getElementById('tokenPanel'),
      tokenInput: document.getElementById('tokenInput'),
      saveTokenButton: document.getElementById('saveTokenButton'),
      lockButton: document.getElementById('lockButton'),
      statusGrid: document.getElementById('statusGrid'),
      resumeButton: document.getElementById('resumeButton'),
      suspendButton: document.getElementById('suspendButton'),
      refreshButton: document.getElementById('refreshButton'),
      openButton: document.getElementById('openButton'),
      message: document.getElementById('message'),
      updatedAt: document.getElementById('updatedAt'),
    };

    function setBusy(nextBusy) {
      busy = nextBusy;
      els.resumeButton.disabled = busy || !token;
      els.suspendButton.disabled = busy || !token;
      els.refreshButton.disabled = busy || !token;
      els.saveTokenButton.disabled = busy;
    }

    function setMessage(text, kind = '') {
      els.message.textContent = text;
      els.message.className = 'message' + (kind ? ' ' + kind : '');
    }

    function renderLockedState() {
      const locked = !token;
      els.tokenPanel.hidden = !locked;
      els.lockButton.hidden = locked;
      setBusy(false);
      if (locked) {
        els.statusGrid.innerHTML = '';
        setMessage('Enter your control token to manage AREQA services.');
      }
    }

    function serviceCard(service) {
      const state = service.state || 'unknown';
      const detail = [
        'service: ' + (service.serviceStatus || 'unknown'),
        'deploy: ' + (service.latestDeployStatus || 'unknown'),
      ].join(' · ');
      return '<article class="service">' +
        '<div class="service-top">' +
          '<div class="service-name">' + escapeHtml(service.label || service.name || 'service') + '</div>' +
          '<div class="pill ' + escapeHtml(state) + '">' + escapeHtml(state) + '</div>' +
        '</div>' +
        '<div class="details">' + escapeHtml(detail) + '</div>' +
      '</article>';
    }

    function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, (char) => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
      })[char]);
    }

    async function apiFetch(path, options = {}) {
      const response = await fetch(path, {
        ...options,
        headers: {
          Authorization: 'Bearer ' + token,
          ...(options.headers || {}),
        },
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(payload?.error?.message || 'Request failed with ' + response.status);
      }
      return payload;
    }

    async function refreshStatus({ quiet = false } = {}) {
      if (!token || busy) return;
      if (!quiet) setMessage('Refreshing status...');
      setBusy(true);
      try {
        const payload = await apiFetch('/api/status');
        els.statusGrid.innerHTML = payload.services.map(serviceCard).join('');
        const appUrl = payload.appUrl || configuredAppUrl;
        if (appUrl) {
          els.openButton.href = appUrl;
          els.openButton.removeAttribute('aria-disabled');
        } else {
          els.openButton.href = '#';
          els.openButton.setAttribute('aria-disabled', 'true');
        }
        els.updatedAt.textContent = 'Last updated: ' + new Date().toLocaleTimeString();
        if (!quiet) setMessage('Status refreshed.', 'ok');
      } catch (error) {
        setMessage(error.message, 'error');
        if (error.message.includes('Invalid control token')) {
          localStorage.removeItem(tokenKey);
          token = '';
          renderLockedState();
        }
      } finally {
        setBusy(false);
      }
    }

    async function runAction(action) {
      if (!token || busy) return;
      setMessage(action === 'resume' ? 'Starting AREQA services...' : 'Suspending AREQA services...');
      setBusy(true);
      try {
        const payload = await apiFetch('/api/' + action, { method: 'POST' });
        els.statusGrid.innerHTML = payload.services.map(serviceCard).join('');
        els.updatedAt.textContent = 'Last updated: ' + new Date().toLocaleTimeString();
        setMessage(payload.ok ? 'Action completed.' : 'Some services returned an error.', payload.ok ? 'ok' : 'error');
      } catch (error) {
        setMessage(error.message, 'error');
      } finally {
        setBusy(false);
      }
    }

    function startPolling() {
      if (pollTimer) clearInterval(pollTimer);
      pollTimer = setInterval(() => refreshStatus({ quiet: true }), pollMs);
    }

    els.saveTokenButton.addEventListener('click', () => {
      token = els.tokenInput.value.trim();
      if (!token) return;
      localStorage.setItem(tokenKey, token);
      renderLockedState();
      refreshStatus();
      startPolling();
    });

    els.lockButton.addEventListener('click', () => {
      localStorage.removeItem(tokenKey);
      token = '';
      renderLockedState();
    });

    els.resumeButton.addEventListener('click', () => runAction('resume'));
    els.suspendButton.addEventListener('click', () => runAction('suspend'));
    els.refreshButton.addEventListener('click', () => refreshStatus());
    els.openButton.addEventListener('click', (event) => {
      if (!els.openButton.href || els.openButton.href.endsWith('#')) event.preventDefault();
    });

    renderLockedState();
    if (token) {
      refreshStatus();
      startPolling();
    }
  </script>
</body>
</html>`;
}
