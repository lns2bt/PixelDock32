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
  // LED matrix renderer. grid=true keeps crisp squares for editors; otherwise
  // pixels are drawn as round LEDs with a soft glow, like the real panel.
  function matrix(canvas, pixels, grid = false, ghost = null) {
    const ctx = canvas.getContext('2d'), w = canvas.width / 32, h = canvas.height / 8;
    ctx.globalAlpha = 1; ctx.shadowBlur = 0;
    ctx.fillStyle = grid ? '#070a11' : '#04060b'; ctx.fillRect(0, 0, canvas.width, canvas.height);
    if (grid) {
      for (let i = 0; i < 256; i++) {
        const value = pixels[i] || 0;
        ctx.fillStyle = value ? '#' + value.toString(16).padStart(6, '0') : '#121827';
        const x = i % 32 * w, y = Math.floor(i / 32) * h;
        if (!value && ghost && ghost[i]) { ctx.fillStyle = '#' + ghost[i].toString(16).padStart(6, '0'); ctx.globalAlpha = .2; }
        ctx.fillRect(x + 1, y + 1, w - 2, h - 2); ctx.globalAlpha = 1;
      }
      return;
    }
    const r = Math.min(w, h) * .36;
    for (let i = 0; i < 256; i++) {
      const value = pixels[i] || 0, cx = (i % 32 + .5) * w, cy = (Math.floor(i / 32) + .5) * h;
      ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2);
      if (!value) {
        ctx.shadowBlur = 0;
        if (ghost && ghost[i]) { ctx.fillStyle = '#' + ghost[i].toString(16).padStart(6, '0'); ctx.globalAlpha = .2; }
        else ctx.fillStyle = '#121828';
        ctx.fill(); ctx.globalAlpha = 1; continue;
      }
      const color = '#' + value.toString(16).padStart(6, '0');
      // Lift dim colours slightly so the preview stays readable on screens.
      ctx.fillStyle = color; ctx.shadowColor = color; ctx.shadowBlur = w * .55; ctx.fill();
    }
    ctx.shadowBlur = 0;
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
  const NAV = [
    ['/', 'Home', '⌂'], ['/modules', 'Playlist', '☰'], ['/time-stage', 'Clock', '◷'],
    ['/weather', 'Weather', '☁\uFE0E'], ['/bitcoin', 'Bitcoin', '₿'], ['/studio', 'Studio', '✎\uFE0E'], ['/advanced', 'Advanced', '⛭'],
  ];
  const navLink = ([href, label, icon]) => `<a href="${href}"><span class="nav-icon" aria-hidden="true">${icon}</span>${label}</a>`;
  const header = document.createElement('header'); header.className = 'live-header';
  header.innerHTML = `<div class="live-header-inner"><div class="live-top">
      <a class="pixel-brand" href="/" aria-label="PixelDock home">PIXEL<span>DOCK</span><small>/32</small></a>
      <small id="activeVersion" class="version-tag">…</small>
      <nav class="retro-nav desktop-nav" aria-label="Main navigation">${NAV.map(navLink).join('')}</nav>
      <div class="shell-actions">
        <button id="headerMatrixToggle" type="button" class="ghost icon-button" aria-controls="headerMatrixPanel" aria-expanded="true" aria-label="Collapse live matrix"><span aria-hidden="true">▴</span></button>
        <button id="shellLogout" type="button" class="ghost icon-button logout-action" title="Log out" aria-label="Log out">⏻</button>
      </div></div>
    <div class="live-matrix" id="headerMatrixPanel"><canvas id="headerMatrix" width="640" height="160" aria-label="Live preview of the rendered LED display"></canvas>
      <div class="live-caption"><p class="kicker">On air <span class="live-label" title="Connection to the display"><i class="live-dot" aria-hidden="true"></i><span id="previewConnection" class="label-text">CONNECTING</span></span></p><strong id="onAir" class="live-on-air">—</strong><div class="progress" aria-hidden="true"><i id="onAirProgress"></i></div></div></div></div>`;
  document.body.prepend(header);
  // Mobile: bottom tab bar plus a "more" sheet for the remaining pages.
  const tabbar = document.createElement('nav'); tabbar.className = 'tabbar'; tabbar.setAttribute('aria-label', 'Main navigation');
  tabbar.innerHTML = NAV.slice(0, 3).map(navLink).join('') + navLink(NAV[5]) + '<button type="button" id="moreButton" aria-haspopup="dialog" aria-expanded="false"><span class="nav-icon" aria-hidden="true">⋯</span>More</button>';
  document.body.append(tabbar);
  const backdrop = document.createElement('div'); backdrop.className = 'sheet-backdrop'; backdrop.hidden = true;
  const sheet = document.createElement('div'); sheet.className = 'sheet'; sheet.hidden = true; sheet.setAttribute('role', 'dialog'); sheet.setAttribute('aria-label', 'More pages');
  sheet.innerHTML = [NAV[3], NAV[4], NAV[6]].map(navLink).join('') + '<button type="button" class="logout-action"><span class="nav-icon" aria-hidden="true">⏻</span>Log out</button><p class="sheet-meta" data-version></p>';
  document.body.append(backdrop, sheet);
  const moreButton = tabbar.querySelector('#moreButton');
  const setSheet = open => { sheet.hidden = backdrop.hidden = !open; moreButton.setAttribute('aria-expanded', String(open)); };
  moreButton.onclick = () => setSheet(sheet.hidden);
  backdrop.onclick = () => setSheet(false);
  document.addEventListener('keydown', event => { if (event.key === 'Escape') setSheet(false); });
  const syncHeaderHeight = () => document.documentElement.style.setProperty('--header-h', header.offsetHeight + 'px');
  new ResizeObserver(syncHeaderHeight).observe(header);
  const versionHint = header.querySelector('#activeVersion');
  fetch('/api/version', {cache:'no-store'}).then(response => {
    if (!response.ok) throw new Error('Version unavailable');
    return response.json();
  }).then(data => {
    versionHint.textContent = `v${data.version}`; versionHint.title = 'Running server version';
    sheet.querySelector('[data-version]').textContent = `PixelDock v${data.version}`;
  }).catch(() => { versionHint.textContent = 'Version unavailable'; });
  const matrixToggle = document.getElementById('headerMatrixToggle');
  let matrixExpanded = true;
  try { matrixExpanded = localStorage.getItem('pixeldock.matrixExpanded') !== 'false'; } catch (_) {}
  function syncMatrixVisibility() {
    document.getElementById('headerMatrixPanel').hidden = !matrixExpanded;
    header.classList.toggle('matrix-collapsed', !matrixExpanded);
    matrixToggle.setAttribute('aria-expanded', String(matrixExpanded));
    matrixToggle.setAttribute('aria-label', `${matrixExpanded ? 'Collapse' : 'Expand'} live matrix`);
    matrixToggle.firstElementChild.textContent = matrixExpanded ? '▴' : '▾';
  }
  syncMatrixVisibility();
  matrixToggle.onclick = () => {
    matrixExpanded = !matrixExpanded; syncMatrixVisibility();
    try { localStorage.setItem('pixeldock.matrixExpanded', String(matrixExpanded)); } catch (_) {}
  };
  window.PixelDockBrightness?.mount({api,toast,header});
  const actions = header.querySelector('.shell-actions');
  const brightnessTrigger = header.querySelector('.brightness-trigger');
  if (brightnessTrigger) actions.insertBefore(brightnessTrigger, matrixToggle);
  const sleepButton = document.createElement('button'); sleepButton.type = 'button'; sleepButton.id = 'shellSleep';
  sleepButton.textContent = '☾'; sleepButton.disabled = true; sleepButton.setAttribute('aria-label','Toggle sleep mode');
  sleepButton.setAttribute('aria-pressed','false'); actions.insertBefore(sleepButton, matrixToggle);
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
  const here = location.pathname;
  document.querySelectorAll('.retro-nav a, .tabbar a, .sheet a').forEach(link => {
    const href = link.getAttribute('href');
    const active = href === here || (href === '/advanced' && ['/debug','/mapping','/tools'].includes(here));
    link.classList.toggle('active', active); if (active) link.setAttribute('aria-current', 'page');
  });
  if ([NAV[3], NAV[4], NAV[6]].some(([href]) => href === here || (href === '/advanced' && ['/debug','/mapping','/tools'].includes(here)))) moreButton.classList.add('active');
  document.querySelectorAll('.logout-action').forEach(button => button.onclick = () => { localStorage.removeItem('token'); location.href = '/login'; });
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
          const slot = status.display.playlist, bar = document.getElementById('onAirProgress');
          if (bar) {
            // Glide linearly to where the slot will be at the next status poll.
            const now = status.display.last_source === 'module' && slot?.duration_s ? 100 * slot.elapsed_s / slot.duration_s : 0;
            const next = status.display.last_source === 'module' && slot?.duration_s ? Math.min(100, 100 * (slot.elapsed_s + 5) / slot.duration_s) : 0;
            if (now < (parseFloat(bar.style.width) || 0) - 1) { bar.style.transition = 'none'; bar.style.width = now + '%'; void bar.offsetWidth; }
            bar.style.transition = 'width 5s linear'; bar.style.width = next + '%';
          }
          window.dispatchEvent(new CustomEvent('pixeldock-status', { detail: status }));
        }
      } catch (_) { document.querySelector('.live-dot').classList.remove('online'); document.getElementById('previewConnection').textContent = 'CONNECTION INTERRUPTED'; }
    }
    setTimeout(poll, matrixExpanded && !document.hidden ? 200 : 1000); // No pixel polling for a collapsed matrix.
  }
  if (token) poll();
})();
