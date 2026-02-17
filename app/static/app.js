let token = localStorage.getItem('token') || '';
const gridState = Array.from({ length: 8 }, () => Array(32).fill(0));

function authHeaders() {
  return token ? { 'Authorization': `Bearer ${token}` } : {};
}

async function login() {
  const username = document.getElementById('username').value;
  const password = document.getElementById('password').value;
  const res = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password })
  });
  if (!res.ok) {
    document.getElementById('loginStatus').innerText = 'Login fehlgeschlagen';
    return;
  }
  const data = await res.json();
  token = data.access_token;
  localStorage.setItem('token', token);
  document.getElementById('loginStatus').innerText = 'OK';
  loadModules();
}

async function loadModules() {
  const res = await fetch('/api/modules', { headers: authHeaders() });
  if (!res.ok) return;
  const modules = await res.json();
  const container = document.getElementById('modules');
  container.innerHTML = '';
  modules.forEach(m => {
    const row = document.createElement('div');
    row.className = 'module-row';
    row.innerHTML = `
      <strong>${m.name}</strong>
      <label><input type="checkbox" ${m.enabled ? 'checked' : ''} id="en-${m.id}"> aktiv</label>
      <input type="number" id="dur-${m.id}" value="${m.duration_seconds}" min="1">
      <input type="number" id="ord-${m.id}" value="${m.sort_order}">
      <button onclick="saveModule(${m.id}, '${m.key.replace(/'/g, "")}', '${m.name.replace(/'/g, "")}')">Speichern</button>
    `;
    container.appendChild(row);
  });
}

async function saveModule(id, key, name) {
  const payload = {
    enabled: document.getElementById(`en-${id}`).checked,
    duration_seconds: parseInt(document.getElementById(`dur-${id}`).value, 10),
    sort_order: parseInt(document.getElementById(`ord-${id}`).value, 10),
    settings: {}
  };
  await fetch(`/api/modules/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(payload)
  });
  loadModules();
}

async function sendText() {
  await fetch('/api/display/text', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({
      text: document.getElementById('manualText').value,
      seconds: parseInt(document.getElementById('manualSeconds').value, 10)
    })
  });
}

async function setBrightness() {
  await fetch('/api/display/brightness', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ brightness: parseInt(document.getElementById('brightness').value, 10) })
  });
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
  pixels.forEach(p => p.classList.remove('on'));
  for (let y = 0; y < 8; y++) for (let x = 0; x < 32; x++) gridState[y][x] = 0;
}

async function sendGrid() {
  await fetch('/api/display/draw', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ pixels: gridState, seconds: 8 })
  });
}

initGrid();
if (token) loadModules();
