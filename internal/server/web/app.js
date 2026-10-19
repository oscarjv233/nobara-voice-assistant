/* ==============================================================================
   Jarvis AI — Control Panel Client Logic (Vanilla JS)
   ============================================================================== */

let currentConfig = {};
let allConversations = [];
let selectedConvId = null;
let statusPollTimer = null;

document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  initSliders();
  initEventListeners();
  loadConfig();
  loadConversations();
  startStatusPolling();
  refreshHardwareInfo();
});

// Toast Notifications
function showToast(message) {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.classList.remove("hidden");
  setTimeout(() => {
    toast.classList.add("hidden");
  }, 2400);
}

// Navigation Tabs
function initTabs() {
  const navBtns = document.querySelectorAll(".nav-btn");
  navBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const tabName = btn.dataset.tab;
      navBtns.forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-pane").forEach((pane) => pane.classList.remove("active"));

      btn.classList.add("active");
      const targetPane = document.getElementById(`tab-${tabName}`);
      if (targetPane) targetPane.classList.add("active");
    });
  });
}

// Range Sliders display update
function initSliders() {
  const sliderTTS = document.getElementById("sliderTTSVol");
  const valTTS = document.getElementById("valTTSVol");
  sliderTTS.addEventListener("input", () => {
    valTTS.textContent = `${sliderTTS.value}%`;
  });

  const sliderSilence = document.getElementById("sliderSilence");
  const valSilence = document.getElementById("valSilence");
  sliderSilence.addEventListener("input", () => {
    valSilence.textContent = `${(sliderSilence.value / 10).toFixed(1)} s`;
  });

  const sliderSens = document.getElementById("sliderWakeSens");
  const valSens = document.getElementById("valWakeSens");
  sliderSens.addEventListener("input", () => {
    const thresh = sliderSens.value / 100;
    let label = `Normal (${thresh.toFixed(2)})`;
    if (thresh <= 0.22) label = `Alta (${thresh.toFixed(2)})`;
    else if (thresh >= 0.38) label = `Estricta (${thresh.toFixed(2)})`;
    valSens.textContent = label;
  });

  // Toggle wake container visibility
  const chkWake = document.getElementById("chkWakeWord");
  const wakeContainer = document.getElementById("wakeContainer");
  chkWake.addEventListener("change", () => {
    wakeContainer.style.opacity = chkWake.checked ? "1" : "0.5";
    wakeContainer.style.pointerEvents = chkWake.checked ? "auto" : "none";
  });
}

// Global Event Listeners
function initEventListeners() {
  document.getElementById("btnSaveGlobal").addEventListener("click", saveConfig);
  document.getElementById("btnNewSession").addEventListener("click", startNewSession);
  document.getElementById("btnRefreshConv").addEventListener("click", loadConversations);
  document.getElementById("convSearch").addEventListener("input", (e) => filterConversations(e.target.value));

  document.getElementById("btnResumeActive").addEventListener("click", resumeActiveSession);
  document.getElementById("btnCopyMarkdown").addEventListener("click", copyMarkdown);
  document.getElementById("btnDeleteConv").addEventListener("click", deleteSelectedConversation);

  document.getElementById("btnCopyActiveID").addEventListener("click", () => {
    const val = document.getElementById("liveActiveID").value;
    if (val && val !== "Ninguna") {
      navigator.clipboard.writeText(val);
      showToast("ID copiado al portapapeles");
    }
  });

  document.getElementById("btnCancelTask").addEventListener("click", cancelRunningTask);
  document.getElementById("btnRefreshHW").addEventListener("click", refreshHardwareInfo);
  document.getElementById("btnTestVoice").addEventListener("click", testVoice);
  document.getElementById("btnTestMic").addEventListener("click", testMic);
}

