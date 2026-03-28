let token = localStorage.getItem('token') || '';
const gridState = Array.from({ length: 8 }, () => Array(32).fill(0));
let pollTimerStatus = null;
let pollTimerPreview = null;
const moduleCollapseState = {};
const serialPingHistory = [];
const serialStateHistory = [];
let ledDebugRefreshInFlight = null;
let ledDebugAutoPollTimer = null;
const PANEL_WIDTH = 8;
const PANEL_HEIGHT = 8;
const MAX_PANEL_COUNT = 4;
const LED_MATRIX_WIDTH = PANEL_WIDTH * MAX_PANEL_COUNT;
const LED_MATRIX_HEIGHT = PANEL_HEIGHT;
const LED_MATRIX_TOTAL_PIXELS = LED_MATRIX_WIDTH * LED_MATRIX_HEIGHT;
const ASSIST_SCAN_MODES = ['row_ltr', 'row_serpentine', 'col_ttb', 'col_serpentine'];
const TOAST_DURATION_MS = {
  success: 2400,
  error: 7000,
};

let toastHideTimer = null;

const mappingAssist = {
  active: false,
  cursor: 0,
  observations: [],
  skipped: [],
  fixedPixels: [],
  draftFixes: [],
  panelCount: MAX_PANEL_COUNT,
  scope: 'all',
  activePanel: 0,
  panelScanModes: Array.from({ length: MAX_PANEL_COUNT }, () => 'row_ltr'),
  sequence: [],
};

