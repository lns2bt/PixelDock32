let token = localStorage.getItem('token') || '';
const gridState = Array.from({ length: 8 }, () => Array(32).fill(0));
let pollTimerStatus = null;
let pollTimerPreview = null;

function authHeaders() {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function startPollingLoops() {
  if (pollTimerStatus) clearInterval(pollTimerStatus);
  if (pollTimerPreview) clearInterval(pollTimerPreview);
  pollTimerStatus = setInterval(refreshStatus, 5000);
  pollTimerPreview = setInterval(refreshPreview, 1000);
}

function toast(message, isError = false) {
  const el = document.getElementById('toast');
  el.innerText = message;
  el.style.background = isError ? '#8b0000' : '#111827';
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 1800);
}

function formatTs(ts) {
  if (!ts) return '-';
  return new Date(ts * 1000).toLocaleTimeString();
}

async function apiRequest(path, options = {}, okMessage = '') {
  try {
    const res = await fetch(path, {
      ...options,
      headers: {
        ...(options.headers || {}),
        ...authHeaders(),
      },
    });

    let data = null;
    try {
      data = await res.json();
    } catch (_err) {
      data = null;
    }

    if (!res.ok) {
      const msg = data?.detail || `HTTP ${res.status}`;
      toast(`Fehler: ${msg}`, true);
      return null;
    }

    if (okMessage) toast(okMessage);
    return data;
  } catch (_err) {
    toast('Netzwerkfehler', true);
    return null;
  }
}

function moduleSettingsHtml(module) {
  const s = module.settings || {};

  if (module.key === 'clock') {
    return `
      <div class="settings-grid">
        <div class="field">
          <label for="set-tz-${module.id}">Zeitzone</label>
          <input id="set-tz-${module.id}" value="${s.timezone || 'Europe/Vienna'}" placeholder="Europe/Vienna" />
        </div>
        <div class="field">
          <label>Anzeige</label>
          <label class="check-label"><input type="checkbox" id="set-sec-${module.id}" ${s.show_seconds !== false ? 'checked' : ''}> Sekunden anzeigen</label>
        </div>
      </div>
    `;
  }

  if (module.key === 'btc') {
    return '<p class="subtle">BTC wird automatisch im kompakten k-Format angezeigt (z. B. 56.8k). Das B vorne ist orange, Preisfarbe hängt vom Trend ab.</p>';
  }

  if (module.key === 'weather') {
    return `
      <div class="settings-grid">
        <div class="field">
          <label for="set-post-${module.id}">Postleitzahl (Info)</label>
          <input id="set-post-${module.id}" value="${s.postcode || '6020'}" placeholder="6020" />
        </div>
        <div class="field">
          <label>Anzeige</label>
          <p class="subtle">Nur Temperatur in Celsius. Farbe: kalt = blau, warm = rot.</p>
        </div>
      </div>
    `;
  }

  return '<p class="subtle">Keine Settings verfügbar.</p>';
}

function collectModuleSettings({ id: moduleId, key: moduleKey }) {
  if (moduleKey === 'clock') {
    return {
      timezone: document.getElementById(`set-tz-${moduleId}`).value.trim() || 'Europe/Vienna',
      show_seconds: document.getElementById(`set-sec-${moduleId}`).checked,
    };
  }

  if (moduleKey === 'btc') {
    return {};
  }

  if (moduleKey === 'weather') {
    return {
      postcode: document.getElementById(`set-post-${moduleId}`).value.trim() || '6020',
    };
  }

  return {};
}

async function login() {
  const username = document.getElementById('username').value;
  const password = document.getElementById('password').value;
  const data = await apiRequest(
    '/api/auth/login',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    },
    'Login erfolgreich',
  );

  if (!data?.access_token) {
    document.getElementById('loginStatus').innerText = 'Login fehlgeschlagen';
    return;
  }
  token = data.access_token;
  localStorage.setItem('token', token);
  document.getElementById('loginStatus').innerText = 'Eingeloggt';

  await Promise.all([loadModules(), refreshStatus(), refreshPreview()]);
  startPollingLoops();
}