// Configuration Loader
async function loadConfig() {
  try {
    const res = await fetch("/api/config");
    if (!res.ok) throw new Error("Error loading config");
    const cfg = await res.json();
    currentConfig = cfg;

    // Apply to UI
    document.getElementById("chkEnabled").checked = cfg.Enabled;
    document.getElementById("selLanguage").value = cfg.AssistantLanguage || "es";

    const voiceVal = `${cfg.VoiceModel}:${cfg.VoiceSpeaker || ""}`;
    const selVoice = document.getElementById("selVoice");
    for (let opt of selVoice.options) {
      if (opt.value === voiceVal) {
        selVoice.value = voiceVal;
        break;
      }
    }

    const ttsVol = Math.round(cfg.TTSVolume * 100);
    document.getElementById("sliderTTSVol").value = ttsVol;
    document.getElementById("valTTSVol").textContent = `${ttsVol}%`;

    document.getElementById("chkVoiceReply").checked = cfg.EnableVoiceReply;
    document.getElementById("chkProcessingCue").checked = cfg.EnableProcessingVoiceCue;
    document.getElementById("selWhisperModel").value = cfg.WhisperModel || "base";
    document.getElementById("chkAutoStop").checked = cfg.AutoStopSilence;

    const silVal = Math.round(cfg.SilenceDuration * 10);
    document.getElementById("sliderSilence").value = silVal;
    document.getElementById("valSilence").textContent = `${(silVal / 10).toFixed(1)} s`;

    document.getElementById("chkContinuous").checked = cfg.ContinuousConversation;
    document.getElementById("chkAudioDucking").checked = cfg.AudioDucking;
    document.getElementById("chkWakeWord").checked = cfg.WakeWordEnabled;
    document.getElementById("selWakeModel").value = cfg.WakeWordModel || "hey_jarvis";

    const sensVal = Math.round(cfg.WakeWordThreshold * 100);
    document.getElementById("sliderWakeSens").value = sensVal;
    document.getElementById("valWakeSens").textContent = `${(sensVal / 100).toFixed(2)}`;

    document.getElementById("chkOverlayHUD").checked = cfg.OverlayHUDEnabled;
    document.getElementById("chkAutostart").checked = cfg.Autostart;

    // Active session ID
    const actId = cfg.ActiveConversationID || "Ninguna";
    document.getElementById("liveActiveID").value = actId;
  } catch (err) {
    console.error(err);
  }
}

// Save Configuration
async function saveConfig() {
  const voiceRaw = document.getElementById("selVoice").value.split(":");
  const voiceModel = voiceRaw[0];
  const voiceSpeaker = voiceRaw[1] || "";

  const payload = {
    Enabled: document.getElementById("chkEnabled").checked,
    AssistantLanguage: document.getElementById("selLanguage").value,
    VoiceModel: voiceModel,
    VoiceSpeaker: voiceSpeaker,
    TTSVolume: parseFloat(document.getElementById("sliderTTSVol").value) / 100,
    EnableVoiceReply: document.getElementById("chkVoiceReply").checked,
    EnableProcessingVoiceCue: document.getElementById("chkProcessingCue").checked,
    WhisperModel: document.getElementById("selWhisperModel").value,
    AutoStopSilence: document.getElementById("chkAutoStop").checked,
    SilenceDuration: parseFloat(document.getElementById("sliderSilence").value) / 10,
    ContinuousConversation: document.getElementById("chkContinuous").checked,
    AudioDucking: document.getElementById("chkAudioDucking").checked,
    WakeWordEnabled: document.getElementById("chkWakeWord").checked,
    WakeWordModel: document.getElementById("selWakeModel").value,
    WakeWordThreshold: parseFloat(document.getElementById("sliderWakeSens").value) / 100,
    OverlayHUDEnabled: document.getElementById("chkOverlayHUD").checked,
    Autostart: document.getElementById("chkAutostart").checked,
  };

  try {
    const res = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (res.ok) {
      showToast("Ajustes guardados correctamente");
    } else {
      showToast("Error al guardar ajustes");
    }
  } catch (err) {
    showToast("Error de conexión al guardar");
  }
}

// Conversations Loader
async function loadConversations() {
  try {
    const res = await fetch("/api/conversations");
    if (!res.ok) return;
    const data = await res.json();
    allConversations = data || [];
    filterConversations(document.getElementById("convSearch").value);
  } catch (err) {
    console.error(err);
  }
}