function authHeaders() {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function startPollingLoops() {
  if (pollTimerStatus) clearInterval(pollTimerStatus);
  if (pollTimerPreview) clearInterval(pollTimerPreview);
  if (ledDebugAutoPollTimer) clearInterval(ledDebugAutoPollTimer);

  const hasStatus = !!document.getElementById('statusApi');
  const hasPreview = !!document.getElementById('previewGrid');
  const hasLedDebugPanel = !!document.getElementById('ledDebugInfo');

  if (hasStatus || document.getElementById('dhtDebugInfo')) {
    pollTimerStatus = setInterval(refreshStatus, 5000);
  }

  if (hasLedDebugPanel) {
    ledDebugAutoPollTimer = setInterval(() => {
      refreshLedDebug({ silent: true });
    }, 1500);
  }

  if (hasPreview) {
    pollTimerPreview = setInterval(refreshPreview, 1000);
  }
}


function pageInfo() {
  const body = document.body;
  return {
    page: body?.dataset.page || 'overview',
    requiresAuth: body?.dataset.requiresAuth !== 'false',
  };
}

function initTopNavigation() {
  const links = Array.from(document.querySelectorAll('[data-page-link]'));
  if (!links.length) return;
  const { page } = pageInfo();
  links.forEach((link) => {
    link.classList.toggle('is-active', link.dataset.pageLink === page);
  });
}

function ensureAuthFlow() {
  const { requiresAuth, page } = pageInfo();
  if (requiresAuth && !token) {
    window.location.replace('/login');
    return false;
  }

  if (!requiresAuth && page === 'login' && token) {
    window.location.replace('/');
    return false;
  }

  return true;
}

function toast(message, isError = false) {
  const el = document.getElementById('toast');
  if (!el) return;
  el.innerText = message;
  el.style.background = isError ? '#8b0000' : '#111827';
  el.classList.add('show');
  if (toastHideTimer) clearTimeout(toastHideTimer);
  toastHideTimer = setTimeout(() => {
    el.classList.remove('show');
    toastHideTimer = null;
  }, isError ? TOAST_DURATION_MS.error : TOAST_DURATION_MS.success);
}

function formatTs(ts) {
  if (!ts) return '-';
  return new Date(ts * 1000).toLocaleTimeString();
}

function formatNumber(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  return Number(value).toLocaleString('de-DE', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function setTextIfExists(id, value) {
  const el = document.getElementById(id);
  if (!el) return;
  el.innerText = value;
}

function debugPanelLoadMessage(targetId, message, details = null) {
  const el = document.getElementById(targetId);
  if (!el) return;
  if (details) {
    el.innerText = `${message}\n${details}`;
    return;
  }
  el.innerText = message;
}

function parseLiveNumber(...values) {
  for (const value of values) {
    if (value === null || value === undefined) continue;
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    if (typeof value === 'string') {
      const normalized = value
        .trim()
        .replace(',', '.')
        .replace(/[^0-9+\-.]/g, '');
      if (!normalized) continue;
      const parsed = Number(normalized);
      if (!Number.isNaN(parsed) && Number.isFinite(parsed)) return parsed;
    }
  }
  return null;
}

function getStatusSnapshot(payload) {
  const root = payload || {};
  const display = root.display || {};
  const sourceDataRaw = root.live_data || root.data || root.cache || root;
  const externalDataRaw = root.data || root.cache || {};
  const sourceData = sourceDataRaw && typeof sourceDataRaw === 'object' ? sourceDataRaw : {};
  const externalData = externalDataRaw && typeof externalDataRaw === 'object' ? externalDataRaw : {};
  const liveDataDebug = root.live_data_debug && typeof root.live_data_debug === 'object'
    ? root.live_data_debug
    : {};
  const renderDebug = liveDataDebug.render_debug && typeof liveDataDebug.render_debug === 'object'
    ? liveDataDebug.render_debug
    : {};
  const panelValues = renderDebug.panel_values && typeof renderDebug.panel_values === 'object'
    ? renderDebug.panel_values
    : {};
  const panelSourceData = { ...sourceData, ...panelValues };
  return { display, sourceData: panelSourceData, externalData, liveDataDebug };
}

function formatDebugValue(value) {
  if (value === null || value === undefined) return '-';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return `${value}`;
  return JSON.stringify(value);
}

function formatAgeSeconds(timestamp) {
  if (!timestamp) return '-';
  const now = Date.now() / 1000;
  const age = Math.max(0, now - Number(timestamp));
  if (!Number.isFinite(age)) return '-';
  if (age < 1) return '<1s';
  if (age < 120) return `${Math.round(age)}s`;
  if (age < 7200) return `${Math.round(age / 60)}m`;
  return `${Math.round(age / 3600)}h`;
}


function formatMs(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  return `${Number(value).toFixed(digits)} ms`;
}

function pushBounded(list, entry, limit = 25) {
  list.unshift(entry);
  if (list.length > limit) list.length = limit;
}

function renderSerialDebugView(result) {
  const summaryEl = document.getElementById('serialDebugSummary');
  const metricsEl = document.getElementById('serialDebugMetrics');
  const timelineEl = document.getElementById('serialDebugTimeline');
  const arduinoEl = document.getElementById('arduinoDebugInfo');
  if (!summaryEl && !metricsEl && !timelineEl && !arduinoEl) return;

  const led = result && typeof result === 'object' ? result : {};
  const serial = led.serial && typeof led.serial === 'object' ? led.serial : null;

  if (!serial) {
    if (summaryEl) summaryEl.innerText = `Status: ⚠️ Kein Serial-Transport aktiv
Aktueller Transport: ${led.transport || '-'}
Strip: ${led.strip_class || '-'}`;
    if (metricsEl) metricsEl.innerText = 'Keine Serial-Metriken verfügbar (LED Driver läuft nicht im serial-Modus).';
    if (timelineEl) timelineEl.innerText = 'Kein Verlauf, da kein serial-Modus aktiv ist.';
    if (arduinoEl) arduinoEl.innerText = 'Arduino-Debugwerte sind nur mit led_transport=serial verfügbar.';
    return;
  }

  const arduinoDebug = serial.arduino_debug && typeof serial.arduino_debug === 'object'
    ? serial.arduino_debug
    : null;

  const nowTs = Date.now() / 1000;
  pushBounded(serialStateHistory, {
    ts: nowTs,
    frames: serial.frames_sent,
    bytes: serial.bytes_sent,
    pingOk: serial.last_ping_ok,
    debugPollOk: serial.last_debug_poll_ok,
    err: serial.last_error,
  });

  const latest = serialStateHistory[0];
  const prev = serialStateHistory[1];
  const deltaFrames = latest && prev ? Math.max(0, (latest.frames || 0) - (prev.frames || 0)) : null;
  const deltaBytes = latest && prev ? Math.max(0, (latest.bytes || 0) - (prev.bytes || 0)) : null;

  const pingState = serial.last_ping_ok === true
    ? '✅ OK'
    : serial.last_ping_ok === false
      ? '⚠️ Fehler'
      : '— noch kein Ping';
  const healthState = serial.last_error ? '⚠️ Fehler erkannt' : '✅ stabil';

  if (summaryEl) {
    summaryEl.innerText = [
      `Status: ${healthState}`,
      `Port/Baud: ${serial.port || '-'} @ ${serial.baudrate || '-'} (requested: ${serial.requested_port || '-'})`,
      `Frames gesendet: ${formatNumber(serial.frames_sent)}`,
      `Letzter Frame: ${formatTs(serial.last_frame_at)} (${formatAgeSeconds(serial.last_frame_at)} alt)`,
      `Letzter Write: ${formatMs(serial.last_frame_write_ms, 3)}`,
      `Letzter ACK / Frame-RTT: ${formatMs(serial.last_frame_ack_ms, 3)} / ${formatMs(serial.last_frame_roundtrip_ms, 3)}`,
      `Ping: ${pingState} (${formatMs(serial.last_ping_rtt_ms, 3)})`,
      `Debug Poll: ${serial.last_debug_poll_ok === true ? '✅ OK' : serial.last_debug_poll_ok === false ? '⚠️ Fehler' : '— noch nicht'} (${formatMs(serial.last_debug_poll_rtt_ms, 3)})`,
      serial.last_debug_poll_error ? `Debug Poll Fehler: ${serial.last_debug_poll_error}` : 'Debug Poll Fehler: -',
      serial.last_error ? `Letzter Fehler: ${serial.last_error}` : 'Letzter Fehler: -',
    ].join('\n');
  }

  if (metricsEl) {
    metricsEl.innerText = [
      `Transport: ${led.transport || '-'} (${led.strip_class || '-'})`,
      `Brightness: ${serial.brightness ?? led.brightness ?? '-'} / 255`,
      `Frame-Payload: ${formatNumber(serial.frame_payload_bytes)} bytes`,
      `Gesamt gesendet: ${formatNumber(serial.bytes_sent)} bytes`,
      `Δ seit letztem Refresh: ${deltaFrames === null ? '-' : `${deltaFrames} Frames`} | ${deltaBytes === null ? '-' : `${deltaBytes} bytes`}`,
      `Brightness-Updates: ${formatNumber(serial.brightness_updates)} (Resync: ${formatNumber(serial.brightness_resyncs)})`,
      `Timeout read/write/ack: ${formatDebugValue(serial.timeout)}s / ${formatDebugValue(serial.write_timeout)}s / ${formatDebugValue(serial.ack_timeout)}s`,
      `Protokoll/ACK: v${formatDebugValue(serial.protocol_version)} | supported=${serial.frame_ack_supported ? 'ja' : 'nein'} | aktiv=${serial.frame_ack_enabled ? 'ja' : 'nein'}`,
      `Verbunden: ${serial.connected ? 'ja' : 'nein'}`,
      `Port-Kandidaten: ${(serial.port_candidates || []).join(', ') || '-'}`,
      `Sender-Thread: ${serial.sender_thread_alive ? 'alive' : 'dead'} | busy=${serial.sender_busy ? 'ja' : 'nein'} | wartet auf ACK=${serial.sender_waiting_for_ack ? 'ja' : 'nein'}`,
      `Queue latest-frame-wins: pending=${serial.sender_queue_pending ? 'ja' : 'nein'} | enqueued=${formatNumber(serial.frames_enqueued)} | ersetzt=${formatNumber(serial.frames_replaced_before_send)}`,
      `Queue-Wartezeit (letzter Frame): ${formatMs(serial.last_frame_queue_wait_ms, 3)}`,
      `Reconnects: ${formatNumber(serial.reconnect_successes)} / ${formatNumber(serial.reconnect_attempts)} (ok/versucht)`,
      `Frame Write Timeouts: ${formatNumber(serial.frame_write_timeouts)} | Retry-OK: ${formatNumber(serial.frame_write_timeout_retry_successes)} | Retries gesamt: ${formatNumber(serial.frame_write_retries)}`,
      `Frame ACKs: ${formatNumber(serial.frame_acks_received)} | ACK-Timeouts: ${formatNumber(serial.frame_ack_timeouts)} | ACK-Fehler: ${formatNumber(serial.frame_ack_errors)} | ACK-Retry-OK: ${formatNumber(serial.frame_ack_retry_successes)}`,
      `Frame Seq (tx/ack): ${formatDebugValue(serial.last_frame_seq)} / ${formatDebugValue(serial.last_frame_ack_seq)}`,
      `Frame-Resync erforderlich: ${serial.frame_resync_required ? 'ja' : 'nein'}`,
      `Debug-Poll Cache-Hits: ${formatNumber(serial.debug_poll_cache_hits)}`,
      `Letzter Reconnect: ${formatTs(serial.last_reconnect_at)} (${formatAgeSeconds(serial.last_reconnect_at)} alt)`,
      `Reconnect-Fehler: ${serial.last_reconnect_error || '-'}`,
      `Protocol-Probe-Fehler: ${serial.protocol_probe_error || '-'}`,
      `Arduino Snapshot: ${arduinoDebug ? 'vorhanden' : 'nicht verfügbar'}`,
      `Ping-Fehler: ${serial.last_ping_error || '-'}`,
      `Debug-Poll-Fehler: ${serial.last_debug_poll_error || '-'}`,
      `Fehlerzeitpunkt: ${formatTs(serial.last_error_at)} (${formatAgeSeconds(serial.last_error_at)} alt)`,
      `Sender-Fehler: ${serial.sender_last_error || '-'} (${formatTs(serial.sender_last_error_at)} / ${formatAgeSeconds(serial.sender_last_error_at)} alt)`,
    ].join('\n');
  }

  if (arduinoEl) {
    if (!arduinoDebug) {
      arduinoEl.innerText = [
        'Noch keine Arduino-Debugwerte empfangen.',
        `Letzter Poll: ${formatTs(serial.last_debug_poll_at)} (${formatAgeSeconds(serial.last_debug_poll_at)} alt)`,
        `Poll-Status: ${serial.last_debug_poll_ok === false ? '⚠️ Fehler' : 'warte auf Daten'}`,
        serial.last_debug_poll_error ? `Poll-Fehler: ${serial.last_debug_poll_error}` : 'Poll-Fehler: -',
        serial.last_error ? `Fehler: ${serial.last_error}` : 'Fehler: -',
      ].join('\n');
    } else {
      arduinoEl.innerText = [
        `Protokollversion: ${arduinoDebug.protocol_version ?? '-'}`,
        `Uptime: ${arduinoDebug.uptime_ms ?? '-'} ms`,
        `Pakete OK: ${formatNumber(arduinoDebug.packets_ok)}`,
        `Frame-Pakete: ${formatNumber(arduinoDebug.frame_packets)}`,
        `Brightness-Pakete: ${formatNumber(arduinoDebug.brightness_packets)}`,
        `Ping-Pakete: ${formatNumber(arduinoDebug.ping_packets)}`,
        `Debug-Pakete: ${formatNumber(arduinoDebug.debug_packets)}`,
        `Checksum-Fehler: ${formatNumber(arduinoDebug.checksum_errors)}`,
        `Ungültige Pakete: ${formatNumber(arduinoDebug.invalid_packets)}`,
        `Timeouts: ${formatNumber(arduinoDebug.packet_timeouts)}`,
        `Letzter Befehl: 0x${Number(arduinoDebug.last_command || 0).toString(16).padStart(2, '0')}`,
        `Arduino Brightness: ${arduinoDebug.brightness ?? '-'} / 255`,
      ].join('\n');
    }
  }

  if (timelineEl) {
    const lines = serialStateHistory.slice(0, 8).map((item, index) => {
      const prevItem = serialStateHistory[index + 1];
      const dFrames = prevItem ? Math.max(0, (item.frames || 0) - (prevItem.frames || 0)) : 0;
      const dBytes = prevItem ? Math.max(0, (item.bytes || 0) - (prevItem.bytes || 0)) : 0;
      return `${formatTs(item.ts)} | +${dFrames} Frames | +${dBytes} bytes | ping=${item.pingOk === null || item.pingOk === undefined ? '-' : item.pingOk ? 'ok' : 'fail'} | poll=${item.debugPollOk === null || item.debugPollOk === undefined ? '-' : item.debugPollOk ? 'ok' : 'fail'}${item.err ? ` | err=${item.err}` : ''}`;
    });
    timelineEl.innerText = lines.length ? lines.join('\n') : '-';
  }
}

function clearSerialDebugHistory() {
  serialPingHistory.length = 0;
  serialStateHistory.length = 0;
  renderSerialPingHistory();
  const timelineEl = document.getElementById('serialDebugTimeline');
  if (timelineEl) timelineEl.innerText = '-';
  toast('Serial-Debugverlauf zurückgesetzt');
}

function renderSerialPingHistory() {
  const el = document.getElementById('serialPingHistory');
  if (!el) return;
  if (!serialPingHistory.length) {
    el.innerText = 'Noch kein Ping ausgeführt.';
    return;
  }

  el.innerText = serialPingHistory
    .slice(0, 12)
    .map((entry) => `${formatTs(entry.ts)} | ${entry.ok ? '✅' : '⚠️'} | RTT=${formatMs(entry.roundtrip, 3)} | nonce=${entry.nonce ?? '-'} | rsp=${entry.responseNonce ?? '-'}${entry.error ? ` | ${entry.error}` : ''}`)
    .join('\n');
}

function renderBackendStatusDebug(payload) {
  const summaryEl = document.getElementById('backendStatusSummary');
  const jsonEl = document.getElementById('backendStatusInfo');
  if (!summaryEl && !jsonEl) return;

  const root = payload && typeof payload === 'object' ? payload : {};
  const display = root.display && typeof root.display === 'object' ? root.display : {};

  if (jsonEl) {
    jsonEl.innerText = JSON.stringify(root, null, 2);
  }

  if (!summaryEl) return;

  summaryEl.innerText = [
    `Display-Service: ${display.running ? 'aktiv' : 'inaktiv'}`,
    `Render-Task alive: ${display.task_alive ? 'ja' : 'nein'}`,
    `FPS (target/actual): ${display.target_fps ?? '-'} / ${display.actual_fps ?? '-'}`,
    `Letzter Frame: ${formatTs(display.last_frame_ts)} (${formatAgeSeconds(display.last_frame_ts)} alt)`,
    `Loop Timing: work=${formatMs(display.last_loop_work_ms, 3)} | sleep=${formatMs(display.last_loop_sleep_ms, 3)} | total=${formatMs(display.last_loop_total_ms, 3)}`,
    `LED Dispatch (Render-Thread): ${formatMs(display.last_led_write_ms, 3)} | frame submitted=${display.last_led_frame_sent === true ? 'ja' : display.last_led_frame_sent === false ? 'nein' : '-'}`,
    `Skipped duplicate frames: ${formatNumber(display.unchanged_frame_skips)}`,
    `Module Query: ${formatMs(display.last_module_query_ms, 3)} | cache=${display.last_module_query_cache_hit === true ? 'hit' : display.last_module_query_cache_hit === false ? 'miss' : '-'}`,
    `Quelle: ${display.last_source || '-'} | Modul: ${display.last_module || '-'}`,
    `Letzter Render-Loop-Fehler: ${display.last_loop_error || '-'}`,
    `Fehlerzeitpunkt: ${formatTs(display.last_loop_error_at)} (${formatAgeSeconds(display.last_loop_error_at)} alt)`,
  ].join('\n');
}

function getLiveDataWaitReason(display, sourceData, liveDataDebug) {
  const snapshotTs = liveDataDebug.snapshot_ts || display.cache_snapshot_ts;
  const hasAnyValues = !!liveDataDebug.has_any_values;
  const renderDebug = liveDataDebug.render_debug || {};
  const moduleHasValues = !!renderDebug.cache_has_any_values;
  const activeModule = renderDebug.module_key || display.last_module;
  if (!snapshotTs) {
    return 'warte auf den ersten Cache-Snapshot aus dem Render-Loop (display.cache_snapshot_ts ist leer)';
  }
  if (activeModule && !moduleHasValues && hasAnyValues) {
    return `Global sind Daten vorhanden, aber das aktive Modul (${activeModule}) hat aktuell keine Nutzwerte im Cache`;
  }
  if (!hasAnyValues) {
    const weatherSource = sourceData.weather_source || sourceData.dht_backend || '-';
    return `Snapshot vorhanden, aber noch keine Nutzdaten (BTC/Wetter/DHT). Wetterquelle aktuell: ${weatherSource}`;
  }
  return 'ok';
}

function getModuleFieldMap(moduleKey) {
  if (moduleKey === 'btc') {
    return {
      overviewBtcPrice: ['btc_eur'],
      overviewBtcTrend: ['btc_trend'],
      overviewBlockHeight: ['btc_block_height'],
      overviewBlockHeightUpdated: ['btc_block_height_updated_at', 'btc_block_height_error'],
    };
  }
  if (moduleKey === 'weather') {
    return {
      overviewOutdoorTemp: ['weather_outdoor_temp', 'weather_temp'],
      overviewWeatherSource: ['weather_source', 'dht_backend'],
      overviewIndoorTemp: ['weather_indoor_temp', 'dht_raw_temperature'],
      overviewDhtBackend: ['dht_backend'],
      overviewHumidity: ['weather_indoor_humidity', 'dht_raw_humidity'],
      overviewDhtUpdated: ['dht_updated_at', 'weather_updated_at'],
    };
  }
  return {};
}

function renderOverviewLiveDataDebug(display, sourceData, externalData, liveDataDebug) {
  const el = document.getElementById('overviewLiveDataDebug');
  if (!el) return;
  const fields = [
    'btc_eur',
    'btc_trend',
    'btc_block_height',
    'weather_outdoor_temp',
    'weather_indoor_temp',
    'weather_indoor_humidity',
    'dht_raw_temperature',
    'dht_raw_humidity',
  ];
  const waitReason = getLiveDataWaitReason(display, sourceData, liveDataDebug);
  const timestamps = liveDataDebug.timestamps || {};
  const errors = liveDataDebug.errors || {};
  const pollState = liveDataDebug.poll_state || {};
  const pollIntervals = pollState.poll_intervals || {};
  const renderDebug = liveDataDebug.render_debug || {};
  const renderFields = renderDebug.panel_values || {};
  const moduleMap = getModuleFieldMap(renderDebug.module_key || display.last_module);

  const lines = [
    `Status: ${waitReason === 'ok' ? 'Daten vorhanden' : 'Warten auf Daten'}`,
    `Wartegrund: ${waitReason === 'ok' ? '-' : waitReason}`,
    `Quelle: ${liveDataDebug.source || 'unbekannt'}`,
    `Render-Quelle: ${display.last_source || '-'}`,
    `Aktives Modul: ${display.last_module || '-'}`,
    `Render-Hook Modul: ${renderDebug.module_key || '-'}`,
    `Render-Hook Text: ${renderDebug.module_text || '-'}`,
    `Render-Hook Update: ${formatTs(renderDebug.updated_at)} | ${formatAgeSeconds(renderDebug.updated_at)}`,
    `Snapshot: ${formatTs(liveDataDebug.snapshot_ts || display.cache_snapshot_ts)}`,
    `LiveData hat Werte: ${liveDataDebug.has_any_values ? 'ja' : 'nein'}`,
    `Aktives Modul hat Werte: ${renderDebug.cache_has_any_values ? 'ja' : 'nein'}`,
    `Display-Cache-Keys: ${(liveDataDebug.display_cache_keys || []).length}`,
    `External-Cache-Keys: ${(liveDataDebug.external_cache_keys || []).length}`,
    `Fehlende Modul-Keys: ${(renderDebug.cache_missing_keys || []).join(', ') || '-'}`,
    '',
    'Polling:',
    `- ExternalDataService läuft: ${pollState.external_running ? 'ja' : 'nein'} (Tasks: ${pollState.poll_task_count ?? 0})`,
    `- Intervalle: BTC=${pollIntervals.btc_seconds ?? '-'}s, Weather=${pollIntervals.weather_seconds ?? '-'}s, DHT=${pollIntervals.dht_seconds ?? '-'}s (enabled=${pollState.dht_enabled ? 'ja' : 'nein'})`,
    '',
    'Letzte Updates (Zeit | Alter):',
    `- BTC: ${formatTs(timestamps.btc_updated_at)} | ${formatAgeSeconds(timestamps.btc_updated_at)}`,
    `- BTC Blockheight: ${formatTs(timestamps.btc_block_height_updated_at)} | ${formatAgeSeconds(timestamps.btc_block_height_updated_at)}`,
    `- Weather: ${formatTs(timestamps.weather_updated_at)} | ${formatAgeSeconds(timestamps.weather_updated_at)}`,
    `- DHT: ${formatTs(timestamps.dht_updated_at)} | ${formatAgeSeconds(timestamps.dht_updated_at)}`,
    `- DHT letzter Versuch: ${formatTs(timestamps.dht_last_attempt_at)} | ${formatAgeSeconds(timestamps.dht_last_attempt_at)}`,
    '',
    'Fehlerstatus:',
    `- BTC: ${errors.btc_error || '-'}`,
    `- BTC Blockheight: ${errors.btc_block_height_error || '-'}`,
    `- Weather: ${errors.weather_error || '-'}`,
    `- DHT: ${errors.dht_error || '-'}`,
    '',
    'Modul-Hook (Werte, die das aktive Modul direkt nutzt):',
  ];

  Object.entries(renderFields).forEach(([key, value]) => {
    lines.push(`• ${key}: ${formatDebugValue(value)}`);
  });

  lines.push('');
  lines.push('UI-Verknüpfung (Overview-Feld -> Datenkeys):');
  Object.entries(moduleMap).forEach(([uiKey, keys]) => {
    lines.push(`• ${uiKey} <= ${keys.join(' | ')}`);
  });
  if (!Object.keys(moduleMap).length) {
    lines.push('• keine direkte Modul-Verknüpfung (z. B. clock/textbox/bitmap)');
  }

  lines.push('');
  lines.push('Vergleich display-cache vs external-cache:');

  fields.forEach((key) => {
    const live = sourceData?.[key];
    const ext = externalData?.[key];
    const marker = live !== null && live !== undefined ? '✓' : '✗';
    lines.push(`${marker} ${key}: live=${formatDebugValue(live)} | ext=${formatDebugValue(ext)}`);
  });
  el.innerText = lines.join('\n');
}

function renderLiveDataSection(sourceData) {
  const weatherOutdoorTemp = parseLiveNumber(sourceData.weather_outdoor_temp, sourceData.weather_temp);
  const weatherIndoorTemp = parseLiveNumber(sourceData.weather_indoor_temp, sourceData.dht_raw_temperature);
  const weatherIndoorHumidity = parseLiveNumber(sourceData.weather_indoor_humidity, sourceData.dht_raw_humidity);
  const weatherSource = sourceData.weather_source || sourceData.dht_backend || 'api';

  setTextIfExists('overviewBtcPrice', sourceData.btc_eur === null || sourceData.btc_eur === undefined
    ? '-'
    : `${formatNumber(sourceData.btc_eur, 0)} €`);
  setTextIfExists('overviewBtcTrend', `Trend: ${sourceData.btc_trend || '-'}`);
  setTextIfExists('overviewBlockHeight', sourceData.btc_block_height === null || sourceData.btc_block_height === undefined
    ? '-'
    : formatNumber(sourceData.btc_block_height, 0));
  setTextIfExists('overviewBlockHeightUpdated', sourceData.btc_block_height_error
    ? `Fehler: ${String(sourceData.btc_block_height_error).slice(0, 28)}`
    : `Update: ${formatTs(sourceData.btc_block_height_updated_at)}`);

  setTextIfExists('overviewOutdoorTemp', weatherOutdoorTemp === null
    ? '-'
    : `${formatNumber(weatherOutdoorTemp, 1)} °C`);
  setTextIfExists('overviewWeatherSource', `Quelle: ${weatherSource}`);
  setTextIfExists('overviewIndoorTemp', weatherIndoorTemp === null
    ? '-'
    : `${formatNumber(weatherIndoorTemp, 1)} °C`);
  setTextIfExists('overviewDhtBackend', `Backend: ${sourceData.dht_backend || '-'}`);
  setTextIfExists('overviewHumidity', weatherIndoorHumidity === null
    ? '-'
    : `${formatNumber(weatherIndoorHumidity, 1)} %`);
  setTextIfExists('overviewDhtUpdated', `Update: ${formatTs(sourceData.dht_updated_at)}`);
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
      const msg = formatApiErrorMessage(data?.detail, res.status);
      if (res.status === 401 && token) {
        token = '';
        localStorage.removeItem('token');
        setTimeout(() => {
          window.location.replace('/login');
        }, 250);
      }
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

function formatApiErrorMessage(detail, status) {
  if (!detail) return `HTTP ${status}`;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const first = detail[0];
    if (typeof first === 'string') return first;
    if (first && typeof first === 'object') {
      const fieldPath = Array.isArray(first.loc) ? first.loc.slice(1).join('.') : '';
      const message = first.msg || first.message || JSON.stringify(first);
      const max = first?.ctx?.le;
      const min = first?.ctx?.ge;
      if (message.includes('less than or equal to') && Number.isFinite(Number(max))) {
        const label = fieldPath || 'Wert';
        return `${label}: Zu groß. Erlaubt sind maximal ${Number(max)} Sekunden.`;
      }
      if (message.includes('greater than or equal to') && Number.isFinite(Number(min))) {
        const label = fieldPath || 'Wert';
        return `${label}: Zu klein. Erlaubt sind mindestens ${Number(min)} Sekunden.`;
      }
      return fieldPath ? `${fieldPath}: ${message}` : message;
    }
    return JSON.stringify(first);
  }
  if (typeof detail === 'object') {
    if (typeof detail.message === 'string') return detail.message;
    return JSON.stringify(detail);
  }
  return String(detail);
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

function setLoginUiState(isLoading = false, statusText = '') {
  const button = document.getElementById('loginButton');
  if (button) {
    button.disabled = isLoading;
    button.innerText = isLoading ? 'Logge ein…' : 'Einloggen';
  }

  const statusEl = document.getElementById('loginStatus');
  if (statusEl) statusEl.innerText = statusText;
}

function initLoginPage() {
  const passwordInput = document.getElementById('password');
  const usernameInput = document.getElementById('username');
  if (!passwordInput || !usernameInput) return;

  if (usernameInput.value.trim()) {
    passwordInput.focus();
  } else {
    usernameInput.focus();
  }

  [usernameInput, passwordInput].forEach((input) => {
    input.addEventListener('input', () => setLoginUiState(false, ''));
  });
}

async function login(event) {
  event?.preventDefault();

  const username = document.getElementById('username')?.value.trim() || '';
  const password = document.getElementById('password')?.value || '';

  if (!username || !password) {
    setLoginUiState(false, 'Bitte Benutzername und Passwort eingeben');
    return;
  }

  setLoginUiState(true, 'Prüfe Login…');

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
    setLoginUiState(false, 'Login fehlgeschlagen');
    return;
  }

  token = data.access_token;
  localStorage.setItem('token', token);
  setLoginUiState(true, 'Eingeloggt – weiter zur Übersicht');
  setTimeout(() => { window.location.href = '/'; }, 350);
}


function logout() {
  token = '';
  localStorage.removeItem('token');
  toast('Abgemeldet');
  setTimeout(() => {
    window.location.href = '/login';
  }, 200);
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
  const statusApiEl = document.getElementById('statusApi');
  const hasStatusUi = !!statusApiEl;

  const data = await apiRequest('/api/debug/status');
  if (!data) {
    if (hasStatusUi) statusApiEl.innerText = token ? 'offline / auth?' : 'nicht eingeloggt';
    debugPanelLoadMessage(
      'backendStatusSummary',
      'Fehler beim Laden von /api/debug/status',
      'Pruefe Login, Backend-Logs und Browser-Konsole/Netzwerk-Tab.',
    );
    debugPanelLoadMessage(
      'backendStatusInfo',
      JSON.stringify({ ok: false, endpoint: '/api/debug/status', at: new Date().toISOString() }, null, 2),
    );
    return;
  }

  renderBackendStatusDebug(data);
  await refreshLiveMappingState({ silent: true, useStatusPayload: data.mapping || null });

  if (!hasStatusUi) {
    await refreshDhtDebug();
    await refreshLedDebug({ silent: true });
    return;
  }

  const {
    display,
    sourceData,
    externalData,
    liveDataDebug,
  } = getStatusSnapshot(data);
  const weatherSource = sourceData.weather_source || sourceData.dht_backend || 'api';
  const shortError = (value, maxLen = 28) => {
    if (!value) return null;
    const text = typeof value === 'string' ? value : JSON.stringify(value);
    if (!text) return null;
    return text.length > maxLen ? `${text.slice(0, maxLen)}...` : text;
  };

  statusApiEl.innerText = 'online';
  setTextIfExists('statusSource', display.last_source || '-');
  setTextIfExists('statusModule', display.last_module || '-');
  setTextIfExists('statusFps', `${display.target_fps ?? '-'} / ${display.actual_fps ?? '-'}`);
  setTextIfExists('statusDebug', display.debug_active
    ? `${display.debug_pattern} bis ${formatTs(display.debug_until)}`
    : 'inaktiv');
  setTextIfExists('statusBtc', shortError(sourceData.btc_error)
    ? `Fehler (${shortError(sourceData.btc_error)})`
    : formatTs(sourceData.btc_updated_at));
  setTextIfExists('statusWeather', shortError(sourceData.weather_error)
    ? `Fehler (${shortError(sourceData.weather_error)})`
    : `${formatTs(sourceData.weather_updated_at)} (${weatherSource})`);
  setTextIfExists('statusDhtLevel', sourceData.dht_gpio_level === null || sourceData.dht_gpio_level === undefined ? '-' : `${sourceData.dht_gpio_level}`);
  setTextIfExists('statusDhtRead', shortError(sourceData.dht_error, 24)
    ? `Fehler (${shortError(sourceData.dht_error, 24)})`
    : `${formatTs(sourceData.dht_updated_at)} / ${sourceData.dht_last_duration_ms ?? '-'}ms / ${sourceData.dht_backend || 'n/a'}`);

  renderLiveDataSection(sourceData);
  renderOverviewLiveDataDebug(display, sourceData, externalData, liveDataDebug);

  await refreshDhtDebug();
  await refreshLedDebug({ silent: true });
}

async function refreshDhtDebug() {
  const data = await apiRequest('/api/debug/dht');
  if (!data) {
    debugPanelLoadMessage(
      'dhtDebugInfo',
      JSON.stringify({ ok: false, endpoint: '/api/debug/dht', at: new Date().toISOString() }, null, 2),
    );
    return;
  }
  const el = document.getElementById('dhtDebugInfo');
  if (!el) return;
  el.innerText = JSON.stringify(data, null, 2);
}




async function runDhtReadOnce() {
  const data = await apiRequest('/api/debug/dht/read-once', { method: 'POST' }, 'DHT Einzel-Read ausgeführt');
  if (!data?.result) return;

  const el = document.getElementById('dhtReadOnceResult');
  if (!el) return;

  const result = data.result;
  const state = result.ok ? '✅ OK' : '⚠️ Fehler';
  const temp = result.temperature === null || result.temperature === undefined ? '-' : `${result.temperature} °C`;
  const hum = result.humidity === null || result.humidity === undefined ? '-' : `${result.humidity} %`;
  el.innerText = [
    `Status: ${state}`,
    `Backend: ${result.backend || 'unbekannt'}`,
    `GPIO ${result.gpio_pin}: level before=${result.gpio_level_before} after=${result.gpio_level_after}`,
    `Read-Dauer: ${result.duration_ms} ms`,
    `Temperatur: ${temp}`,
    `Luftfeuchte: ${hum}`,
    result.error ? `Fehler: ${result.error}` : 'Fehler: -',
  ].join('\n');

  await refreshDhtDebug();
}

async function runGpioEnvironmentCheck() {
  const data = await apiRequest('/api/debug/gpio/environment');
  if (!data?.result) return;
  renderGpioResult('GPIO-Umgebungscheck', data.result);
}

function renderGpioResult(title, result) {
  const el = document.getElementById('gpioFinderResult');
  if (!el) return;
  const safe = result || {};
  const status = safe.ok ? '✅ OK' : '⚠️ Fehler';
  el.innerText = `${title}\nStatus: ${status}\n${JSON.stringify(safe, null, 2)}`;
}

async function runGpioOutputTest() {
  const gpioPin = parseInt(document.getElementById('gpioPin').value, 10);
  const pulses = parseInt(document.getElementById('gpioPulses').value, 10);
  const holdMs = parseInt(document.getElementById('gpioHoldMs').value, 10);

  const data = await apiRequest('/api/debug/gpio/output-test', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ gpio_pin: gpioPin, pulses, hold_ms: holdMs }),
  }, 'GPIO Output-Test abgeschlossen');

  if (!data?.result) return;
  renderGpioResult(`LED-Datenpin-Test auf GPIO ${gpioPin}`, data.result);
}

