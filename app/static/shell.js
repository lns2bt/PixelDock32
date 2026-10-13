/* Shared shell: passive preview. Brightness writes occur only on user action. */
(() => {
  'use strict';
  const token = localStorage.getItem('token');
  if (!token && location.pathname !== '/login') { location.replace('/login'); return; }
  const api = async (path, options = {}) => {
    const response = await fetch(path, { ...options, headers: { Authorization: `Bearer ${token}`, ...(options.body && typeof options.body === 'string' ? { 'Content-Type': 'application/json' } : {}), ...options.headers }, signal: options.signal || AbortSignal.timeout(10000) });
    if (response.status === 401) { localStorage.removeItem('token'); location.replace('/login'); throw new Error('Bitte neu anmelden'); }
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `Anfrage fehlgeschlagen (${response.status})`);
    return data;
  };
  let toastTimer;
  function toast(message, error = false) {
    let node = document.querySelector('.retro-toast');
    if (!node) { node = document.createElement('div'); node.className = 'retro-toast'; node.setAttribute('role', 'status'); document.body.append(node); }
    node.textContent = message; node.classList.toggle('error', error); node.hidden = false;
    clearTimeout(toastTimer); toastTimer = setTimeout(() => { node.hidden = true; }, error ? 7000 : 3000);
  }
  function matrix(canvas, pixels, grid = false, ghost = null) {
    const ctx = canvas.getContext('2d'), w = canvas.width / 32, h = canvas.height / 8;
    ctx.fillStyle = '#070a11'; ctx.fillRect(0, 0, canvas.width, canvas.height);
    for (let i = 0; i < 256; i++) {
      const value = pixels[i] || 0;
      ctx.fillStyle = value ? '#' + value.toString(16).padStart(6, '0') : '#121827';
      const x = i % 32 * w, y = Math.floor(i / 32) * h;
      if (!value && ghost && ghost[i]) { ctx.fillStyle = '#' + ghost[i].toString(16).padStart(6, '0'); ctx.globalAlpha = .2; }
      ctx.fillRect(x + (grid ? 1 : 1.5), y + (grid ? 1 : 1.5), w - (grid ? 2 : 3), h - (grid ? 2 : 3)); ctx.globalAlpha = 1;
    }
  }
  window.PixelDock = { api, toast, matrix };
  document.querySelector('.top-nav')?.remove();
  const header = document.createElement('header'); header.className = 'live-header';
  header.innerHTML = `<div class="live-header-inner"><div class="live-top"><a class="pixel-brand" href="/">PIXEL<span>DOCK</span><small> /32</small></a><span class="live-label"><i class="live-dot" aria-hidden="true"></i><span id="previewConnection">VERBINDE …</span></span></div><div class="live-matrix"><canvas id="headerMatrix" width="512" height="128" aria-label="Live-Vorschau der gerenderten LED-Anzeige"></canvas><div class="live-caption">GERENDERTES BILD<strong id="onAir">—</strong>32 × 8 · 256 Pixel</div></div><nav class="retro-nav" aria-label="Hauptnavigation"><a href="/">Dashboard</a><a href="/modules">Playlist</a><a href="/studio">Pixel-Studio</a><a href="/advanced">Erweitert</a><button id="shellLogout" type="button">Abmelden</button></nav></div>`;
  document.body.prepend(header);
  window.PixelDockBrightness?.mount({api,toast,header});
  document.querySelectorAll('.retro-nav a').forEach(link => {
    const active = link.getAttribute('href') === location.pathname || (link.getAttribute('href') === '/advanced' && ['/debug','/mapping','/tools'].includes(location.pathname));
    link.classList.toggle('active', active); if (active) link.setAttribute('aria-current', 'page');
  });
  document.getElementById('shellLogout').onclick = () => { localStorage.removeItem('token'); location.href = '/login'; };
  let lastStatus = 0, hardwareOnline = true, moduleNames = {}, namesUpdated = 0;
  const canvas = document.getElementById('headerMatrix');
  async function poll() {
    if (!document.hidden) {
      try {
        const preview = await api('/api/debug/preview');
        const pixels = preview.frame.flat().map((lit, i) => { const color = preview.colors[Math.floor(i / 32)][i % 32]; return lit ? color ? (color[0] << 16) | (color[1] << 8) | color[2] : 0x505050 : 0; });
        matrix(canvas, pixels); document.querySelector('.live-dot').classList.toggle('online', hardwareOnline); document.getElementById('previewConnection').textContent = hardwareOnline ? 'LIVE · VORSCHAU' : 'VORSCHAU · UNO OFFLINE';
        if (Date.now() - lastStatus > 5000) {
          const status = await api('/api/debug/status'); lastStatus = Date.now();
          hardwareOnline = status.led_transport?.transport !== 'serial' || !!status.led_transport?.serial?.connected;
          if (Date.now() - namesUpdated > 30000) {
            const rows = await api('/api/modules'); moduleNames = Object.fromEntries(rows.map(row => [row.key,row.name])); namesUpdated = Date.now();
          }
          document.getElementById('onAir').textContent = status.display.last_source === 'module' ? moduleNames[status.display.last_module] || 'Playlist' : status.display.last_source === 'manual' ? 'Nachricht / Zeichnung' : 'Testmuster';
          window.dispatchEvent(new CustomEvent('pixeldock-status', { detail: status }));
        }
      } catch (_) { document.querySelector('.live-dot').classList.remove('online'); document.getElementById('previewConnection').textContent = 'VERBINDUNG UNTERBROCHEN'; }
    }
    setTimeout(poll, 200); // No overlapping requests; pause while the tab is hidden.
  }
  if (token) poll();
})();