function filterConversations(query) {
  const listEl = document.getElementById("threadsList");
  listEl.innerHTML = "";

  query = (query || "").trim().toLowerCase();
  const activeID = currentConfig.ActiveConversationID || "";

  const matches = allConversations.filter((c) => {
    if (!query) return true;
    return (
      (c.title && c.title.toLowerCase().includes(query)) ||
      (c.last_user && c.last_user.toLowerCase().includes(query)) ||
      (c.last_reply && c.last_reply.toLowerCase().includes(query)) ||
      c.id.toLowerCase().includes(query)
    );
  });

  document.getElementById("threadsCount").textContent = `${matches.length} de ${allConversations.length} sesiones`;

  matches.forEach((conv) => {
    const item = document.createElement("div");
    item.className = `thread-item ${conv.id === selectedConvId ? "active" : ""}`;
    item.dataset.id = conv.id;

    const shortDate = conv.date_str ? conv.date_str.substring(0, 16) : "";
    const isActive = conv.id === activeID;

    item.innerHTML = `
      <div class="thread-meta-row">
        <span class="thread-date">${shortDate}</span>
        <div class="thread-pills">
          <span class="pill">${conv.turn_count || 1}t</span>
          ${isActive ? '<span class="pill pill-active">ACTIVA</span>' : ""}
        </div>
      </div>
      <div class="thread-title" title="${escapeHtml(conv.title)}">${escapeHtml(conv.title)}</div>
      <div class="thread-preview">${escapeHtml(conv.last_reply || conv.last_user || "Sin detalles")}</div>
    `;

    item.addEventListener("click", () => selectConversation(conv.id));
    listEl.appendChild(item);
  });
}

// Select Conversation and Render Detail
async function selectConversation(convId) {
  selectedConvId = convId;

  // Update active item styles in sidebar
  document.querySelectorAll(".thread-item").forEach((el) => {
    el.classList.toggle("active", el.dataset.id === convId);
  });

  const btnResume = document.getElementById("btnResumeActive");
  const btnCopy = document.getElementById("btnCopyMarkdown");
  const btnDelete = document.getElementById("btnDeleteConv");

  btnCopy.disabled = false;
  btnDelete.disabled = false;

  const isActive = convId === (currentConfig.ActiveConversationID || "");
  btnResume.disabled = isActive;
  btnResume.textContent = isActive ? "Sesión Activa" : "Fijar como Activa";

  try {
    const res = await fetch(`/api/conversations/${convId}`);
    if (!res.ok) return;
    const detail = await res.json();
    renderConversationDetail(detail);
  } catch (err) {
    console.error(err);
  }
}

// Render Conversation with Summary + Reverse Turns
function renderConversationDetail(detail) {
  const viewerTitle = document.getElementById("viewerTitle");
  const viewerSub = document.getElementById("viewerSub");
  const streamEl = document.getElementById("viewerStream");

  viewerTitle.textContent = detail.title || "Conversación";
  const turns = detail.turns || [];
  const summary = detail.summary || {};
  viewerSub.textContent = `ID: ${detail.id}  ·  ${turns.length} turnos registrados`;

  if (!turns.length) {
    streamEl.innerHTML = `<div class="empty-state"><p>No hay turnos registrados en esta sesión.</p></div>`;
    return;
  }

  const toolsStr = summary.tools_used && summary.tools_used.length ? summary.tools_used.join(", ") : "Ninguna";
  const lastUser = summary.last_user || (turns[turns.length - 1] ? turns[turns.length - 1].user : "");
  const lastReply = summary.last_reply || (turns[turns.length - 1] ? turns[turns.length - 1].reply : "");

  let htmlStr = `
    <div class="session-summary-box">
      <div class="summary-badge">RESUMEN DE LA SESIÓN</div>
      <div class="summary-row"><b>Última orden:</b> ${escapeHtml(lastUser || "Sin orden")}</div>
      <div class="summary-row"><b>Último resultado:</b> ${escapeHtml(lastReply || "Completado")}</div>
      <div class="summary-meta-line">
        <span>Turnos totales: <b>${turns.length}</b></span>
        <span>Herramientas invocadas: <b>${escapeHtml(toolsStr)}</b></span>
      </div>
    </div>
  `;

  // Render turns in reverse order (newest turn at the top!)
  const reversedTurns = [...turns].reverse();
  reversedTurns.forEach((turn, idx) => {
    const turnNum = turns.length - idx;
    const isLatest = idx === 0;

    let timeBadge = turn.time
      ? `<span class="turn-time-tag ${isLatest ? "latest" : ""}">Turno ${turnNum} ${isLatest ? "(Más reciente)" : ""} · ${turn.time}</span>`
      : `<span class="turn-time-tag">Turno ${turnNum}</span>`;

    htmlStr += `
      <div class="turn-container">
        <div class="turn-header">
          <span style="color: #38bdf8;">[USUARIO]</span>
          ${timeBadge}
        </div>
        <div class="user-card">
          <div class="user-text">${escapeHtml(turn.user)}</div>
        </div>
    `;

    if (turn.actions && turn.actions.length) {
      turn.actions.forEach((act) => {
        const detail = act.summary || act.cmd || "";
        htmlStr += `<div class="tool-chip">[HERRAMIENTA: ${escapeHtml(act.name)}] ${escapeHtml(detail)}</div>`;
      });
    }

    if (turn.reply) {
      htmlStr += `
        <div class="turn-header" style="margin-top: 6px;">
          <span style="color: #38bdf8;">[JARVIS]</span>
        </div>
        <div class="jarvis-card">
          <div class="jarvis-text">${formatText(turn.reply)}</div>
        </div>
      `;
    }

    htmlStr += `</div>`;
  });

  streamEl.innerHTML = htmlStr;
}