async function runGpioInputProbe() {
  const gpioPin = parseInt(document.getElementById('gpioPin').value, 10);
  const sampleMs = parseInt(document.getElementById('gpioSampleMs').value, 10);
  const pullUp = document.getElementById('gpioPull').value === 'up';

  const data = await apiRequest('/api/debug/gpio/input-probe', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ gpio_pin: gpioPin, sample_ms: sampleMs, pull_up: pullUp }),
  }, 'GPIO Input-Probe abgeschlossen');

  if (!data?.result) return;
  renderGpioResult(`Sensor-Probe auf GPIO ${gpioPin}`, data.result);
}

async function refreshLedDebug(options = {}) {
  const { silent = false } = options;

  if (ledDebugRefreshInFlight) {
    return ledDebugRefreshInFlight;
  }

  ledDebugRefreshInFlight = (async () => {
    const data = await apiRequest('/api/debug/led', {}, silent ? '' : 'Arduino Serial Debug aktualisiert');
    if (!data?.result) {
      debugPanelLoadMessage(
        'serialDebugSummary',
        'Fehler beim Laden von /api/debug/led',
        'Pruefe Login, API und ob das Backend laeuft.',
      );
      debugPanelLoadMessage('serialDebugMetrics', '-');
      debugPanelLoadMessage(
        'ledDebugInfo',
        JSON.stringify({ ok: false, endpoint: '/api/debug/led', at: new Date().toISOString() }, null, 2),
      );
      return null;
    }
    const el = document.getElementById('ledDebugInfo');
    if (!el) return data.result;
    el.innerText = JSON.stringify(data.result, null, 2);
    renderSerialDebugView(data.result);
    return data.result;
  })();

  try {
    return await ledDebugRefreshInFlight;
  } finally {
    ledDebugRefreshInFlight = null;
  }
}


