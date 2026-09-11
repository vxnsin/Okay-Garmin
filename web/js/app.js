/* Okay-Garmin settings window. */

const METER_BARS = 32;

let config = null;
let saveTimer = null;
let updateInfo = null;
let currentState = "starting";
let appInfo = { wake_word: "okay garmin" };
let placing = false;

const $ = (id) => document.getElementById(id);

const ICONS = {
  file: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>',
  folder:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>',
  run: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>',
  play: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>',
  trash:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>',
};

/* ------------------------------------------------------------------ toasts */

function toast(message, kind) {
  const el = document.createElement("div");
  el.className = "toast" + (kind ? " " + kind : "");
  el.textContent = message;
  $("toasts").appendChild(el);
  setTimeout(() => el.remove(), 3200);
}

/* ------------------------------------------------------------------ saving */

function save(immediate) {
  clearTimeout(saveTimer);
  const write = async () => {
    try {
      await window.pywebview.api.save_config(config);
    } catch (e) {
      console.error("Save failed", e);
      toast(I18n.t("toast.model_error"), "bad");
    }
  };
  // Typing in a text field would otherwise cross the bridge on every keystroke.
  // Returning the promise lets callers that depend on the saved value -- such
  // as starting Spotify authorisation with a freshly typed client ID -- wait.
  if (immediate) return write();
  saveTimer = setTimeout(write, 400);
  return Promise.resolve();
}

/* ---------------------------------------------------------------- navigation */

function showPage(name) {
  document.querySelectorAll(".page").forEach((p) => p.classList.toggle("active", p.id === "page-" + name));
  document.querySelectorAll(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.page === name));
}

/* -------------------------------------------------------------------- meter */

function buildMeter() {
  const meter = $("meter");
  meter.innerHTML = "";
  for (let i = 0; i < METER_BARS; i++) {
    const bar = document.createElement("i");
    // A gentle curve so quiet speech still lights a visible number of bars.
    bar.style.height = 30 + Math.sin((i / METER_BARS) * Math.PI) * 70 + "%";
    meter.appendChild(bar);
  }
}

function paintMeter(level) {
  const lit = Math.round(Math.min(1, level * 1.6) * METER_BARS);
  const bars = $("meter").children;
  for (let i = 0; i < bars.length; i++) {
    bars[i].className = i < lit ? (i > METER_BARS * 0.85 ? "peak" : "on") : "";
  }
}

/* ------------------------------------------------------------------- status */

const DOT_CLASS = {
  listening: "live",
  armed: "busy",
  recording: "busy",
  transcribing: "busy",
  executing: "busy",
  downloading: "warn",
  starting: "warn",
  paused: "",
  error: "bad",
};

function renderState(state) {
  currentState = state;
  const label = I18n.t("state." + state);
  $("stateText").textContent = label;
  $("sideState").textContent = label;
  const cls = "dot " + (DOT_CLASS[state] || "");
  $("stateDot").className = cls;
  $("sideDot").className = cls;

  const paused = state === "paused";
  $("pauseBtn").textContent = I18n.t(paused ? "overview.resume" : "overview.pause");
  if (!paused && state !== "error") paintHint();
}

function paintHint() {
  if (!config) return;
  const hint = $("stateHint");
  hint.textContent = I18n.t("overview.wake_hint", { wake: appInfo.wake_word });
  if (!config.push_to_talk.enabled) return;

  // Substitute a sentinel, then split on it, so the hotkey renders as a <kbd>
  // wherever the translation happens to place it.
  const SENTINEL = "%%KEY%%";
  const [before, after] = I18n.t("overview.ptt_hint", { hotkey: SENTINEL }).split(SENTINEL);
  hint.appendChild(document.createTextNode(" " + before));
  const kbd = document.createElement("kbd");
  kbd.textContent = config.push_to_talk.hotkey;
  hint.appendChild(kbd);
  if (after) hint.appendChild(document.createTextNode(after));
}