// Conversation Actions
async function startNewSession() {
  try {
    const res = await fetch("/api/conversations/new", { method: "POST" });
    if (res.ok) {
      const data = await res.json();
      currentConfig.ActiveConversationID = data.id;
      document.getElementById("liveActiveID").value = data.id;
      showToast(`Nueva sesión limpia iniciada (${data.id.substring(0, 8)})`);
      await loadConversations();
      selectConversation(data.id);
    }
  } catch (err) {
    showToast("Error iniciando sesión");
  }
}

async function resumeActiveSession() {
  if (!selectedConvId) return;
  try {
    const res = await fetch("/api/conversations/active", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: selectedConvId }),
    });
    if (res.ok) {
      currentConfig.ActiveConversationID = selectedConvId;
      document.getElementById("liveActiveID").value = selectedConvId;
      document.getElementById("btnResumeActive").disabled = true;
      document.getElementById("btnResumeActive").textContent = "Sesión Activa";
      showToast("Sesión fijada como activa");
      filterConversations(document.getElementById("convSearch").value);
    }
  } catch (err) {
    showToast("Error al fijar sesión");
  }
}

async function copyMarkdown() {
  if (!selectedConvId) return;
  try {
    const res = await fetch(`/api/conversations/${selectedConvId}/export`);
    if (res.ok) {
      const data = await res.json();
      navigator.clipboard.writeText(data.markdown);
      showToast("Markdown copiado al portapapeles");
    }
  } catch (err) {
    showToast("Error copiando markdown");
  }
}

async function deleteSelectedConversation() {
  if (!selectedConvId) return;
  if (!confirm(`¿Deseas eliminar permanentemente la sesión ${selectedConvId.substring(0, 8)}?`)) return;

  try {
    const res = await fetch(`/api/conversations/${selectedConvId}`, { method: "DELETE" });
    if (res.ok) {
      showToast("Sesión eliminada");
      selectedConvId = null;
      document.getElementById("viewerStream").innerHTML = `<div class="empty-state"><p>Sesión eliminada.</p></div>`;
      document.getElementById("btnResumeActive").disabled = true;
      document.getElementById("btnCopyMarkdown").disabled = true;
      document.getElementById("btnDeleteConv").disabled = true;
      loadConversations();
    }
  } catch (err) {
    showToast("Error al eliminar");
  }
}

// Live Status Polling
function startStatusPolling() {
  if (statusPollTimer) clearInterval(statusPollTimer);
  statusPollTimer = setInterval(async () => {
    try {
      const res = await fetch("/api/status");
      if (!res.ok) return;
      const st = await res.json();
      updateStatusUI(st);
    } catch (e) {}
  }, 1000);
}