async function runLedSerialPing() {
  const nonce = Math.floor(Date.now()) >>> 0;
  const data = await apiRequest('/api/debug/led/serial-ping', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ nonce }) }, 'Serial Ping ausgeführt');
  if (!data?.result) return;

  const el = document.getElementById('ledPingResult');
  if (!el) return;
  const r = data.result;
  pushBounded(serialPingHistory, {
    ts: Date.now() / 1000,
    ok: !!r.ok,
    roundtrip: r.roundtrip_ms,
    nonce: r.nonce,
    responseNonce: r.response_nonce,
    error: r.error,
  }, 30);
  renderSerialPingHistory();

  el.innerText = [
    `Status: ${r.ok ? '✅ OK' : '⚠️ Fehler'}`,
    `Reconnect während Ping: ${r.reconnected ? 'ja' : 'nein'}`,
    `Roundtrip: ${r.roundtrip_ms ?? '-'} ms`,
    `Nonce: ${r.nonce ?? '-'}`,
    `Antwort-Nonce: ${r.response_nonce ?? '-'}`,
    `Rohantwort (hex): ${r.raw_response_hex || '-'}`,
    `Fehler: ${r.error || '-'}`,
  ].join('\n');

  await refreshLedDebug({ silent: true });
}

function initPreviewGrid() {
  const container = document.getElementById('previewGrid');
  if (!container || container.childElementCount > 0) return;
  for (let y = 0; y < 8; y += 1) {
    for (let x = 0; x < 32; x += 1) {
      const px = document.createElement('div');
      px.className = 'preview-pixel';
      if (x > 0 && x % 8 === 0) px.classList.add('panel-divider-left');
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
  const maxX = (Math.max(1, Math.min(MAX_PANEL_COUNT, mappingAssist.panelCount || MAX_PANEL_COUNT)) * PANEL_WIDTH) - 1;
  const x = parseInt(document.getElementById('mapX').value, 10);
  const y = parseInt(document.getElementById('mapY').value, 10);
  if (!Number.isInteger(x) || !Number.isInteger(y) || x < 0 || x > maxX || y < 0 || y > 7) {
    toast(`X/Y müssen im Bereich 0..${maxX} / 0..7 liegen`, true);
    return;
  }

  const data = await apiRequest(`/api/debug/mapping/coordinate?x=${x}&y=${y}`);
  if (!data?.mapping) return;

  const m = data.mapping;
  document.getElementById('mappingInfo').innerText =
    `x=${m.x}, y=${m.y} -> panel=${m.panel_index}, rotation=${m.panel_rotation}°, local=(${m.local_x},${m.local_y}), pixel_in_panel=${m.pixel_in_panel}, led_index=${m.index}, serpentine_flip=${m.serpentine_flipped}`;
}

function parseCsvIntList(raw) {
  if (typeof raw !== 'string') return [];
  return raw
    .split(',')
    .map((part) => part.trim())
    .filter((part) => part.length > 0)
    .map((part) => Number.parseInt(part, 10))
    .filter((value) => Number.isInteger(value));
}

function mappingFormPayload() {
  return {
    first_pixel_offset: parseInt(document.getElementById('mapFirstOffset').value, 10) || 0,
    panel_order: parseCsvIntList(document.getElementById('mapPanelOrder').value),
    panel_rotations: parseCsvIntList(document.getElementById('mapPanelRotations').value),
    data_starts_right: !!document.getElementById('mapDataStartsRight').checked,
    serpentine: !!document.getElementById('mapSerpentine').checked,
  };
}

function applyMappingToForm(mapping) {
  if (!mapping || typeof mapping !== 'object') return;
  const offsetEl = document.getElementById('mapFirstOffset');
  const panelOrderEl = document.getElementById('mapPanelOrder');
  const rotationsEl = document.getElementById('mapPanelRotations');
  const dataStartsRightEl = document.getElementById('mapDataStartsRight');
  const serpentineEl = document.getElementById('mapSerpentine');
  if (!offsetEl || !panelOrderEl || !rotationsEl || !dataStartsRightEl || !serpentineEl) return;

  offsetEl.value = `${mapping.first_pixel_offset ?? 0}`;
  panelOrderEl.value = Array.isArray(mapping.panel_order) ? mapping.panel_order.join(',') : '';
  rotationsEl.value = Array.isArray(mapping.panel_rotations) ? mapping.panel_rotations.join(',') : '';
  dataStartsRightEl.checked = !!mapping.data_starts_right;
  serpentineEl.checked = !!mapping.serpentine;
}

function renderRuntimeMappingInfo(mapping) {
  const el = document.getElementById('mappingRuntimeInfo');
  if (!el) return;
  if (!mapping) {
    el.innerText = 'Kein Mapping-Status verfügbar.';
    return;
  }

  el.innerText = [
    `Live Override: ${mapping.active ? '✅ aktiv' : 'ℹ️ aus (Settings)'}`,
    `Quelle: ${mapping.source || '-'}`,
    `first_pixel_offset: ${mapping.first_pixel_offset}`,
    `data_starts_right: ${mapping.data_starts_right}`,
    `serpentine: ${mapping.serpentine}`,
    `panel_order: ${(mapping.panel_order || []).join(',') || '-'}`,
    `panel_rotations: ${(mapping.panel_rotations || []).join(',') || '-'}`,
    `pixel_fixes_count: ${mapping.pixel_fixes_count ?? 0}`,
    `Panel-Layout: ${mapping.panel_count || '-'} x ${mapping.panel_width || '-'}×${mapping.panel_height || '-'} | Matrix ${mapping.panel_columns || '-'}×${mapping.panel_rows || '-'} | LED count ${mapping.led_count || '-'}`,
    'Tipp: Starte "Stripes" oder "Panel Walk" und ändere Offset/Order/Rotation live bis Preview + reale LEDs übereinstimmen.',
  ].join('\n');
}

async function refreshLiveMappingState(options = {}) {
  const { silent = true, useStatusPayload = null } = options;
  let mapping = useStatusPayload;
  if (!mapping) {
    const data = await apiRequest('/api/debug/mapping/runtime', {}, silent ? '' : 'Live-Mapping geladen');
    if (!data?.mapping) return null;
    mapping = data.mapping;
  }
  applyMappingToForm(mapping);
  renderRuntimeMappingInfo(mapping);
  const panelCountFromRuntime = Number(mapping.panel_count);
  if (Number.isInteger(panelCountFromRuntime) && panelCountFromRuntime >= 1 && panelCountFromRuntime <= MAX_PANEL_COUNT) {
    mappingAssist.panelCount = panelCountFromRuntime;
    const panelCountEl = document.getElementById('assistPanelCount');
    if (panelCountEl) panelCountEl.value = `${panelCountFromRuntime}`;
    rebuildMappingAssistSequence();
    renderMappingAssistState();
  }
  return mapping;
}

async function applyLiveMapping() {
  const payload = mappingFormPayload();
  const data = await apiRequest('/api/debug/mapping/runtime', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }, 'Live-Mapping angewendet');
  if (!data?.mapping) return;
  applyMappingToForm(data.mapping);
  renderRuntimeMappingInfo(data.mapping);
  await refreshPreview();
}

async function resetLiveMapping() {
  const data = await apiRequest('/api/debug/mapping/runtime', { method: 'DELETE' }, 'Live-Mapping zurückgesetzt');
  if (!data?.mapping) return;
  applyMappingToForm(data.mapping);
  renderRuntimeMappingInfo(data.mapping);
  await refreshPreview();
}

async function nudgeFirstOffset(delta) {
  const offsetEl = document.getElementById('mapFirstOffset');
  if (!offsetEl) return;
  const current = parseInt(offsetEl.value, 10) || 0;
  offsetEl.value = `${current + delta}`;
  await applyLiveMapping();
}

function initMappingAssistGrid() {
  const container = document.getElementById('mappingAssistGrid');
  if (!container) return;

  const expectedPixels = LED_MATRIX_TOTAL_PIXELS;
  if (container.childElementCount !== expectedPixels) {
    container.replaceChildren();
  } else {
    return;
  }

  container.style.setProperty('--matrix-width', `${LED_MATRIX_WIDTH}`);
  container.style.setProperty('--matrix-height', `${LED_MATRIX_HEIGHT}`);
  container.style.display = 'grid';
  container.style.gridTemplateColumns = `repeat(${LED_MATRIX_WIDTH}, var(--pixel-size, 14px))`;
  container.style.gridTemplateRows = `repeat(${LED_MATRIX_HEIGHT}, var(--pixel-size, 14px))`;
  container.style.gridAutoFlow = 'row';
  container.style.gap = 'var(--pixel-gap, 2px)';
  container.style.width = 'max-content';
  container.style.maxWidth = '100%';
  container.style.overflowX = 'auto';

  for (let y = 0; y < LED_MATRIX_HEIGHT; y += 1) {
    for (let x = 0; x < LED_MATRIX_WIDTH; x += 1) {
      const px = document.createElement('button');
      px.type = 'button';
      px.className = 'preview-pixel';
      const panelIndex = Math.floor(x / PANEL_WIDTH);
      px.classList.add(panelIndex % 2 === 0 ? 'assist-panel-even' : 'assist-panel-odd');
      if (x > 0 && x % 8 === 0) px.classList.add('panel-divider-left');
      if (y > 0 && y % 8 === 0) px.classList.add('panel-divider-top');
      if (x % 8 === 7) px.classList.add('assist-panel-right-edge');
      if (y === 0) px.classList.add('assist-panel-top-edge');
      if (y === PANEL_HEIGHT - 1) px.classList.add('assist-panel-bottom-edge');
      px.id = `assist-${x}-${y}`;
      px.title = `Beobachtet: ${x},${y}`;
      px.setAttribute('aria-label', `Position ${x}, ${y}`);
      px.onclick = () => mappingAssistMarkObserved(x, y);
      container.appendChild(px);
    }
  }
  initMappingAssistConfigControls();
  rebuildMappingAssistSequence();
  renderMappingAssistGridState();
}

function updateMappingCoordinateRange() {
  const maxX = (Math.max(1, Math.min(MAX_PANEL_COUNT, mappingAssist.panelCount || MAX_PANEL_COUNT)) * PANEL_WIDTH) - 1;
  const mapX = document.getElementById('mapX');
  const mapXLabel = document.querySelector('label[for="mapX"]');
  if (mapX) mapX.max = `${maxX}`;
  if (mapXLabel) mapXLabel.innerText = `Logisches X (0-${maxX})`;
}

function mappingAssistDimensions() {
  const panelCount = Math.max(1, Math.min(MAX_PANEL_COUNT, Number(mappingAssist.panelCount) || MAX_PANEL_COUNT));
  return { panelCount, width: panelCount * PANEL_WIDTH, height: PANEL_HEIGHT, total: panelCount * PANEL_WIDTH * PANEL_HEIGHT };
}

function mappingAssistLocalOrder(mode) {
  const order = [];
  if (mode === 'col_ttb' || mode === 'col_serpentine') {
    for (let x = 0; x < PANEL_WIDTH; x += 1) {
      const serpentineFlip = mode === 'col_serpentine' && x % 2 === 1;
      for (let yStep = 0; yStep < PANEL_HEIGHT; yStep += 1) {
        const y = serpentineFlip ? (PANEL_HEIGHT - 1 - yStep) : yStep;
        order.push({ x, y });
      }
    }
    return order;
  }
  for (let y = 0; y < PANEL_HEIGHT; y += 1) {
    const serpentineFlip = mode === 'row_serpentine' && y % 2 === 1;
    for (let xStep = 0; xStep < PANEL_WIDTH; xStep += 1) {
      const x = serpentineFlip ? (PANEL_WIDTH - 1 - xStep) : xStep;
      order.push({ x, y });
    }
  }
  return order;
}

function rebuildMappingAssistSequence() {
  const dims = mappingAssistDimensions();
  const scope = mappingAssist.scope === 'active' ? 'active' : 'all';
  const activePanel = Math.max(0, Math.min(dims.panelCount - 1, Number(mappingAssist.activePanel) || 0));
  mappingAssist.activePanel = activePanel;
  const panels = scope === 'active'
    ? [activePanel]
    : Array.from({ length: dims.panelCount }, (_, idx) => idx);
  const sequence = [];
  panels.forEach((panelIndex) => {
    const mode = ASSIST_SCAN_MODES.includes(mappingAssist.panelScanModes[panelIndex])
      ? mappingAssist.panelScanModes[panelIndex]
      : 'row_ltr';
    const localOrder = mappingAssistLocalOrder(mode);
    localOrder.forEach((pos) => {
      sequence.push({
        x: panelIndex * PANEL_WIDTH + pos.x,
        y: pos.y,
        panelIndex,
        localX: pos.x,
        localY: pos.y,
      });
    });
  });
  mappingAssist.sequence = sequence;
  mappingAssist.cursor = Math.max(0, Math.min(Math.max(sequence.length - 1, 0), mappingAssist.cursor));
  updateMappingCoordinateRange();
}

function assistLogicalFromCursor(cursor) {
  if (!mappingAssist.sequence.length) rebuildMappingAssistSequence();
  if (!mappingAssist.sequence.length) return { x: 0, y: 0, panelIndex: 0, localX: 0, localY: 0 };
  const safeCursor = Math.max(0, Math.min(mappingAssist.sequence.length - 1, cursor));
  return mappingAssist.sequence[safeCursor];
}

function initMappingAssistConfigControls() {
  const panelCountEl = document.getElementById('assistPanelCount');
  const scopeEl = document.getElementById('assistPanelScope');
  const activePanelEl = document.getElementById('assistActivePanel');
  const scanModeEl = document.getElementById('assistScanMode');
  if (!panelCountEl || !scopeEl || !activePanelEl || !scanModeEl) return;

  panelCountEl.value = `${mappingAssist.panelCount}`;
  scopeEl.value = mappingAssist.scope;
  activePanelEl.value = `${mappingAssist.activePanel}`;
  scanModeEl.value = mappingAssist.panelScanModes[mappingAssist.activePanel] || 'row_ltr';

  const syncControlState = () => {
    const activePanel = Math.max(0, Math.min(MAX_PANEL_COUNT - 1, Number(activePanelEl.value) || 0));
    const count = Math.max(1, Math.min(MAX_PANEL_COUNT, Number(panelCountEl.value) || MAX_PANEL_COUNT));
    activePanelEl.querySelectorAll('option').forEach((opt) => {
      const panelIdx = Number(opt.value);
      opt.disabled = panelIdx >= count;
    });
    if (activePanel >= count) {
      activePanelEl.value = `${count - 1}`;
    }
    activePanelEl.disabled = scopeEl.value !== 'active';
    scanModeEl.value = mappingAssist.panelScanModes[Number(activePanelEl.value) || 0] || 'row_ltr';
  };

  panelCountEl.onchange = () => {
    mappingAssist.panelCount = Math.max(1, Math.min(MAX_PANEL_COUNT, Number(panelCountEl.value) || MAX_PANEL_COUNT));
    if (mappingAssist.activePanel >= mappingAssist.panelCount) mappingAssist.activePanel = mappingAssist.panelCount - 1;
    activePanelEl.value = `${mappingAssist.activePanel}`;
    syncControlState();
    rebuildMappingAssistSequence();
    renderMappingAssistState();
  };
  scopeEl.onchange = () => {
    mappingAssist.scope = scopeEl.value === 'active' ? 'active' : 'all';
    syncControlState();
    rebuildMappingAssistSequence();
    renderMappingAssistState();
  };
  activePanelEl.onchange = () => {
    mappingAssist.activePanel = Math.max(0, Math.min(MAX_PANEL_COUNT - 1, Number(activePanelEl.value) || 0));
    scanModeEl.value = mappingAssist.panelScanModes[mappingAssist.activePanel] || 'row_ltr';
    rebuildMappingAssistSequence();
    renderMappingAssistState();
  };
  scanModeEl.onchange = () => {
    const selectedMode = ASSIST_SCAN_MODES.includes(scanModeEl.value) ? scanModeEl.value : 'row_ltr';
    mappingAssist.panelScanModes[mappingAssist.activePanel] = selectedMode;
    rebuildMappingAssistSequence();
    renderMappingAssistState();
  };

  syncControlState();
}

function upsertDraftFix(entry) {
  const idx = mappingAssist.draftFixes.findIndex((item) => item.logical_x === entry.logical_x && item.logical_y === entry.logical_y);
  if (idx >= 0) mappingAssist.draftFixes[idx] = entry;
  else mappingAssist.draftFixes.push(entry);
}

function renderMappingAssistGridState() {
  const dims = mappingAssistDimensions();
  const current = mappingAssist.active ? assistLogicalFromCursor(mappingAssist.cursor) : null;
  const currentFix = current
    ? mappingAssist.draftFixes.find((item) => item.logical_x === current.x && item.logical_y === current.y)
    : null;

  for (let y = 0; y < LED_MATRIX_HEIGHT; y += 1) {
    for (let x = 0; x < LED_MATRIX_WIDTH; x += 1) {
      const el = document.getElementById(`assist-${x}-${y}`);
      if (!el) continue;
      const active = x < dims.width && y < dims.height;
      el.disabled = !active;
      el.style.opacity = active ? '1' : '0.2';
      el.classList.toggle('assist-current', !!current && current.x === x && current.y === y);
      el.classList.toggle('assist-picked', !!currentFix && currentFix.observed_x === x && currentFix.observed_y === y);
      const fixed = mappingAssist.draftFixes.some((item) => item.observed_x === x && item.observed_y === y);
      el.classList.toggle('assist-fixed', fixed);
    }
  }
}

function renderMappingFixesInfo() {
  const el = document.getElementById('mappingFixesInfo');
  if (!el) return;
  if (!mappingAssist.draftFixes.length) {
    el.innerText = 'Noch keine Fix-Pixel.';
    return;
  }
  const lines = [
    `Fix-Pixel (Entwurf): ${mappingAssist.draftFixes.length}`,
    `Bereits aktiv im Backend: ${mappingAssist.fixedPixels.length}`,
    'Format: logisch -> beobachtet',
  ];
  mappingAssist.draftFixes
    .slice()
    .sort((a, b) => (a.logical_y - b.logical_y) || (a.logical_x - b.logical_x))
    .forEach((item) => {
      lines.push(`(${item.logical_x},${item.logical_y}) -> (${item.observed_x},${item.observed_y})`);
    });
  lines.push('Editieren: gehe auf die logische LED im Assistenten und klicke eine neue beobachtete Position.');
  el.innerText = lines.join('\n');
}

async function loadMappingAssistFixes() {
  const data = await apiRequest('/api/debug/mapping/fixes');
  if (!data?.fixes) return;
  mappingAssist.fixedPixels = Array.isArray(data.fixes) ? data.fixes : [];
  mappingAssist.draftFixes = mappingAssist.fixedPixels.map((item) => ({ ...item }));
  renderMappingFixesInfo();
  renderMappingAssistGridState();
}

async function drawSingleLogicalPixel(x, y, seconds = 6) {
  const frame = Array.from({ length: LED_MATRIX_HEIGHT }, () => Array(LED_MATRIX_WIDTH).fill(0));
  frame[y][x] = 1;
  return apiRequest('/api/display/draw', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pixels: frame, seconds }),
  }, '');
}