function renderHistory(entries) {
  const list = $("historyList");
  list.innerHTML = "";
  if (!entries || !entries.length) {
    const note = document.createElement("div");
    note.className = "empty-note";
    note.textContent = I18n.t("overview.history_empty");
    list.appendChild(note);
    return;
  }
  entries
    .slice()
    .reverse()
    .forEach((entry) => {
      const row = document.createElement("div");
      row.className = "history-item";

      const said = document.createElement("span");
      said.className = "said" + (entry.text ? "" : " empty");
      said.textContent = entry.text || "—";
      row.appendChild(said);

      const tag = document.createElement("span");
      tag.className = "tag " + (entry.matched ? "hit" : "miss");
      tag.textContent = entry.matched
        ? entry.matched + " · " + Math.round((entry.score || 0) * 100) + "%"
        : I18n.t("overview.no_match");
      row.appendChild(tag);

      list.appendChild(row);
    });
}

/* ----------------------------------------------------------------- commands */

function renderCommands() {
  const list = $("commandList");
  list.innerHTML = "";

  if (!config.voice_commands.length) {
    const note = document.createElement("div");
    note.className = "card empty-note";
    note.textContent = I18n.t("commands.empty");
    list.appendChild(note);
    return;
  }

  config.voice_commands.forEach((cmd, index) => {
    list.appendChild(buildCommandRow(cmd, index));
  });
}

function field(labelKey, control) {
  const wrap = document.createElement("div");
  wrap.className = "field";
  const label = document.createElement("label");
  label.textContent = I18n.t(labelKey);
  wrap.appendChild(label);
  wrap.appendChild(control);
  return wrap;
}

function buildCommandRow(cmd, index) {
  const row = document.createElement("div");
  row.className = "command" + (cmd.enabled === false ? " off" : "");

  // Spoken phrase
  const phrase = document.createElement("input");
  phrase.type = "text";
  phrase.value = cmd.command || "";
  phrase.placeholder = I18n.t("commands.phrase_ph");
  phrase.title = I18n.t("commands.slot_hint");
  // "spiel" with no {} can never carry a song name -- say so rather than
  // letting it fail silently at runtime.
  if (cmd.type === "spotify" && SLOT_ACTIONS.has(cmd.value) && !(cmd.command || "").includes("{}")) {
    phrase.classList.add("warn");
    phrase.title = I18n.t("commands.slot_required");
  }
  phrase.addEventListener("input", () => {
    config.voice_commands[index].command = phrase.value;
    save();
  });
  row.appendChild(field("commands.phrase", phrase));

  // Action type
  const type = document.createElement("select");
  ["hotkey", "media", "spotify", "file", "folder", "run"].forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = I18n.t("type." + value);
    option.selected = cmd.type === value;
    type.appendChild(option);
  });
  type.addEventListener("change", () => {
    const command = config.voice_commands[index];
    command.type = type.value;
    // Give the new type a valid default rather than an empty value it cannot use.
    command.value = DEFAULT_VALUE[type.value] ?? "";
    renderCommands();
    save(true);
  });
  row.appendChild(field("commands.type", type));

  // Value: hotkey recorder or path picker
  row.appendChild(field("type." + (cmd.type || "hotkey"), buildValueControl(cmd, index)));

  // Delay -- v1 never initialised this, so new commands showed "undefined".
  const delay = document.createElement("input");
  delay.type = "number";
  delay.min = "0";
  delay.step = "0.5";
  delay.value = cmd.delay ?? 0;
  delay.addEventListener("input", () => {
    config.voice_commands[index].delay = parseFloat(delay.value) || 0;
    save();
  });
  row.appendChild(field("commands.delay", delay));

  // Actions
  const actions = document.createElement("div");
  actions.className = "command-actions";

  const enabled = document.createElement("label");
  enabled.className = "switch";
  enabled.title = I18n.t("commands.enabled");
  const enabledInput = document.createElement("input");
  enabledInput.type = "checkbox";
  enabledInput.checked = cmd.enabled !== false;
  enabledInput.addEventListener("change", () => {
    config.voice_commands[index].enabled = enabledInput.checked;
    row.classList.toggle("off", !enabledInput.checked);
    save(true);
  });
  enabled.appendChild(enabledInput);
  enabled.appendChild(document.createElement("span"));
  actions.appendChild(enabled);

  const test = document.createElement("button");
  test.className = "btn icon";
  test.title = I18n.t("commands.test");
  test.innerHTML = ICONS.play;
  test.addEventListener("click", async () => {
    const result = await window.pywebview.api.test_command(index);
    if (result.status === "needs-speech") toast(I18n.t("toast.test_needs_speech"));
    else toast(I18n.t("toast.test_started"), "good");
  });
  actions.appendChild(test);

  const remove = document.createElement("button");
  remove.className = "btn icon danger";
  remove.title = I18n.t("commands.delete");
  remove.innerHTML = ICONS.trash;
  remove.addEventListener("click", () => {
    config.voice_commands.splice(index, 1);
    renderCommands();
    save(true);
  });
  actions.appendChild(remove);

  row.appendChild(actions);

  // Aliases span the full width underneath
  const aliases = document.createElement("input");
  aliases.type = "text";
  aliases.value = (cmd.aliases || []).join(", ");
  aliases.placeholder = I18n.t("commands.aliases_ph");
  aliases.addEventListener("input", () => {
    config.voice_commands[index].aliases = aliases.value
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    save();
  });
  const aliasField = field("commands.aliases", aliases);
  aliasField.classList.add("aliases-row");
  row.appendChild(aliasField);

  return row;
}