async function loadModules() {
  const modules = await apiRequest('/api/modules');
  if (!modules) return;

  const container = document.getElementById('modules');
  container.innerHTML = '';

  modules.forEach((m) => {
    const row = document.createElement('div');
    row.className = 'module-row';
    row.innerHTML = `
      <div class="field">
        <label>Modul</label>
        <div class="module-name">${m.name}</div>
      </div>
      <div class="field">
        <label>Aktiv</label>
        <label class="check-label"><input type="checkbox" ${m.enabled ? 'checked' : ''} id="en-${m.id}"> aktiv</label>
      </div>
      <div class="field">
        <label for="dur-${m.id}">Dauer (Sek.)</label>
        <input type="number" id="dur-${m.id}" value="${m.duration_seconds}" min="1">
      </div>
      <div class="field">
        <label for="ord-${m.id}">Reihenfolge</label>
        <input type="number" id="ord-${m.id}" value="${m.sort_order}">
      </div>
      <div class="field actions-end">
        <button class="btn" onclick="saveModule(${m.id}, '${m.key}')">Speichern</button>
      </div>
      <div class="module-settings">
        <label class="settings-title">Moduleinstellungen</label>
        ${moduleSettingsHtml(m)}
      </div>
    `;
    container.appendChild(row);
  });
}