function renderMappingAssistState() {
  const el = document.getElementById('mappingAssistState');
  if (!el) return;
  if (!mappingAssist.active) {
    el.innerText = 'Assistent noch nicht gestartet.';
    return;
  }
  const { x, y, panelIndex, localX, localY } = assistLogicalFromCursor(mappingAssist.cursor);
  const total = mappingAssist.sequence.length || 0;
  el.innerText = [
    `Schritt: ${mappingAssist.cursor + 1}/${total}`,
    `Leuchte jetzt: logische LED (${x},${y}) | Panel ${panelIndex + 1}, lokal (${localX},${localY})`,
    `Erfasste Beobachtungen: ${mappingAssist.observations.length} (Fixes Entwurf: ${mappingAssist.draftFixes.length})`,
    `Übersprungen: ${mappingAssist.skipped.length}`,
    `Panel-Setup: ${mappingAssist.panelCount}×8x8 | Bereich: ${mappingAssist.scope === 'active' ? `nur Panel ${mappingAssist.activePanel + 1}` : 'alle aktiven Panels'}`,
    'Klicke unten auf die LED-Position, die in echt leuchtet.',
  ].join('\n');
  renderMappingAssistGridState();
}

async function mappingAssistShowCurrent() {
  if (!mappingAssist.active) return;
  const { x, y } = assistLogicalFromCursor(mappingAssist.cursor);
  await drawSingleLogicalPixel(x, y, 3600);
  renderMappingAssistState();
  renderMappingFixesInfo();
}

