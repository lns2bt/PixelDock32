let token = localStorage.getItem('token') || '';
const gridState = Array.from({ length: 8 }, () => Array(32).fill(0));
let pollTimerStatus = null;
let pollTimerPreview = null;
const moduleCollapseState = {};

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

function transitionControls(moduleId, settings) {
  return `
    <div class="field">
      <label for="set-trans-dir-${moduleId}">Transition Richtung</label>
      <select id="set-trans-dir-${moduleId}">
        <option value="down" ${settings.transition_direction !== 'up' ? 'selected' : ''}>Neu von oben nach unten</option>
        <option value="up" ${settings.transition_direction === 'up' ? 'selected' : ''}>Neu von unten nach oben</option>
      </select>
    </div>
    <div class="field">
      <label for="set-trans-ms-${moduleId}">Transition (ms)</label>
      <input id="set-trans-ms-${moduleId}" type="number" min="0" max="2000" value="${settings.transition_ms ?? 350}" />
    </div>
  `;
}

function applyTextboxPreset(moduleId) {
  const preset = document.getElementById(`set-preset-${moduleId}`).value;
  const presets = {
    welcome: {
      lines: 'HELLO\nPIXELDOCK',
      font: 'small',
      lineSeconds: 2,
      mode: 'static',
      speed: 35,
      transitionMs: 450,
    },
    status: {
      lines: 'WLAN OK\nTEMP OK\nAPI READY',
      font: 'small',
      lineSeconds: 2,
      mode: 'static',
      speed: 35,
      transitionMs: 350,
    },
    alert: {
      lines: 'WARNUNG\nCHECK\nSYSTEM',
      font: 'normal',
      lineSeconds: 1,
      mode: 'static',
      speed: 35,
      transitionMs: 250,
    },
    ticker: {
      lines: 'PIXELDOCK STATUS LIVE',
      font: 'small',
      lineSeconds: 2,
      mode: 'scroll',
      speed: 45,
      transitionMs: 0,
    },
  };

  const cfg = presets[preset];
  if (!cfg) return;
  document.getElementById(`set-lines-${moduleId}`).value = cfg.lines;
  document.getElementById(`set-font-${moduleId}`).value = cfg.font;
  document.getElementById(`set-line-sec-${moduleId}`).value = cfg.lineSeconds;
  document.getElementById(`set-text-mode-${moduleId}`).value = cfg.mode;
  document.getElementById(`set-scroll-speed-${moduleId}`).value = cfg.speed;
  document.getElementById(`set-trans-ms-${moduleId}`).value = cfg.transitionMs;
  toast('Textbox-Preset geladen (bitte speichern)');
}

