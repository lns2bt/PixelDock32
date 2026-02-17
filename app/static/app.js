let token = localStorage.getItem('token') || '';
const gridState = Array.from({ length: 8 }, () => Array(32).fill(0));

function authHeaders() {
  return token ? { 'Authorization': `Bearer ${token}` } : {};
}

function toast(message, isError = false) {
  const el = document.getElementById('toast');
  el.innerText = message;
  el.style.background = isError ? '#8b0000' : '#111';
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
      }
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

async function login() {
  const username = document.getElementById('username').value;
  const password = document.getElementById('password').value;
  const data = await apiRequest('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password })
  }, 'Login erfolgreich');

  if (!data?.access_token) {
    document.getElementById('loginStatus').innerText = 'Login fehlgeschlagen';
    return;
  }
  token = data.access_token;
  localStorage.setItem('token', token);
  document.getElementById('loginStatus').innerText = 'OK';
  await Promise.all([loadModules(), refreshStatus()]);
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
      <strong>${m.name}</strong>
      <label><input type="checkbox" ${m.enabled ? 'checked' : ''} id="en-${m.id}"> aktiv</label>
      <input type="number" id="dur-${m.id}" value="${m.duration_seconds}" min="1">
      <input type="number" id="ord-${m.id}" value="${m.sort_order}">
      <button onclick="saveModule(${m.id})">Speichern</button>
    `;
    container.appendChild(row);
  });
}

async function saveModule(id) {
  const duration = parseInt(document.getElementById(`dur-${id}`).value, 10);
  const sortOrder = parseInt(document.getElementById(`ord-${id}`).value, 10);
  if (!Number.isInteger(duration) || duration < 1) {
    toast('Dauer muss >= 1 sein', true);
    return;
  }
  if (!Number.isInteger(sortOrder)) {
    toast('Reihenfolge muss Zahl sein', true);
    return;
  }

  const payload = {
    enabled: document.getElementById(`en-${id}`).checked,
    duration_seconds: duration,
    sort_order: sortOrder,
    settings: {}
  };

  const res = await apiRequest(`/api/modules/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  }, 'Modul gespeichert');
  if (res) {
    await Promise.all([loadModules(), refreshStatus()]);
  }
}

async function sendText() {
  const text = document.getElementById('manualText').value;
  const seconds = parseInt(document.getElementById('manualSeconds').value, 10);
  const res = await apiRequest('/api/display/text', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, seconds })
  }, 'Text gesendet');
  if (res) await refreshStatus();
}

async function setBrightness() {
  const brightness = parseInt(document.getElementById('brightness').value, 10);
  const res = await apiRequest('/api/display/brightness', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ brightness })
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
    body: JSON.stringify(payload)
  }, 'Debug-Pattern gestartet');
  if (res) await refreshStatus();
}

async function stopDebugPattern() {
  const res = await apiRequest('/api/debug/pattern', { method: 'DELETE' }, 'Debug-Pattern gestoppt');
  if (res) await refreshStatus();
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

function initGrid() {
  const grid = document.getElementById('grid');
  for (let y = 0; y < 8; y++) {
    for (let x = 0; x < 32; x++) {
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
  for (let y = 0; y < 8; y++) {
    for (let x = 0; x < 32; x++) {
      gridState[y][x] = 0;
    }
  }
}

async function sendGrid() {
  const res = await apiRequest('/api/display/draw', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pixels: gridState, seconds: 8 })
  }, 'Pixel-Frame gesendet');
  if (res) await refreshStatus();
}

initGrid();
refreshStatus();
if (token) {
  loadModules();
  setInterval(refreshStatus, 5000);
}