function mappingAssistNext() {
  if (!mappingAssist.active) return;
  const maxIndex = Math.max(0, mappingAssist.sequence.length - 1);
  mappingAssist.cursor = Math.min(mappingAssist.cursor + 1, maxIndex);
  mappingAssistShowCurrent();
}

function mappingAssistPrev() {
  if (!mappingAssist.active) return;
  mappingAssist.cursor = Math.max(mappingAssist.cursor - 1, 0);
  mappingAssistShowCurrent();
}

function mappingAssistSkip() {
  if (!mappingAssist.active) return;
  mappingAssist.skipped.push(mappingAssist.cursor);
  mappingAssistNext();
}

async function startMappingAssist() {
  rebuildMappingAssistSequence();
  mappingAssist.active = true;
  mappingAssist.cursor = 0;
  mappingAssist.observations = [];
  mappingAssist.skipped = [];
  await loadMappingAssistFixes();
  renderMappingAssistResult(null);
  await mappingAssistShowCurrent();
}

function mappingAssistReset() {
  mappingAssist.active = false;
  mappingAssist.cursor = 0;
  mappingAssist.observations = [];
  mappingAssist.skipped = [];
  renderMappingAssistState();
  renderMappingAssistResult(null);
  renderMappingAssistGridState();
}

async function mappingAssistMarkObserved(observedX, observedY) {
  if (!mappingAssist.active) return;
  const dims = mappingAssistDimensions();
  if (observedX >= dims.width || observedY >= dims.height) return;
  const { x, y } = assistLogicalFromCursor(mappingAssist.cursor);
  const existing = mappingAssist.observations.findIndex((item) => item.logical_x === x && item.logical_y === y);
  const entry = { logical_x: x, logical_y: y, observed_x: observedX, observed_y: observedY };
  if (existing >= 0) mappingAssist.observations[existing] = entry;
  else mappingAssist.observations.push(entry);
  upsertDraftFix(entry);
  renderMappingFixesInfo();
  renderMappingAssistGridState();

  toast(`Beobachtung gespeichert: logisch (${x},${y}) -> real (${observedX},${observedY})`);
  if (mappingAssist.cursor < mappingAssist.sequence.length - 1) {
    mappingAssist.cursor += 1;
    await mappingAssistShowCurrent();
  } else {
    renderMappingAssistState();
  }
}