function updateStatusUI(st) {
  const badge = document.getElementById("statusBadge");
  const statusText = document.getElementById("statusText");

  const liveTaskBadge = document.getElementById("liveTaskBadge");
  const liveTaskTime = document.getElementById("liveTaskTime");
  const liveProgressBar = document.getElementById("liveProgressBar");
  const liveUserText = document.getElementById("liveUserText");
  const liveActionText = document.getElementById("liveActionText");
  const liveCommandBox = document.getElementById("liveCommandBox");
  const liveCommandText = document.getElementById("liveCommandText");
  const btnCancelTask = document.getElementById("btnCancelTask");

  if (st.status === "RUNNING") {
    badge.className = "status-badge status-running";
    statusText.textContent = "EJECUTANDO";

    liveTaskBadge.className = "badge badge-warning";
    liveTaskBadge.textContent = `Ejecutando (PID ${st.pid || ""})`;
    const elapsed = st.started_at ? Math.round(Date.now() / 1000 - st.started_at) : 0;
    liveTaskTime.textContent = `Tiempo transcurrido: ${elapsed}s`;

    liveProgressBar.classList.remove("hidden");
    btnCancelTask.disabled = false;

    liveUserText.textContent = st.user_text || "Comando de voz";
    liveActionText.textContent = st.current_action || "Procesando...";

    if (st.tool_detail) {
      liveCommandText.textContent = `$ ${st.tool_detail}`;
      liveCommandBox.classList.remove("hidden");
    } else {
      liveCommandBox.classList.add("hidden");
    }
  } else {
    badge.className = "status-badge status-idle";
    statusText.textContent = "En reposo";

    liveTaskBadge.className = "badge badge-success";
    liveTaskBadge.textContent = "En reposo (IDLE)";
    liveTaskTime.textContent = "";

    liveProgressBar.classList.add("hidden");
    btnCancelTask.disabled = true;

    liveUserText.textContent = st.last_user_text || "Ninguna";
    liveActionText.textContent = st.last_action || "Esperando comando de voz";
    liveCommandBox.classList.add("hidden");
  }
}

async function cancelRunningTask() {
  try {
    const res = await fetch("/api/task/cancel", { method: "POST" });
    if (res.ok) {
      showToast("Tarea cancelada correctamente");
    }
  } catch (err) {
    showToast("Error al cancelar tarea");
  }
}

async function refreshHardwareInfo() {
  try {
    const res = await fetch("/api/hardware");
    if (!res.ok) return;
    const data = await res.json();
    document.getElementById("metricGPU").textContent = data.gpu_temp ? `${data.gpu_temp} °C` : "--";
    document.getElementById("metricCPU").textContent = data.cpu_temp ? `${data.cpu_temp} °C` : "--";
    document.getElementById("metricVol").textContent = data.volume !== undefined ? `${data.volume}%` : "--";
    document.getElementById("hwStatusMsg").textContent = data.summary || "Sensores operando en rangos normales.";
  } catch (e) {}
}

async function testVoice() {
  const voiceRaw = document.getElementById("selVoice").value.split(":");
  const payload = {
    model: voiceRaw[0],
    speaker: voiceRaw[1] || "",
    volume: parseFloat(document.getElementById("sliderTTSVol").value) / 100,
  };
  showToast("Reproduciendo muestra de voz...");
  try {
    await fetch("/api/test/voice", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (e) {}
}

async function testMic() {
  const btn = document.getElementById("btnTestMic");
  const resultBox = document.getElementById("micTestResult");

  btn.disabled = true;
  btn.textContent = "Grabando 3 segundos... Habla ahora";
  resultBox.className = "test-result-box";
  resultBox.textContent = "Escuchando tu voz...";

  try {
    const res = await fetch("/api/test/mic", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: document.getElementById("selWhisperModel").value,
        lang: document.getElementById("selLanguage").value,
      }),
    });
    const data = await res.json();
    btn.disabled = false;
    btn.textContent = "Probar Micrófono (3 segundos)";

    if (data.text) {
      resultBox.className = "test-result-box success";
      resultBox.textContent = `Reconocido: "${data.text}"`;
    } else {
      resultBox.className = "test-result-box error";
      resultBox.textContent = "No se detectó voz clara. Comprueba que el micrófono esté activo.";
    }
  } catch (e) {
    btn.disabled = false;
    btn.textContent = "Probar Micrófono (3 segundos)";
    resultBox.className = "test-result-box error";
    resultBox.textContent = "Error al ejecutar prueba de micrófono.";
  }
}

// Helpers
function escapeHtml(text) {
  if (!text) return "";
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function formatText(text) {
  if (!text) return "";
  let esc = escapeHtml(text);
  esc = esc.replace(/```(?:[a-zA-Z0-9_\-]+)?\n?(.*?)```/gs, (m, code) => {
    return `<div class="code-box"><pre><code>${code.trim()}</code></pre></div>`;
  });
  esc = esc.replace(/`([^`\n]+)`/g, '<code class="inline-code">$1</code>');
  esc = esc.replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
  esc = esc.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, "<i>$1</i>");
  esc = esc.replace(/\n/g, "<br/>");
  return esc;
}
