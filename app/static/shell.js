/* Shared shell: passive preview. Brightness writes occur only on user action. */
(() => {
  'use strict';
  const token = localStorage.getItem('token');
  if (!token && location.pathname !== '/login') { location.replace('/login'); return; }
  const api = async (path, options = {}) => {
    const response = await fetch(path, { ...options, headers: { Authorization: `Bearer ${token}`, ...(options.body && typeof options.body === 'string' ? { 'Content-Type': 'application/json' } : {}), ...options.headers }, signal: options.signal || AbortSignal.timeout(10000) });
    if (response.status === 401) { localStorage.removeItem('token'); location.replace('/login'); throw new Error('Please register again'); }
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `Request failed (${response.status})`);
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
  const bitcoinTimings = new Map();
  function bitcoinDuration(row) {
    const key = JSON.stringify([row.id, row.settings || {}]);
    if (!bitcoinTimings.has(key)) {
      const request = api('/api/bitcoin/duration', {method:'POST', body:JSON.stringify({settings:row.settings || {}, module_id:row.id})});
      bitcoinTimings.set(key, request);
      request.catch(() => { if (bitcoinTimings.get(key) === request) bitcoinTimings.delete(key); });
    }
    return bitcoinTimings.get(key);
  }
  function bitcoinDurationText(timing) {
    const seconds = Number(timing.duration_seconds ?? timing.duration);
    return Number.isFinite(seconds) ? `Automatic · approx. ${seconds.toLocaleString('en-GB', {maximumFractionDigits:1})} s` : 'Automatic duration';
  }
  const weatherTimings = new Map();
  function weatherDuration(row) {
    const key=JSON.stringify([row.id,row.settings||{}]);
    if(!weatherTimings.has(key)) {
      const request=api('/api/weather/duration',{method:'POST',body:JSON.stringify({module_id:row.id,settings:row.settings||{}})});
      weatherTimings.set(key,request);
      request.catch(()=>{if(weatherTimings.get(key)===request)weatherTimings.delete(key);});
    }
    return weatherTimings.get(key);
  }
  window.PixelDock = { api, toast, matrix, bitcoinDuration, bitcoinDurationText, weatherDuration };
  document.querySelector('.top-nav')?.remove();
  const header = document.createElement('header'); header.className = 'live-header';
  header.innerHTML = `<div class="live-header-inner"><div class="live-top"><a class="pixel-brand" href="/">PIXEL<span>DOCK</span><small> /32</small></a><span class="live-label"><i class="live-dot" aria-hidden="true"></i><span id="previewConnection">CONNECTING …</span></span><strong id="onAir" class="live-on-air">—</strong><button id="headerMatrixToggle" type="button" aria-controls="headerMatrixPanel" aria-expanded="true" aria-label="Collapse live matrix"><span aria-hidden="true">▴</span></button></div><div class="live-matrix" id="headerMatrixPanel"><canvas id="headerMatrix" width="512" height="128" aria-label="Live preview of the rendered LED display"></canvas><div class="live-caption">RENDERED FRAME<br>32 × 8 · 256 pixels</div></div><nav class="retro-nav" aria-label="Main navigation"><a href="/">Dashboard</a><a href="/modules">Playlist</a><a href="/studio">Pixel-Studio</a><a href="/advanced">Advanced</a><button id="shellLogout" type="button">Log out</button></nav></div>`;
  document.body.prepend(header);
  const versionHint = document.createElement('small');
  versionHint.id = 'activeVersion'; versionHint.className = 'muted';
  versionHint.textContent = 'Version …';
  header.querySelector('.retro-nav').append(versionHint);
  fetch('/api/version', {cache:'no-store'}).then(response => {
    if (!response.ok) throw new Error('Version unavailable');
    return response.json();
  }).then(data => { versionHint.textContent = `v${data.version}`; versionHint.title = 'Running server version'; })
    .catch(() => { versionHint.textContent = 'Version unavailable'; });
  const matrixToggle = document.getElementById('headerMatrixToggle');
  let matrixExpanded = true;
  try { matrixExpanded = localStorage.getItem('pixeldock.matrixExpanded') !== 'false'; } catch (_) {}
  function syncMatrixVisibility() {
    document.getElementById('headerMatrixPanel').hidden = !matrixExpanded;
    header.classList.toggle('matrix-collapsed', !matrixExpanded);
    matrixToggle.setAttribute('aria-expanded', String(matrixExpanded));
    matrixToggle.setAttribute('aria-label', `Live matrix ${matrixExpanded ? 'collapse' : 'expand'}`);
    matrixToggle.firstElementChild.textContent = matrixExpanded ? '▴' : '▾';
  }
  syncMatrixVisibility();
  matrixToggle.onclick = () => {
    matrixExpanded = !matrixExpanded; syncMatrixVisibility();
    try { localStorage.setItem('pixeldock.matrixExpanded', String(matrixExpanded)); } catch (_) {}
  };
  const stageNav = document.createElement('a'); stageNav.href = '/time-stage'; stageNav.textContent = 'Time-Stage';
  header.querySelector('.retro-nav').insertBefore(stageNav, header.querySelector('[href="/studio"]'));
  const bitcoinNav = document.createElement('a'); bitcoinNav.href='/bitcoin'; bitcoinNav.textContent='Bitcoin';
  header.querySelector('.retro-nav').insertBefore(bitcoinNav,header.querySelector('[href="/studio"]'));
  const weatherNav=document.createElement('a');weatherNav.href='/weather';weatherNav.textContent='Weather';
  header.querySelector('.retro-nav').insertBefore(weatherNav,header.querySelector('[href="/studio"]'));
  window.PixelDockBrightness?.mount({api,toast,header});
  const sleepButton = document.createElement('button'); sleepButton.type = 'button'; sleepButton.id = 'shellSleep';
  sleepButton.textContent = '☾'; sleepButton.disabled = true; sleepButton.setAttribute('aria-label','Toggle sleep mode');
  sleepButton.setAttribute('aria-pressed','false'); header.querySelector('.live-top').append(sleepButton);
  let sleepActive = false;
  sleepButton.onclick = async () => {
    if (sleepActive && !confirm('Turn off sleep mode now? The normal brightness and playlist become active again.')) return;
    sleepButton.disabled = true;
    try {
      const result = await api('/api/time-stage/sleep',{method:'POST',body:JSON.stringify({mode:sleepActive?'wake':'sleep'})});
      const until = result.sleep?.until;
      const zone = result.timezone || 'UTC';
      toast(`${result.sleep?.active ? 'Sleep' : 'Awake'} override${until ? ' until '+new Date(until).toLocaleString('en-GB',{timeZone:zone})+' · '+zone : ''}. Then automatic mode.`);
      lastStatus = 0;
    } catch (error) {toast(error.message,true);} finally {sleepButton.disabled=false;}
  };
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
        if (matrixExpanded) {
          const preview = await api('/api/debug/preview');
          const pixels = preview.frame.flat().map((lit, i) => { const color = preview.colors[Math.floor(i / 32)][i % 32]; return lit ? color ? (color[0] << 16) | (color[1] << 8) | color[2] : 0x505050 : 0; });
          matrix(canvas, pixels);
        }
        if (Date.now() - lastStatus > 5000) {
          const status = await api('/api/debug/status'); lastStatus = Date.now();
          hardwareOnline = status.led_transport?.transport !== 'serial' || !!status.led_transport?.serial?.connected;
          document.querySelector('.live-dot').classList.toggle('online', hardwareOnline);
          document.getElementById('previewConnection').textContent = hardwareOnline ? 'LIVE · PREVIEW' : 'PREVIEW · UNO OFFLINE';
          if (Date.now() - namesUpdated > 30000) {
            const rows = await api('/api/modules'); moduleNames = Object.fromEntries(rows.map(row => [row.key,row.name])); namesUpdated = Date.now();
          }
          const stage = status.display.time_stage;
          if (stage?.sleep) {
            sleepActive = stage.sleep.active; sleepButton.disabled = false;
            sleepButton.setAttribute('aria-pressed',String(sleepActive));
            sleepButton.title = `${sleepActive?'Sleep mode':'Awake'} · ${stage.sleep.mode==='auto'?'Automatic':'Manual'}${stage.sleep.until?' until '+new Date(stage.sleep.until).toLocaleString('en-GB',{timeZone:stage.timezone || 'UTC'}):''} · ${stage.timezone || 'UTC'}`;
          }
          document.getElementById('onAir').textContent = status.display.last_source === 'module' ? moduleNames[status.display.last_module] || 'Playlist' : status.display.last_source === 'manual' ? 'Message/drawing' : status.display.last_source === 'bitcoin-preview' ? 'Bitcoin · LED Preview' : status.display.last_source === 'weather-preview' ? 'Weather · LED preview' : status.display.last_source === 'time-stage-preview' ? 'Time Stage · LED preview' : status.display.last_source === 'sleep' ? 'Time-Stage · Sleep mode' : status.display.last_source.startsWith('time-stage') ? 'Time-Stage' : status.display.last_source === 'idle' ? 'Pause' : 'Test pattern';
          window.dispatchEvent(new CustomEvent('pixeldock-status', { detail: status }));
        }
      } catch (_) { document.querySelector('.live-dot').classList.remove('online'); document.getElementById('previewConnection').textContent = 'CONNECTION INTERRUPTED'; }
    }
    setTimeout(poll, matrixExpanded && !document.hidden ? 200 : 1000); // No pixel polling for a collapsed matrix.
  }
  if (token) poll();
})();