const DEFAULT_VALUE = {
  hotkey: "",
  media: "play_pause",
  spotify: "play",
  file: "",
  folder: "",
  run: "",
};

const CHOICES = {
  media: ["play_pause", "next", "previous", "volume_up", "volume_down", "mute"],
  spotify: [
    "play",
    "queue",
    "pause",
    "resume",
    "next",
    "previous",
    "current",
    "shuffle_on",
    "shuffle_off",
    "shuffle_toggle",
    "repeat_all",
    "repeat_track",
    "repeat_off",
    "repeat_cycle",
    "like",
    "unlike",
    "like_toggle",
    "volume_up",
    "volume_down",
  ],
};

// Only these two read the {} slot; the rest act on whatever is already playing.
const SLOT_ACTIONS = new Set(["play", "queue"]);

function buildChoiceControl(cmd, index) {
  const select = document.createElement("select");
  CHOICES[cmd.type].forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = I18n.t(cmd.type + "." + value);
    option.selected = cmd.value === value;
    select.appendChild(option);
  });
  select.addEventListener("change", () => {
    config.voice_commands[index].value = select.value;
    save(true);
  });
  return select;
}

function buildValueControl(cmd, index) {
  if (CHOICES[cmd.type]) return buildChoiceControl(cmd, index);

  if ((cmd.type || "hotkey") === "hotkey") {
    const input = document.createElement("input");
    input.type = "text";
    input.className = "hotkey-input";
    input.readOnly = true;
    input.value = cmd.value || "";
    input.placeholder = I18n.t("commands.record");
    input.addEventListener("click", () => {
      recordHotkey(
        input,
        (combo) => {
          config.voice_commands[index].value = combo;
          save(true);
        },
        () => I18n.t("commands.recording"),
      );
    });
    return input;
  }

  const wrap = document.createElement("div");
  wrap.className = "with-button";

  const input = document.createElement("input");
  input.type = "text";
  input.readOnly = true;
  input.value = cmd.value || "";
  input.placeholder = I18n.t("ph." + cmd.type);
  wrap.appendChild(input);

  const browse = document.createElement("button");
  browse.className = "btn icon";
  browse.title = I18n.t("commands.browse");
  browse.innerHTML = ICONS[cmd.type] || ICONS.file;
  browse.addEventListener("click", async () => {
    const path = await window.pywebview.api.pick_path(cmd.type);
    if (path) {
      config.voice_commands[index].value = path;
      input.value = path;
      save(true);
    }
  });
  wrap.appendChild(browse);

  return wrap;
}

/* -------------------------------------------------------------------- forms */

function bindToggle(id, read, write) {
  const el = $(id);
  el.checked = read();
  el.addEventListener("change", () => {
    write(el.checked);
    save(true);
  });
}

function bindValue(id, read, write, event) {
  const el = $(id);
  el.value = read();
  el.addEventListener(event || "change", () => {
    write(el.value);
    save(event === "input");
  });
}