function renderMappingAssistResult(result) {
  const el = document.getElementById('mappingAssistResult');
  if (!el) return;
  if (!result) {
    el.innerText = 'Noch keine Mapping-Auswertung.';
    return;
  }
  const solutions = Array.isArray(result.solutions) ? result.solutions : [];
  if (!solutions.length) {
    el.innerText = [
      'Keine Lösung gefunden.',
      `Beobachtungen: ${result.observation_count || 0}`,
      'Erfasse mehr LEDs (idealerweise aus verschiedenen Panels/Zeilen).',
    ].join('\n');
    return;
  }
  const first = solutions[0];
  el.innerText = [
    `Lösungen gefunden: ${result.solutions_found}`,
    `Beste Lösung: offset=${first.first_pixel_offset}, data_starts_right=${first.data_starts_right}, serpentine=${first.serpentine}`,
    `panel_order=${(first.panel_order || []).join(',')}`,
    `panel_rotations=${(first.panel_rotations || []).join(',')}`,
    'Klicke "Live-Mapping anwenden", um diese Werte zu übernehmen.',
  ].join('\n');
}

async function inferMappingFromAssist() {
  if (!mappingAssist.observations.length) {
    toast('Keine Beobachtungen vorhanden', true);
    return;
  }
  const payload = { observations: mappingAssist.observations, max_solutions: 8 };
  const data = await apiRequest('/api/debug/mapping/infer', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }, 'Mapping-Auswertung fertig');
  if (!data?.result) return;

  renderMappingAssistResult(data.result);
  const best = data.result.solutions && data.result.solutions[0];
  if (best) {
    applyMappingToForm(best);
    renderRuntimeMappingInfo({
      ...(data.result.current_mapping || {}),
      ...best,
      active: true,
      source: 'inference_candidate',
    });
  }
}

