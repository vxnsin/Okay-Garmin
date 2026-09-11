/* Recording a key combination.

   v1's recorder had two bugs: on key-up it deleted "Win" from a set that only
   ever contained "windows", so the Windows key stuck; and releasing a modifier
   before the main key rebuilt the label from a half-empty set, losing it.
   This version keeps one ordered model and only reads from it. */

const MODIFIER_KEYS = {
  Control: "ctrl",
  Alt: "alt",
  AltGraph: "alt",
  Shift: "shift",
  Meta: "windows",
};

const MODIFIER_ORDER = ["ctrl", "alt", "shift", "windows"];

const NAMED_KEYS = {
  " ": "space",
  Escape: "esc",
  Enter: "enter",
  Tab: "tab",
  Backspace: "backspace",
  Delete: "delete",
  Insert: "insert",
  Home: "home",
  End: "end",
  PageUp: "pageup",
  PageDown: "pagedown",
  ArrowUp: "up",
  ArrowDown: "down",
  ArrowLeft: "left",
  ArrowRight: "right",
  PrintScreen: "printscreen",
  CapsLock: "capslock",
};

function keyName(event) {
  if (NAMED_KEYS[event.key]) return NAMED_KEYS[event.key];
  if (/^F\d{1,2}$/.test(event.key)) return event.key.toLowerCase();
  if (event.key.length === 1) return event.key.toLowerCase();
  return null;
}

function formatCombo(modifiers, mainKey) {
  const parts = MODIFIER_ORDER.filter((m) => modifiers.has(m));
  if (mainKey) parts.push(mainKey);
  return parts.join("+");
}

/**
 * Record a combination into `input`.
 * @param {HTMLInputElement} input
 * @param {(combo: string) => void} onDone  called with the final combo
 * @param {() => string} placeholderText    label shown while recording
 */
function recordHotkey(input, onDone, placeholderText) {
  if (input.classList.contains("recording")) return;

  const previous = input.value;
  const modifiers = new Set();
  let mainKey = null;
  let recording = true;

  input.classList.add("recording");
  input.value = placeholderText ? placeholderText() : "...";

  function paint() {
    input.value = formatCombo(modifiers, mainKey) || (placeholderText ? placeholderText() : "...");
  }

  function onKeyDown(event) {
    if (!recording) return;
    event.preventDefault();
    event.stopPropagation();

    if (event.key === "Escape" && !modifiers.size) {
      cancel();
      return;
    }
    if (MODIFIER_KEYS[event.key]) {
      modifiers.add(MODIFIER_KEYS[event.key]);
      paint();
      return;
    }
    const name = keyName(event);
    if (name) {
      mainKey = name;
      paint();
    }
  }

  function onKeyUp(event) {
    if (!recording) return;
    event.preventDefault();

    // Finish once the main key is released, or when the last modifier of a
    // modifier-only combination goes up.
    if (mainKey && !MODIFIER_KEYS[event.key]) {
      finish();
      return;
    }
    if (MODIFIER_KEYS[event.key] && !mainKey) {
      modifiers.delete(MODIFIER_KEYS[event.key]);
      if (modifiers.size === 0) cancel();
    }
  }

  function finish() {
    const combo = formatCombo(modifiers, mainKey);
    stop();
    input.value = combo;
    onDone(combo);
  }

  function cancel() {
    stop();
    input.value = previous;
  }

  function onClickAway(event) {
    if (event.target !== input) cancel();
  }

  function stop() {
    recording = false;
    input.classList.remove("recording");
    window.removeEventListener("keydown", onKeyDown, true);
    window.removeEventListener("keyup", onKeyUp, true);
    window.removeEventListener("mousedown", onClickAway, true);
  }

  window.addEventListener("keydown", onKeyDown, true);
  window.addEventListener("keyup", onKeyUp, true);
  setTimeout(() => window.addEventListener("mousedown", onClickAway, true), 50);
}