function fillForms() {
  $("uiLanguage").value = config.ui_language;
  $("themeSelect").value = config.theme;
  $("soundToggle").checked = config.sound_enabled;
  $("notifyToggle").checked = config.notifications_enabled;

  $("sttLanguage").value = config.stt.language;
  $("whisperModel").value = config.stt.whisper_model;
  $("threshold").value = config.match_threshold;
  $("thresholdValue").textContent = Number(config.match_threshold).toFixed(2);
  $("commandTimeout").value = config.command_timeout;
  $("cooldown").value = config.cooldown;

  $("pttToggle").checked = config.push_to_talk.enabled;
  $("pttHotkey").value = config.push_to_talk.hotkey;
  $("pttHotkeyRow").classList.toggle("disabled", !config.push_to_talk.enabled);

  $("overlayToggle").checked = config.overlay.enabled;
  $("overlayPosition").value = config.overlay.position;
  $("overlayScale").value = config.overlay.scale;
  $("overlayScaleValue").textContent = Math.round(config.overlay.scale * 100) + "%";
  $("spotifyClientId").value = config.spotify.client_id || "";
  paintOverlayRows();
}

function paintOverlayRows() {
  const enabled = config.overlay.enabled;
  ["overlayPositionRow", "overlayScaleRow", "overlayPlaceRow"].forEach((id) => {
    $(id).classList.toggle("disabled", !enabled);
  });
  // A hand-placed HUD ignores the preset corners, so say so instead of
  // leaving a control that silently does nothing.
  const custom = Boolean(config.overlay.custom);
  $("overlayPosition").disabled = custom;
  $("overlayCustomNote").hidden = !custom;
  $("overlayResetBtn").hidden = !custom;
}

function wireForms() {
  $("uiLanguage").addEventListener("change", (e) => {
    config.ui_language = e.target.value;
    I18n.setLanguage(config.ui_language);
    rerenderAll();
    save(true);
  });

  $("themeSelect").addEventListener("change", (e) => {
    config.theme = e.target.value;
    document.documentElement.dataset.theme = config.theme;
    save(true);
  });

  bindToggle("soundToggle", () => config.sound_enabled, (v) => (config.sound_enabled = v));
  bindToggle("notifyToggle", () => config.notifications_enabled, (v) => (config.notifications_enabled = v));

  bindValue("sttLanguage", () => config.stt.language, (v) => (config.stt.language = v));
  bindValue("whisperModel", () => config.stt.whisper_model, (v) => (config.stt.whisper_model = v));
  bindValue("commandTimeout", () => config.command_timeout, (v) => (config.command_timeout = parseFloat(v) || 6));
  bindValue("cooldown", () => config.cooldown, (v) => (config.cooldown = parseFloat(v) || 0));

  $("threshold").addEventListener("input", (e) => {
    config.match_threshold = parseFloat(e.target.value);
    $("thresholdValue").textContent = config.match_threshold.toFixed(2);
    save();
  });

  $("inputDevice").addEventListener("change", (e) => {
    config.input_device = e.target.value === "" ? null : parseInt(e.target.value, 10);
    save(true);
  });

  $("pttToggle").addEventListener("change", (e) => {
    config.push_to_talk.enabled = e.target.checked;
    $("pttHotkeyRow").classList.toggle("disabled", !e.target.checked);
    paintHint();
    save(true);
  });

  $("pttHotkey").addEventListener("click", () => {
    recordHotkey(
      $("pttHotkey"),
      (combo) => {
        config.push_to_talk.hotkey = combo;
        paintHint();
        save(true);
      },
      () => I18n.t("commands.recording"),
    );
  });

  $("overlayToggle").addEventListener("change", (e) => {
    config.overlay.enabled = e.target.checked;
    paintOverlayRows();
    save(true);
  });

  bindValue("overlayPosition", () => config.overlay.position, (v) => (config.overlay.position = v));

  $("overlayScale").addEventListener("input", (e) => {
    config.overlay.scale = parseFloat(e.target.value);
    $("overlayScaleValue").textContent = Math.round(config.overlay.scale * 100) + "%";
    save();
  });

  $("overlayPreviewBtn").addEventListener("click", () => window.pywebview.api.preview_overlay());

  $("overlayPlaceBtn").addEventListener("click", async () => {
    if (placing) {
      await window.pywebview.api.end_overlay_placement();
      return;
    }
    const result = await window.pywebview.api.start_overlay_placement();
    if (result.status === "ok") {
      placing = true;
      $("overlayPlaceBtn").textContent = I18n.t("voice.overlay_place_stop");
      toast(I18n.t("toast.placement_on"));
    }
  });

  $("overlayResetBtn").addEventListener("click", () => {
    config.overlay.custom = false;
    config.overlay.x = null;
    config.overlay.y = null;
    paintOverlayRows();
    save(true);
  });

  $("spotifyClientId").addEventListener("input", (e) => {
    config.spotify.client_id = e.target.value.trim();
    save();
  });

  $("spotifyConnectBtn").addEventListener("click", async () => {
    await save(true);
    const result = await window.pywebview.api.connect_spotify();
    if (result.status === "error") toast(I18n.t("music.need_client_id"), "bad");
    else toast(I18n.t("music.check_browser"));
  });

  $("spotifyDisconnectBtn").addEventListener("click", async () => {
    await window.pywebview.api.disconnect_spotify();
    refreshSpotify();
  });

  $("spotifyDashboardBtn").addEventListener("click", () => {
    window.pywebview.api.open_external("https://developer.spotify.com/dashboard");
  });

  $("autostartToggle").addEventListener("change", async (e) => {
    const result = await window.pywebview.api.set_autostart(e.target.checked);
    if (result.enabled !== e.target.checked) e.target.checked = result.enabled;
  });

  $("pauseBtn").addEventListener("click", async () => {
    const status = await window.pywebview.api.get_status();
    await window.pywebview.api.set_paused(!status.paused);
  });

  $("addCommandBtn").addEventListener("click", () => {
    config.voice_commands.push({
      command: "",
      aliases: [],
      type: "hotkey",
      value: "",
      delay: 0,
      enabled: true,
    });
    renderCommands();
    save(true);
  });

  $("modelDownloadBtn").addEventListener("click", async () => {
    $("modelDownloadBtn").disabled = true;
    $("modelDownloadBtn").textContent = I18n.t("overview.downloading");
    $("modelProgress").hidden = false;
    await window.pywebview.api.download_models();
  });

  $("checkUpdateBtn").addEventListener("click", checkUpdates);
  $("updateBtn").addEventListener("click", runUpdate);
  $("openLogsBtn").addEventListener("click", () => window.pywebview.api.open_logs());
  $("repoBtn").addEventListener("click", () => {
    window.pywebview.api.open_external(updateInfo?.repo || "https://github.com/vxnsin/Okay-Garmin");
  });

  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.addEventListener("click", () => showPage(btn.dataset.page));
  });
}