async function applyMappingAssistFixes() {
  const payload = { fixes: mappingAssist.draftFixes };
  const data = await apiRequest('/api/debug/mapping/fixes', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }, 'Fix-Pixel live angewendet');
  if (!data?.fixes) return;
  mappingAssist.fixedPixels = Array.isArray(data.fixes) ? data.fixes : [];
  mappingAssist.draftFixes = mappingAssist.fixedPixels.map((item) => ({ ...item }));
  renderMappingFixesInfo();
  renderMappingAssistGridState();
  await refreshPreview();
  await refreshLiveMappingState({ silent: true });
}

async function clearMappingAssistFixes() {
  const data = await apiRequest('/api/debug/mapping/fixes', { method: 'DELETE' }, 'Fix-Pixel gelöscht');
  if (!data?.fixes) return;
  mappingAssist.fixedPixels = [];
  mappingAssist.draftFixes = [];
  mappingAssist.observations = [];
  renderMappingFixesInfo();
  renderMappingAssistGridState();
  await refreshPreview();
  await refreshLiveMappingState({ silent: true });
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

initTopNavigation();

if (document.body?.dataset.page === 'debug') {
  debugPanelLoadMessage('backendStatusSummary', 'Frontend JS geladen, lade Backend-Status…');
  debugPanelLoadMessage('serialDebugSummary', 'Frontend JS geladen, lade Arduino-Debugdaten…');
  window.addEventListener('error', (event) => {
    debugPanelLoadMessage(
      'backendStatusSummary',
      'Frontend-JS-Fehler',
      `${event.message || 'unbekannter Fehler'} @ ${event.filename || '-'}:${event.lineno || '-'}:${event.colno || '-'}`,
    );
  });
  window.addEventListener('unhandledrejection', (event) => {
    const reason = event?.reason;
    const text = typeof reason === 'string' ? reason : (reason?.message || JSON.stringify(reason));
    debugPanelLoadMessage('backendStatusSummary', 'Frontend Promise-Fehler', text || 'unbekannter Fehler');
  });
}

if (ensureAuthFlow()) {
  const { page, requiresAuth } = pageInfo();
  if (document.getElementById('grid')) initGrid();
  if (document.getElementById('previewGrid')) initPreviewGrid();
  if (document.getElementById('mappingAssistGrid')) initMappingAssistGrid();
  if (page === 'login') initLoginPage();

  if (requiresAuth && token) {
    if (page === 'modules') loadModules();
    if (page === 'overview') refreshStatus();
    if (page === 'tools') refreshPreview();
    if (page === 'mapping') {
      renderMappingAssistState();
      refreshLiveMappingState({ silent: true });
      loadMappingAssistFixes();
      refreshPreview();
    }
    if (page === 'debug') {
      refreshDhtDebug();
      refreshLedDebug({ silent: true });
      refreshStatus();
    }
    startPollingLoops();
  }
}