function moduleSettingsHtml(module) {
  const s = module.settings || {};

  if (module.key === 'clock') {
    return `
      <div class="settings-grid settings-grid-color">
        <div class="field">
          <label for="set-tz-${module.id}">Zeitzone</label>
          <input id="set-tz-${module.id}" value="${s.timezone || 'Europe/Vienna'}" placeholder="Europe/Vienna" />
        </div>
        <div class="field">
          <label>Anzeige</label>
          <label class="check-label"><input type="checkbox" id="set-sec-${module.id}" ${s.show_seconds !== false ? 'checked' : ''}> Sekunden anzeigen</label>
        </div>
        <div class="field">
          <label for="set-font-${module.id}">Schriftgröße</label>
          <select id="set-font-${module.id}">
            <option value="normal" ${s.font_size !== 'small' ? 'selected' : ''}>Normal (5x7)</option>
            <option value="small" ${s.font_size === 'small' ? 'selected' : ''}>Klein (3x5)</option>
          </select>
        </div>
        <div class="field">
          <label for="set-color-${module.id}">Schriftfarbe</label>
          <input id="set-color-${module.id}" type="color" value="${s.color || '#c8e6ff'}" />
        </div>
        <div class="field">
          <label for="set-x-${module.id}">Offset X</label>
          <input id="set-x-${module.id}" type="number" min="-16" max="16" value="${s.x_offset ?? 0}" />
        </div>
        <div class="field">
          <label for="set-y-${module.id}">Offset Y</label>
          <input id="set-y-${module.id}" type="number" min="-4" max="4" value="${s.y_offset ?? 0}" />
        </div>
        <div class="field">
          <label for="set-spacing-${module.id}">Zeichenabstand</label>
          <input id="set-spacing-${module.id}" type="number" min="0" max="4" value="${s.char_spacing ?? 1}" />
        </div>
        <div class="field">
          <label for="set-clock-sec-border-mode-${module.id}">Sekunden-Rand Animation</label>
          <select id="set-clock-sec-border-mode-${module.id}">
            <option value="off" ${!s.seconds_border_mode || s.seconds_border_mode === 'off' ? 'selected' : ''}>Aus</option>
            <option value="linear" ${s.seconds_border_mode === 'linear' ? 'selected' : ''}>Simpel (linear)</option>
            <option value="two_forward_one_back" ${s.seconds_border_mode === 'two_forward_one_back' ? 'selected' : ''}>2 vor, 1 zurück</option>
            <option value="dual_edge" ${s.seconds_border_mode === 'dual_edge' ? 'selected' : ''}>Dual-Edge (von zwei Seiten)</option>
          </select>
        </div>
        <div class="field">
          <label for="set-clock-sec-border-color-${module.id}">Sekunden-Rand Farbe</label>
          <input id="set-clock-sec-border-color-${module.id}" type="color" value="${s.seconds_border_color || '#3cc8ff'}" />
        </div>

      </div>
    `;
  }

  if (module.key === 'btc') {
    return `
      <div class="settings-grid settings-grid-color">
        <div class="field">
          <label for="set-font-${module.id}">Schriftgröße</label>
          <select id="set-font-${module.id}">
            <option value="normal" ${s.font_size !== 'small' ? 'selected' : ''}>Normal (5x7)</option>
            <option value="small" ${s.font_size === 'small' ? 'selected' : ''}>Klein (3x5)</option>
          </select>
        </div>
        <div class="field">
          <label for="set-x-${module.id}">Offset X</label>
          <input id="set-x-${module.id}" type="number" min="-16" max="16" value="${s.x_offset ?? 0}" />
        </div>
        <div class="field">
          <label for="set-y-${module.id}">Offset Y</label>
          <input id="set-y-${module.id}" type="number" min="-4" max="4" value="${s.y_offset ?? 0}" />
        </div>
        <div class="field">
          <label for="set-spacing-${module.id}">Zeichenabstand</label>
          <input id="set-spacing-${module.id}" type="number" min="0" max="4" value="${s.char_spacing ?? 1}" />
        </div>
        <div class="field">
          <label for="set-b-${module.id}">Farbe B</label>
          <input id="set-b-${module.id}" type="color" value="${s.color_b || '#ff8c00'}" />
        </div>
        <div class="field">
          <label for="set-up-${module.id}">Farbe Trend hoch</label>
          <input id="set-up-${module.id}" type="color" value="${s.color_up || '#00c850'}" />
        </div>
        <div class="field">
          <label for="set-down-${module.id}">Farbe Trend runter</label>
          <input id="set-down-${module.id}" type="color" value="${s.color_down || '#e63c3c'}" />
        </div>
        <div class="field">
          <label for="set-flat-${module.id}">Farbe Trend neutral</label>
          <input id="set-flat-${module.id}" type="color" value="${s.color_flat || '#dcdc50'}" />
        </div>
        <div class="field">
          <label for="set-fallback-${module.id}">Farbe Fallback</label>
          <input id="set-fallback-${module.id}" type="color" value="${s.color_fallback || '#9ca3af'}" />
        </div>
        <div class="field">
          <label class="check-label"><input type="checkbox" id="set-btc-block-${module.id}" ${s.show_block_height === true ? 'checked' : ''}> Zweiter Screen: Blockhöhe</label>
        </div>
        <div class="field">
          <label for="set-btc-screen-sec-${module.id}">Screen-Wechsel (Sek.)</label>
          <input id="set-btc-screen-sec-${module.id}" type="number" min="1" max="60" value="${s.screen_seconds ?? 4}" />
        </div>
        ${transitionControls(module.id, s)}
      </div>
    `;
  }

  if (module.key === 'weather') {
    return `
      <div class="settings-grid settings-grid-color">
        <div class="field">
          <label for="set-post-${module.id}">Postleitzahl (Info)</label>
          <input id="set-post-${module.id}" value="${s.postcode || '6020'}" placeholder="6020" />
        </div>
        <div class="field">
          <label for="set-font-${module.id}">Schriftgröße</label>
          <select id="set-font-${module.id}">
            <option value="normal" ${s.font_size !== 'small' ? 'selected' : ''}>Normal (5x7)</option>
            <option value="small" ${s.font_size === 'small' ? 'selected' : ''}>Klein (3x5)</option>
          </select>
        </div>
        <div class="field">
          <label for="set-x-${module.id}">Offset X</label>
          <input id="set-x-${module.id}" type="number" min="-16" max="16" value="${s.x_offset ?? 0}" />
        </div>
        <div class="field">
          <label for="set-y-${module.id}">Offset Y</label>
          <input id="set-y-${module.id}" type="number" min="-4" max="4" value="${s.y_offset ?? 0}" />
        </div>
        <div class="field">
          <label for="set-spacing-${module.id}">Zeichenabstand</label>
          <input id="set-spacing-${module.id}" type="number" min="0" max="4" value="${s.char_spacing ?? 1}" />
        </div>
        <div class="field">
          <label for="set-cold-${module.id}">Farbe kalt</label>
          <input id="set-cold-${module.id}" type="color" value="${s.color_cold || '#3b82f6'}" />
        </div>
        <div class="field">
          <label for="set-warm-${module.id}">Farbe warm</label>
          <input id="set-warm-${module.id}" type="color" value="${s.color_warm || '#f97316'}" />
        </div>
        <div class="field">
          <label for="set-humidity-${module.id}">Farbe Luftfeuchte</label>
          <input id="set-humidity-${module.id}" type="color" value="${s.color_humidity || '#6ed2ff'}" />
        </div>
        <div class="field">
          <label for="set-fallback-${module.id}">Farbe Fallback</label>
          <input id="set-fallback-${module.id}" type="color" value="${s.color_fallback || '#9ca3af'}" />
        </div>
        <div class="field">
          <label for="set-weather-screen-sec-${module.id}">Screen-Wechsel (Sek.)</label>
          <input id="set-weather-screen-sec-${module.id}" type="number" min="1" max="60" value="${s.screen_seconds ?? 4}" />
        </div>
        ${transitionControls(module.id, s)}
      </div>
    `;
  }

  if (module.key === 'textbox') {
    return `
      <div class="settings-grid settings-grid-color">
        <div class="field">
          <label for="set-preset-${module.id}">Preset</label>
          <div class="inline-actions">
            <select id="set-preset-${module.id}">
              <option value="welcome" ${s.preset === 'welcome' ? 'selected' : ''}>Welcome</option>
              <option value="status" ${s.preset === 'status' ? 'selected' : ''}>Status</option>
              <option value="alert" ${s.preset === 'alert' ? 'selected' : ''}>Alert</option>
              <option value="ticker" ${s.preset === 'ticker' ? 'selected' : ''}>Ticker</option>
            </select>
            <button type="button" class="btn btn-secondary" onclick="applyTextboxPreset(${module.id})">Laden</button>
          </div>
        </div>
        <div class="field field-span-2">
          <label for="set-lines-${module.id}">Mehrzeiliger Text (eine Zeile pro Zeile)</label>
          <textarea id="set-lines-${module.id}" rows="4" placeholder="ZEILE 1&#10;ZEILE 2">${s.lines || 'HELLO\nPIXELDOCK'}</textarea>
        </div>
        <div class="field">
          <label for="set-line-sec-${module.id}">Zeilenwechsel (Sek.)</label>
          <input id="set-line-sec-${module.id}" type="number" min="1" max="30" value="${s.line_seconds ?? 2}" />
        </div>
        <div class="field">
          <label for="set-text-mode-${module.id}">Text-Ausgabe</label>
          <select id="set-text-mode-${module.id}">
            <option value="static" ${s.text_mode !== 'scroll' ? 'selected' : ''}>Zeilenweise</option>
            <option value="scroll" ${s.text_mode === 'scroll' ? 'selected' : ''}>Scroll/Ticker</option>
          </select>
        </div>
        <div class="field">
          <label for="set-scroll-speed-${module.id}">Scroll-Speed</label>
          <input id="set-scroll-speed-${module.id}" type="number" min="5" max="120" value="${s.scroll_speed ?? 35}" />
        </div>
        <div class="field">
          <label for="set-font-${module.id}">Schriftgröße</label>
          <select id="set-font-${module.id}">
            <option value="normal" ${s.font_size !== 'small' ? 'selected' : ''}>Normal (5x7)</option>
            <option value="small" ${s.font_size === 'small' ? 'selected' : ''}>Klein (3x5)</option>
          </select>
        </div>
        <div class="field">
          <label for="set-color-${module.id}">Farbe</label>
          <input id="set-color-${module.id}" type="color" value="${s.color || '#f4f4f5'}" />
        </div>
        <div class="field">
          <label for="set-x-${module.id}">Offset X</label>
          <input id="set-x-${module.id}" type="number" min="-16" max="16" value="${s.x_offset ?? 0}" />
        </div>
        <div class="field">
          <label for="set-y-${module.id}">Offset Y</label>
          <input id="set-y-${module.id}" type="number" min="-4" max="4" value="${s.y_offset ?? 0}" />
        </div>
        <div class="field">
          <label for="set-spacing-${module.id}">Zeichenabstand</label>
          <input id="set-spacing-${module.id}" type="number" min="0" max="4" value="${s.char_spacing ?? 1}" />
        </div>
        ${transitionControls(module.id, s)}
      </div>
    `;
  }

  if (module.key === 'bitmap') {
    return `
      <div class="settings-grid settings-grid-color">
        <div class="field field-span-2">
          <label for="set-bitmap-file-${module.id}">Bitmap-Datei (unter app/bitmaps, z. B. .txt/.pbm/.ppm)</label>
          <input id="set-bitmap-file-${module.id}" value="${s.file || 'sample_gradient.ppm'}" placeholder="sample_arrow.txt" />
        </div>
        <div class="field">
          <label for="set-bitmap-dir-${module.id}">Scroll-Richtung</label>
          <select id="set-bitmap-dir-${module.id}">
            <option value="top_to_bottom" ${s.scroll_direction !== 'bottom_to_top' ? 'selected' : ''}>unten → oben</option>
            <option value="bottom_to_top" ${s.scroll_direction === 'bottom_to_top' ? 'selected' : ''}>oben → unten</option>
          </select>
        </div>
        <div class="field">
          <label for="set-bitmap-speed-${module.id}">Scroll-Speed</label>
          <input id="set-bitmap-speed-${module.id}" type="number" min="0.25" max="20" step="0.25" value="${s.scroll_speed ?? 2}" />
        </div>
        <div class="field">
          <label for="set-bitmap-color-${module.id}">Fallback/Solid Farbe</label>
          <input id="set-bitmap-color-${module.id}" type="color" value="${s.color || '#f4f4f5'}" />
        </div>
        <div class="field">
          <label for="set-bitmap-color-mode-${module.id}">Farbmodus</label>
          <select id="set-bitmap-color-mode-${module.id}">
            <option value="bitmap" ${s.color_mode !== 'solid' ? 'selected' : ''}>Bitmap RGB verwenden</option>
            <option value="solid" ${s.color_mode === 'solid' ? 'selected' : ''}>Alles in Solid-Farbe</option>
          </select>
        </div>
        ${transitionControls(module.id, s)}
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
      font_size: document.getElementById(`set-font-${moduleId}`).value,
      color: document.getElementById(`set-color-${moduleId}`).value,
      x_offset: parseInt(document.getElementById(`set-x-${moduleId}`).value, 10) || 0,
      y_offset: parseInt(document.getElementById(`set-y-${moduleId}`).value, 10) || 0,
      char_spacing: (() => { const v = parseInt(document.getElementById(`set-spacing-${moduleId}`).value, 10); return Number.isNaN(v) ? 1 : v; })(),
      seconds_border_mode: document.getElementById(`set-clock-sec-border-mode-${moduleId}`).value,
      seconds_border_color: document.getElementById(`set-clock-sec-border-color-${moduleId}`).value,
    };
  }

  const commonTransition = {
    transition_direction: document.getElementById(`set-trans-dir-${moduleId}`).value,
    transition_ms: parseInt(document.getElementById(`set-trans-ms-${moduleId}`).value, 10) || 350,
  };

  if (moduleKey === 'btc') {
    return {
      font_size: document.getElementById(`set-font-${moduleId}`).value,
      x_offset: parseInt(document.getElementById(`set-x-${moduleId}`).value, 10) || 0,
      y_offset: parseInt(document.getElementById(`set-y-${moduleId}`).value, 10) || 0,
      char_spacing: (() => { const v = parseInt(document.getElementById(`set-spacing-${moduleId}`).value, 10); return Number.isNaN(v) ? 1 : v; })(),
      color_b: document.getElementById(`set-b-${moduleId}`).value,
      color_up: document.getElementById(`set-up-${moduleId}`).value,
      color_down: document.getElementById(`set-down-${moduleId}`).value,
      color_flat: document.getElementById(`set-flat-${moduleId}`).value,
      color_fallback: document.getElementById(`set-fallback-${moduleId}`).value,
      show_block_height: document.getElementById(`set-btc-block-${moduleId}`).checked,
      screen_seconds: parseInt(document.getElementById(`set-btc-screen-sec-${moduleId}`).value, 10) || 4,
      ...commonTransition,
    };
  }

  if (moduleKey === 'weather') {
    return {
      postcode: document.getElementById(`set-post-${moduleId}`).value.trim() || '6020',
      font_size: document.getElementById(`set-font-${moduleId}`).value,
      x_offset: parseInt(document.getElementById(`set-x-${moduleId}`).value, 10) || 0,
      y_offset: parseInt(document.getElementById(`set-y-${moduleId}`).value, 10) || 0,
      char_spacing: (() => { const v = parseInt(document.getElementById(`set-spacing-${moduleId}`).value, 10); return Number.isNaN(v) ? 1 : v; })(),
      color_cold: document.getElementById(`set-cold-${moduleId}`).value,
      color_warm: document.getElementById(`set-warm-${moduleId}`).value,
      color_humidity: document.getElementById(`set-humidity-${moduleId}`).value,
      color_fallback: document.getElementById(`set-fallback-${moduleId}`).value,
      screen_seconds: parseInt(document.getElementById(`set-weather-screen-sec-${moduleId}`).value, 10) || 4,
      ...commonTransition,
    };
  }

  if (moduleKey === 'textbox') {
    return {
      lines: document.getElementById(`set-lines-${moduleId}`).value,
      line_seconds: parseInt(document.getElementById(`set-line-sec-${moduleId}`).value, 10) || 2,
      text_mode: document.getElementById(`set-text-mode-${moduleId}`).value,
      scroll_speed: parseInt(document.getElementById(`set-scroll-speed-${moduleId}`).value, 10) || 35,
      preset: document.getElementById(`set-preset-${moduleId}`).value,
      font_size: document.getElementById(`set-font-${moduleId}`).value,
      color: document.getElementById(`set-color-${moduleId}`).value,
      x_offset: parseInt(document.getElementById(`set-x-${moduleId}`).value, 10) || 0,
      y_offset: parseInt(document.getElementById(`set-y-${moduleId}`).value, 10) || 0,
      char_spacing: (() => { const v = parseInt(document.getElementById(`set-spacing-${moduleId}`).value, 10); return Number.isNaN(v) ? 1 : v; })(),
      ...commonTransition,
    };
  }

  if (moduleKey === 'bitmap') {
    return {
      file: document.getElementById(`set-bitmap-file-${moduleId}`).value.trim(),
      scroll_direction: document.getElementById(`set-bitmap-dir-${moduleId}`).value,
      scroll_speed: parseFloat(document.getElementById(`set-bitmap-speed-${moduleId}`).value) || 2,
      color: document.getElementById(`set-bitmap-color-${moduleId}`).value,
      color_mode: document.getElementById(`set-bitmap-color-mode-${moduleId}`).value,
      ...commonTransition,
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
    if (typeof moduleCollapseState[m.id] === 'undefined') {
      moduleCollapseState[m.id] = !m.enabled;
    }

    const row = document.createElement('div');
    const isCollapsed = !!moduleCollapseState[m.id];
    row.className = `module-row ${isCollapsed ? 'collapsed' : ''}`;
    row.innerHTML = `
      <div class="module-main">
        <button class="module-toggle" type="button" onclick="toggleModuleCard(${m.id})" aria-label="Modul ein- oder ausklappen">
          <span id="arrow-${m.id}" class="module-arrow ${isCollapsed ? '' : 'open'}">▸</span>
        </button>
        <div class="field module-name-wrap">
          <label>Modul</label>
          <div class="module-name">${m.name}</div>
          <span class="module-key">${m.key}</span>
        </div>
        <div class="field">
          <label>Aktiv</label>
          <label class="check-label"><input type="checkbox" ${m.enabled ? 'checked' : ''} id="en-${m.id}" onchange="toggleModuleEnabled(${m.id}, '${m.key}')"> aktiv</label>
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
      </div>
      <div class="module-settings" id="settings-${m.id}">
        <label class="settings-title">Moduleinstellungen</label>
        ${moduleSettingsHtml(m)}
      </div>
    `;
    container.appendChild(row);
  });
}

function toggleModuleCard(moduleId) {
  moduleCollapseState[moduleId] = !moduleCollapseState[moduleId];
  const row = document.querySelector(`#settings-${moduleId}`)?.closest('.module-row');
  if (!row) return;

  row.classList.toggle('collapsed', moduleCollapseState[moduleId]);
  const arrow = document.getElementById(`arrow-${moduleId}`);
  if (arrow) arrow.classList.toggle('open', !moduleCollapseState[moduleId]);
}

async function toggleModuleEnabled(moduleId, moduleKey) {
  const enabled = document.getElementById(`en-${moduleId}`).checked;

  const payload = {
    enabled,
    duration_seconds: parseInt(document.getElementById(`dur-${moduleId}`).value, 10) || 8,
    sort_order: parseInt(document.getElementById(`ord-${moduleId}`).value, 10) || 0,
    settings: collectModuleSettings({ id: moduleId, key: moduleKey }),
  };

  const res = await apiRequest(
    `/api/modules/${moduleId}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
    enabled ? 'Modul aktiviert' : 'Modul deaktiviert',
  );

  if (!res) {
    document.getElementById(`en-${moduleId}`).checked = !enabled;
    return;
  }

  moduleCollapseState[moduleId] = !enabled;
  const row = document.querySelector(`#settings-${moduleId}`)?.closest('.module-row');
  if (row) row.classList.toggle('collapsed', !enabled);
  const arrow = document.getElementById(`arrow-${moduleId}`);
  if (arrow) arrow.classList.toggle('open', enabled);

  await Promise.all([refreshStatus(), refreshPreview()]);
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
    body: JSON.stringify({
      text,
      seconds,
      font_size: document.getElementById('manualFontSize').value,
      color: document.getElementById('manualColor').value,
      x_offset: parseInt(document.getElementById('manualOffsetX').value, 10) || 0,
      y_offset: parseInt(document.getElementById('manualOffsetY').value, 10) || 0,
    }),
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
    : `${formatTs(data.data.weather_updated_at)} (${data.data.weather_source || 'api'})`;
  document.getElementById('statusDhtLevel').innerText = data.data.dht_gpio_level === null ? '-' : `${data.data.dht_gpio_level}`;
  document.getElementById('statusDhtRead').innerText = data.data.dht_error
    ? `Fehler (${data.data.dht_error.slice(0, 24)}...)`
    : `${formatTs(data.data.dht_updated_at)} / ${data.data.dht_last_duration_ms ?? '-'}ms`;
  await refreshDhtDebug();
}

async function refreshDhtDebug() {
  const data = await apiRequest('/api/debug/dht');
  if (!data) return;
  const el = document.getElementById('dhtDebugInfo');
  if (!el) return;
  el.innerText = JSON.stringify(data, null, 2);
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
    `x=${m.x}, y=${m.y} -> panel=${m.panel_index}, rotation=${m.panel_rotation}°, local=(${m.local_x},${m.local_y}), pixel_in_panel=${m.pixel_in_panel}, led_index=${m.index}, serpentine_flip=${m.serpentine_flipped}`;
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
  refreshDhtDebug();
  startPollingLoops();
}