async function saveModule(moduleId, moduleKey) {
  const duration = parseInt(document.getElementById(`dur-${moduleId}`).value, 10);
  const sortOrder = parseInt(document.getElementById(`ord-${moduleId}`).value, 10);
  if (!Number.isInteger(duration) || duration < 1) {
    toast('Dauer muss >= 1 sein', true);
    return;
  }
  if (!Number.isInteger(sortOrder)) {
    toast('Reihenfolge muss Zahl sein', true);
    return;
  }

  const payload = {
    enabled: document.getElementById(`en-${moduleId}`).checked,
    duration_seconds: duration,
    sort_order: sortOrder,
    settings: collectModuleSettings({ id: moduleId, key: moduleKey }),
  };

  const res = await apiRequest(
    `/api/modules/${moduleId}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
    'Modul gespeichert',
  );
  if (res) {
    await Promise.all([loadModules(), refreshStatus(), refreshPreview()]);
  }
}

async function sendText() {
  const text = document.getElementById('manualText').value;
  const seconds = parseInt(document.getElementById('manualSeconds').value, 10);
  const res = await apiRequest('/api/display/text', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, seconds }),
  }, 'Text gesendet');
  if (res) {
    await refreshStatus();
    await refreshPreview();
  }
}

async function setBrightness() {
  const brightness = parseInt(document.getElementById('brightness').value, 10);
  const res = await apiRequest('/api/display/brightness', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ brightness }),
  }, 'Helligkeit gesetzt');
  if (res) await refreshStatus();
}

async function startDebugPattern() {
  const payload = {
    pattern: document.getElementById('debugPattern').value,
    seconds: parseInt(document.getElementById('debugSeconds').value, 10),
    interval_ms: parseInt(document.getElementById('debugInterval').value, 10),
  };
  const res = await apiRequest('/api/debug/pattern', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }, 'Debug-Pattern gestartet');
  if (res) {
    await refreshStatus();
    await refreshPreview();
  }
}

async function stopDebugPattern() {
  const res = await apiRequest('/api/debug/pattern', { method: 'DELETE' }, 'Debug-Pattern gestoppt');
  if (res) {
    await refreshStatus();
    await refreshPreview();
  }
}

function runPreset(pattern, seconds, intervalMs) {
  document.getElementById('debugPattern').value = pattern;
  document.getElementById('debugSeconds').value = seconds;
  document.getElementById('debugInterval').value = intervalMs;
  startDebugPattern();
}

async function refreshStatus() {
  const data = await apiRequest('/api/debug/status');
  if (!data) {
    document.getElementById('statusApi').innerText = token ? 'offline / auth?' : 'nicht eingeloggt';
    return;
  }

  document.getElementById('statusApi').innerText = 'online';
  document.getElementById('statusSource').innerText = data.display.last_source || '-';
  document.getElementById('statusModule').innerText = data.display.last_module || '-';
  document.getElementById('statusFps').innerText = `${data.display.target_fps} / ${data.display.actual_fps}`;
  document.getElementById('statusDebug').innerText = data.display.debug_active
    ? `${data.display.debug_pattern} bis ${formatTs(data.display.debug_until)}`
    : 'inaktiv';
  document.getElementById('statusBtc').innerText = data.data.btc_error
    ? `Fehler (${data.data.btc_error.slice(0, 28)}...)`
    : formatTs(data.data.btc_updated_at);
  document.getElementById('statusWeather').innerText = data.data.weather_error
    ? `Fehler (${data.data.weather_error.slice(0, 28)}...)`
    : formatTs(data.data.weather_updated_at);
}

function initPreviewGrid() {
  const container = document.getElementById('previewGrid');
  if (!container || container.childElementCount > 0) return;
  for (let y = 0; y < 8; y += 1) {
    for (let x = 0; x < 32; x += 1) {
      const px = document.createElement('div');
      px.className = 'preview-pixel';
      px.id = `preview-${x}-${y}`;
      container.appendChild(px);
    }
  }
}

function renderPreviewFrame(frame, colors = null) {
  if (!Array.isArray(frame)) return;
  for (let y = 0; y < 8; y += 1) {
    for (let x = 0; x < 32; x += 1) {
      const el = document.getElementById(`preview-${x}-${y}`);
      if (!el) continue;
      const on = !!(frame[y] && frame[y][x]);
      el.classList.toggle('on', on);
      if (!on) {
        el.style.backgroundColor = '';
        continue;
      }
      const c = colors && colors[y] && colors[y][x] ? colors[y][x] : [37, 99, 235];
      el.style.backgroundColor = `rgb(${c[0]}, ${c[1]}, ${c[2]})`;
    }
  }
}

async function refreshPreview() {
  if (!token) return;
  const data = await apiRequest('/api/debug/preview');
  if (!data?.frame) return;
  renderPreviewFrame(data.frame, data.colors || null);
}

async function checkMappingCoordinate() {
  const x = parseInt(document.getElementById('mapX').value, 10);
  const y = parseInt(document.getElementById('mapY').value, 10);
  if (!Number.isInteger(x) || !Number.isInteger(y) || x < 0 || x > 31 || y < 0 || y > 7) {
    toast('X/Y müssen im Bereich 0..31 / 0..7 liegen', true);
    return;
  }

  const data = await apiRequest(`/api/debug/mapping/coordinate?x=${x}&y=${y}`);
  if (!data?.mapping) return;

  const m = data.mapping;
  document.getElementById('mappingInfo').innerText =
    `x=${m.x}, y=${m.y} -> panel=${m.panel_index}, local=(${m.local_x},${m.local_y}), pixel_in_panel=${m.pixel_in_panel}, led_index=${m.index}, serpentine_flip=${m.serpentine_flipped}`;
}

function initGrid() {
  const grid = document.getElementById('grid');
  for (let y = 0; y < 8; y += 1) {
    for (let x = 0; x < 32; x += 1) {
      const pixel = document.createElement('div');
      pixel.className = 'pixel';
      pixel.onclick = () => {
        gridState[y][x] = gridState[y][x] ? 0 : 1;
        pixel.classList.toggle('on', !!gridState[y][x]);
      };
      grid.appendChild(pixel);
    }
  }
}

function clearGrid() {
  const pixels = document.querySelectorAll('.pixel');
  pixels.forEach((p) => p.classList.remove('on'));
  for (let y = 0; y < 8; y += 1) {
    for (let x = 0; x < 32; x += 1) {
      gridState[y][x] = 0;
    }
  }
}

async function sendGrid() {
  const res = await apiRequest('/api/display/draw', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pixels: gridState, seconds: 8 }),
  }, 'Pixel-Frame gesendet');
  if (res) {
    await refreshStatus();
    await refreshPreview();
  }
}

initGrid();
initPreviewGrid();
if (token) {
  loadModules();
  refreshStatus();
  refreshPreview();
  startPollingLoops();
}