/* ------------------------------------------------------------------ spotify */

async function refreshSpotify() {
  const status = await window.pywebview.api.get_spotify_status();
  const connected = status.connected;
  $("spotifyBadge").textContent = I18n.t(connected ? "music.connected" : "music.not_connected");
  $("spotifyBadge").classList.toggle("badge-secondary", !connected);
  $("spotifyStatusText").textContent = I18n.t(
    connected ? "music.connected_desc" : "music.not_connected_desc",
  );
  $("spotifyConnectBtn").hidden = connected;
  $("spotifyDisconnectBtn").hidden = !connected;
  $("spotifyRedirect").textContent = status.redirect_uri;
}

/* ------------------------------------------------------------------ updates */

async function checkUpdates() {
  const button = $("checkUpdateBtn");
  button.disabled = true;
  button.textContent = I18n.t("about.checking");
  try {
    updateInfo = await window.pywebview.api.get_version();
    renderUpdate(updateInfo);
  } finally {
    button.disabled = false;
    button.textContent = I18n.t("about.check");
  }
}

function renderUpdate(info) {
  if (!info) return;
  updateInfo = info;
  $("aboutVersion").textContent = info.current;
  $("sideVersion").textContent = info.current;
  $("aboutLatest").textContent = info.checked ? info.latest : I18n.t("about.offline");
  $("updateBanner").hidden = !info.checked;
  $("sideUpdate").hidden = !info.update_available;
  $("updateBtn").hidden = !info.update_available;
  $("updateBanner").classList.toggle("warn", info.update_available);
  if (info.checked) {
    $("updateText").textContent = info.update_available
      ? I18n.t("about.update_available", { version: info.latest })
      : I18n.t("about.up_to_date");
  }
}

async function runUpdate() {
  const result = await window.pywebview.api.run_updater();
  if (result.status === "ok") toast(I18n.t("toast.update_started"));
  else toast(I18n.t("toast.update_failed"), "bad");
}

