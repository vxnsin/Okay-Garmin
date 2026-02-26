let config = {
    sound_enabled: true,
    voice_commands: []
};

const keyMap = {
    Control: "ctrl",
    Alt: "alt",
    Shift: "shift",
    Meta: "windows"
};


const ICONS = {
    file: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>`,
    
    folder: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>`,
    
    run: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect><line x1="8" y1="21" x2="16" y2="21"></line><line x1="12" y1="17" x2="12" y2="21"></line></svg>`,
    
    trash: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>`
};

async function fetchLatestVersion() {
    try {
        if (window.pywebview && window.pywebview.api && window.pywebview.api.get_version) {

            const versionData = await window.pywebview.api.get_version();
            const versionElement = document.getElementById("versionDisplay");

            if (versionData.update_available) {
                versionElement.textContent = `${versionData.current} (Update)`;
                versionElement.style.background = "linear-gradient(135deg, #ef4444 0%, #dc2626 100%)";
            } else {
                versionElement.textContent = versionData.current;
            }

        } else {
            document.getElementById("versionDisplay").textContent = "v1.3";
        }
    } catch (e) {
        document.getElementById("versionDisplay").textContent = "v1.3";
    }
}

async function loadConfig() {
    config = await window.pywebview.api.get_config();
    document.getElementById("soundToggle").checked = config.sound_enabled;
    document.getElementById("autostartToggle").checked = config.autostart_enabled;
    renderCommands();
    fetchLatestVersion();
}

async function saveConfig() {
    await window.pywebview.api.save_config(config);
}

function getIconForType(type) {
    switch(type) {
        case 'file': return ICONS.file;
        case 'folder': return ICONS.folder;
        case 'run': return ICONS.run;
        default: return ICONS.file;
    }
}

function renderCommands() {
    const container = document.getElementById("commandList");
    container.innerHTML = "";

    config.voice_commands.forEach((cmd, index) => {
        const div = document.createElement("div");
        div.className = "command";

        let valueField;
        if(cmd.type === "hotkey") {
            valueField = `<input type="text" class="hotkey-input" readonly placeholder="Klicken zum Aufnehmen" 
                onclick="startHotkeyRecording(${index}, this)" value="${cmd.value}">`;
        } else {
            const icon = getIconForType(cmd.type);
            valueField = `
                <div class="value-container">
                    <input type="text" readonly placeholder="${getPlaceholderForType(cmd.type)}" value="${cmd.value}">
                    <button class="icon-btn" onclick="pickPath(${index}, '${cmd.type}')" title="${getTooltipForType(cmd.type)}">
                        ${icon}
                    </button>
                </div>
            `;
        }

        div.innerHTML = `
            <input type="text" value="${cmd.command}" placeholder="Sprachbefehl (z.B. 'Öffne Editor')"
                onchange="updateCommand(${index}, 'command', this.value)">

            <select onchange="updateCommandType(${index}, this.value)">
                <option value="hotkey" ${cmd.type === "hotkey" ? "selected" : ""}>Hotkey</option>
                <option value="file" ${cmd.type === "file" ? "selected" : ""}>Datei</option>
                <option value="folder" ${cmd.type === "folder" ? "selected" : ""}>Ordner</option>
                <option value="run" ${cmd.type === "run" ? "selected" : ""}>Programm</option>
            </select>

            ${valueField}

            <button class="delete-btn" onclick="removeCommand(${index})" title="Löschen">
                ${ICONS.trash}
            </button>
        `;

        container.appendChild(div);
    });
}

function getPlaceholderForType(type) {
    switch(type) {
        case 'file': return "Datei auswählen...";
        case 'folder': return "Ordner auswählen...";
        case 'run': return "Programm auswählen...";
        default: return "Pfad auswählen...";
    }
}

function getTooltipForType(type) {
    switch(type) {
        case 'file': return "Datei durchsuchen";
        case 'folder': return "Ordner durchsuchen";
        case 'run': return "Programm auswählen";
        default: return "Durchsuchen";
    }
}

function addCommand() {
    config.voice_commands.push({
        command: "",
        type: "hotkey",
        value: ""
    });
    renderCommands();
    saveConfig();
}

function removeCommand(index) {
    config.voice_commands.splice(index, 1);
    renderCommands();
    saveConfig();
}

function updateCommand(index, field, value) {
    config.voice_commands[index][field] = value;
    saveConfig();
}

function updateCommandType(index, newType) {
    config.voice_commands[index].type = newType;
    config.voice_commands[index].value = "";
    renderCommands();
    saveConfig();
}

async function pickPath(index, type) {
    let path = await window.pywebview.api.pick_path(type);
    if(path) {
        config.voice_commands[index].value = path;
        renderCommands();
        saveConfig();
    }
}

function startHotkeyRecording(index, input) {
    if(input.classList.contains('recording')) return;
    
    input.classList.add('recording');
    input.value = "Tasten drücken...";
    
    const modifiers = new Set();
    let mainKey = null;
    let isRecording = true;

    function keydownHandler(e) {
        if(!isRecording) return;
        e.preventDefault();


            if (keyMap[e.key]) {
                modifiers.add(keyMap[e.key]);
                input.value = Array.from(modifiers).join("+") + (mainKey ? "+" + mainKey : "");
                return;
            }

        if (!mainKey) {
            mainKey = e.key.length === 1 ? e.key.toLowerCase() : e.key;
            if (mainKey.startsWith("F") && mainKey.length > 1) {
                mainKey = mainKey.toUpperCase();
            }
            input.value = Array.from(modifiers).join("+") + (modifiers.size ? "+" : "") + mainKey;
        }
    }

    function keyupHandler(e) {
        if(!isRecording) return;
        e.preventDefault();

        if (e.key === "Control" || e.key === "Alt" || e.key === "Shift" || e.key === "Meta") {
            modifiers.delete(e.key === "Meta" ? "Win" : e.key);
            input.value = Array.from(modifiers).join("+") + (modifiers.size && mainKey ? "+" : mainKey ? mainKey : "");
            return;
        }

        if (mainKey === e.key || mainKey === e.key.toLowerCase()) {
            finishRecording();
        }
    }

    function finishRecording() {
        isRecording = false;
        config.voice_commands[index].value = input.value;
        input.classList.remove('recording');
        saveConfig();
        cleanup();
    }

    function cleanup() {
        window.removeEventListener("keydown", keydownHandler);
        window.removeEventListener("keyup", keyupHandler);
        window.removeEventListener("click", clickOutside);
    }

    function clickOutside(e) {
        if (e.target !== input && isRecording) {
            input.value = config.voice_commands[index].value || "";
            input.classList.remove('recording');
            cleanup();
        }
    }

    window.addEventListener("keydown", keydownHandler);
    window.addEventListener("keyup", keyupHandler);
    setTimeout(() => window.addEventListener("click", clickOutside), 100);
}

// Autostart-Toggle Event
document.getElementById("autostartToggle").addEventListener("change", async function() {
    try {
        await window.pywebview.api.set_autostart(this.checked);
    } catch (e) {
        console.error("Autostart konnte nicht geändert werden:", e);
        this.checked = !this.checked; 
    }
});

document.getElementById("soundToggle").addEventListener("change", function() {
    config.sound_enabled = this.checked;
    saveConfig();
});

window.addEventListener("pywebviewready", loadConfig);