/* ------------------------------------------------------------------- models */

function renderModels(status) {
  const ready = status.vosk.available && status.whisper.available;
  $("modelBanner").hidden = ready;
  if (ready) return;

  const missing = [];
  if (!status.vosk.available) missing.push("Vosk " + status.vosk.language + " (" + status.vosk.size_mb + " MB)");
  if (!status.whisper.available) missing.push("Whisper " + status.whisper.size + " (" + status.whisper.size_mb + " MB)");
  $("modelBannerText").textContent = I18n.t("overview.models_missing") + ": " + missing.join(", ");
}

/* -------------------------------------------------------------------- events */

window.ogEvent = function (event) {
  switch (event.type) {
    case "level":
      paintMeter(event.level);
      break;
    case "state":
      renderState(event.state);
      if (event.state === "error" && event.error) {
        $("stateHint").textContent = event.error;
      }
      break;
    case "transcript":
      refreshHistory();
      break;
    case "model_progress": {
      const bar = $("modelProgress");
      bar.hidden = false;
      // Whisper reports no byte progress, so show an indeterminate bar for it.
      bar.classList.toggle("indeterminate", event.stage === "whisper");
      bar.firstElementChild.style.width = Math.round(event.progress * 100) + "%";
      $("modelBannerText").textContent = event.message;
      break;
    }
    case "models_ready":
      $("modelBanner").hidden = true;
      toast(I18n.t("toast.models_ready"), "good");
      break;
    case "model_error":
      $("modelDownloadBtn").disabled = false;
      $("modelDownloadBtn").textContent = I18n.t("overview.download");
      $("modelProgress").hidden = true;
      toast(I18n.t("toast.model_error") + ": " + event.error, "bad");
      break;
    case "update_info":
      renderUpdate(event);
      break;
    case "spotify_connected":
      refreshSpotify();
      toast(I18n.t("music.connected"), "good");
      break;
    case "spotify_auth_error":
      toast(I18n.t("music.connect_failed") + ": " + event.error, "bad");
      break;
    case "placement_ended":
      placing = false;
      $("overlayPlaceBtn").textContent = I18n.t("voice.overlay_place_start");
      config.overlay.custom = true;
      paintOverlayRows();
      break;
  }
};

async function refreshHistory() {
  const status = await window.pywebview.api.get_status();
  renderHistory(status.history);
}

function rerenderAll() {
  I18n.apply();
  fillForms();
  renderCommands();
  renderState(currentState);
  paintHint();
  refreshHistory();
}

/* --------------------------------------------------------------------- boot */

async function boot() {
  config = await window.pywebview.api.get_config();

  await I18n.load();
  I18n.setLanguage(config.ui_language);
  document.documentElement.dataset.theme = config.theme;

  buildMeter();
  fillForms();
  wireForms();
  renderCommands();
  paintHint();

  // Microphones
  const devices = await window.pywebview.api.get_devices();
  const select = $("inputDevice");
  const auto = document.createElement("option");
  auto.value = "";
  auto.textContent = I18n.t("voice.device_default");
  select.appendChild(auto);
  devices.forEach((device) => {
    const option = document.createElement("option");
    option.value = String(device.index);
    option.textContent = device.name;
    select.appendChild(option);
  });
  select.value = config.input_device === null || config.input_device === undefined ? "" : String(config.input_device);

  // Autostart is meaningless when running from source.
  const info = await window.pywebview.api.get_app_info();
  appInfo = info;
  paintHint();
  $("aboutConfig").textContent = info.config_path;
  $("aboutLogs").textContent = info.log_path;
  $("aboutVersion").textContent = info.version;
  $("sideVersion").textContent = info.version;
  if (!info.frozen) {
    $("autostartRow").classList.add("disabled");
    $("autostartToggle").disabled = true;
    $("autostartRow").querySelector(".row-desc").textContent = I18n.t("setting.autostart_unsupported");
  } else {
    $("autostartToggle").checked = await window.pywebview.api.get_autostart();
  }

  const status = await window.pywebview.api.get_status();
  renderState(status.state);
  renderHistory(status.history);

  renderModels(await window.pywebview.api.get_models_status());
  refreshSpotify();
}

window.addEventListener("pywebviewready", boot);
