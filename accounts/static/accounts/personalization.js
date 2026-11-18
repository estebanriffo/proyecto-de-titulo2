(() => {
    "use strict";

    const panel = document.getElementById("settings-panel");
    if (!panel) return;
    const form = document.getElementById("preferences-form");
    const root = document.documentElement;
    const feedback = document.getElementById("speech-feedback");
    const status = document.getElementById("preferences-status");
    const storageKey = `aamr-preferences-v1-${panel.dataset.preferencesScope}`;
    const defaults = {
        font: "default", textSize: 100, palette: "original",
        headerColor: "#ffffff", bodyColor: "#eef4f8", footerColor: "#ffffff",
        voiceVolume: 80, activityVolume: 80,
    };
    const palettes = {
        original: ["#ffffff", "#eef4f8", "#ffffff"],
        ocean: ["#dcebf7", "#f1f7fc", "#193f70"],
        garden: ["#dceee4", "#f2f7f1", "#22635e"],
        sand: ["#efe2c7", "#fcf7ec", "#594b35"],
        night: ["#172636", "#101c28", "#172636"],
    };
    const fonts = {
        default: '"Atkinson Hyperlegible Next", system-ui, sans-serif',
        arial: "Arial, sans-serif",
        verdana: "Verdana, sans-serif",
        opendyslexic: '"OpenDyslexic", Verdana, sans-serif',
    };
    const synthesis = window.speechSynthesis;
    let preferences = { ...defaults };
    let activeButton = null;
    let speechRun = 0;

    function numberInRange(value, minimum, maximum, fallback) {
        return typeof value === "number" && Number.isFinite(value)
            ? Math.min(maximum, Math.max(minimum, value)) : fallback;
    }

    function restore() {
        try {
            const saved = JSON.parse(sessionStorage.getItem(storageKey));
            if (!saved || typeof saved !== "object") return;
            if (Object.hasOwn(fonts, saved.font)) preferences.font = saved.font;
            if (Object.hasOwn(palettes, saved.palette) || saved.palette === "custom") {
                preferences.palette = saved.palette;
            }
            for (const key of ["headerColor", "bodyColor", "footerColor"]) {
                if (typeof saved[key] === "string" && /^#[0-9a-f]{6}$/i.test(saved[key])) {
                    preferences[key] = saved[key];
                }
            }
            preferences.textSize = numberInRange(saved.textSize, 50, 300, 100);
            preferences.voiceVolume = numberInRange(saved.voiceVolume, 0, 100, 80);
            preferences.activityVolume = numberInRange(saved.activityVolume, 0, 100, 80);
        } catch {
            status.textContent = "Puedes personalizar la página. Este navegador no pudo recuperar las preferencias.";
        }
    }

    function foreground(hex) {
        const channels = hex.match(/[0-9a-f]{2}/gi).map(channel => {
            const value = parseInt(channel, 16) / 255;
            return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
        });
        const luminance = channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
        return (luminance + 0.05) / 0.05 > 1.05 / (luminance + 0.05) ? "#000000" : "#ffffff";
    }

    function sendVolume(frame) {
        frame.contentWindow?.postMessage({
            type: "aamr:set-volume", volume: preferences.activityVolume / 100,
        }, "*");
    }

    function apply() {
        root.dataset.personalized = "true";
        root.style.setProperty("--reading-font", fonts[preferences.font]);
        root.style.fontSize = `${preferences.textSize}%`;
        for (const region of ["header", "body", "footer"]) {
            const color = preferences[`${region}Color`];
            root.style.setProperty(`--personal-${region}`, color);
            root.style.setProperty(`--personal-${region}-text`, foreground(color));
        }
        for (const key of Object.keys(defaults)) {
            form.elements.namedItem(key).value = preferences[key];
        }
        for (const [key, id] of [["textSize", "text-size-value"], ["voiceVolume", "voice-volume-value"], ["activityVolume", "activity-volume-value"]]) {
            document.getElementById(id).value = `${preferences[key]} %`;
        }
        document.querySelectorAll("audio, video").forEach(media => {
            media.volume = preferences.activityVolume / 100;
        });
        document.querySelectorAll("iframe.activity-player").forEach(sendVolume);
    }

    function save() {
        try {
            sessionStorage.setItem(storageKey, JSON.stringify(preferences));
            status.textContent = "Cambios guardados para esta sesión del navegador.";
        } catch {
            status.textContent = "Los cambios se aplican a esta página. El navegador no permite guardarlos.";
        }
    }

    function stopSpeech() {
        speechRun += 1;
        synthesis?.cancel();
        if (activeButton) {
            activeButton.setAttribute("aria-pressed", "false");
            activeButton.setAttribute("aria-label", "Escuchar este texto");
            activeButton.textContent = "🔊";
            activeButton = null;
        }
    }

    function chunksFor(text) {
        const chunks = [];
        while (text.length > 180) {
            let split = text.lastIndexOf(" ", 180);
            if (split < 1) split = 180;
            chunks.push(text.slice(0, split));
            text = text.slice(split).trim();
        }
        if (text) chunks.push(text);
        return chunks;
    }

    function speak(button, block) {
        const wasActive = button === activeButton;
        stopSpeech();
        if (wasActive) {
            feedback.textContent = "Lectura detenida.";
            return;
        }
        if (preferences.voiceVolume === 0) {
            feedback.textContent = "El volumen de lectura está en cero. Puedes aumentarlo en Configuración.";
            return;
        }
        const copy = block.cloneNode(true);
        copy.querySelectorAll(".speech-button, [aria-hidden='true'], input, select, textarea").forEach(node => node.remove());
        const text = copy.textContent.replace(/\s+/g, " ").trim();
        const chunks = chunksFor(text);
        const currentRun = speechRun;
        activeButton = button;
        button.textContent = "⏹";
        button.setAttribute("aria-label", "Detener lectura");
        button.setAttribute("aria-pressed", "true");
        feedback.textContent = "Leyendo el texto seleccionado.";

        function next() {
            if (currentRun !== speechRun) return;
            if (!chunks.length) {
                stopSpeech();
                feedback.textContent = "Lectura finalizada.";
                return;
            }
            const utterance = new SpeechSynthesisUtterance(chunks.shift());
            const voices = synthesis.getVoices();
            const spanish = voices.filter(voice => voice.lang.toLowerCase().startsWith("es"));
            const voice = spanish.find(voice => voice.localService) || spanish[0];
            if (voice) utterance.voice = voice;
            utterance.lang = voice?.lang || "es-CL";
            utterance.volume = preferences.voiceVolume / 100;
            utterance.rate = 0.95;
            utterance.onend = next;
            utterance.onerror = event => {
                if (currentRun !== speechRun) return;
                stopSpeech();
                feedback.textContent = event.error === "canceled" || event.error === "interrupted"
                    ? "Lectura detenida." : "No se pudo reproducir la voz. Comprueba las voces y el audio de tu navegador.";
            };
            synthesis.speak(utterance);
        }
        next();
    }

    function addSpeechControls() {
        const selector = "main h1, main h2, main h3, main h4, main h5, main h6, main p, main li, main dt, main dd, main blockquote, main figcaption, main label, main legend, main .helptext, footer p, footer .footer-brand";
        document.querySelectorAll(selector).forEach(block => {
            if (block.closest("[data-no-speech], .account-summary, .role-label, .availability, [hidden], [aria-hidden='true'], a, button")) return;
            if (block.querySelector("h1, h2, h3, h4, h5, h6, p, li, label, legend, .helptext")) return;
            const text = block.textContent.trim();
            if (!text || /^(estudiante|docente|administrador|próximamente|sesión iniciada|tu cuenta)$/i.test(text)) return;
            const button = document.createElement("button");
            button.type = "button";
            button.className = "speech-button";
            button.textContent = "🔊";
            button.setAttribute("aria-label", "Escuchar este texto");
            button.setAttribute("aria-pressed", "false");
            button.title = "Escuchar este texto";
            if (!synthesis || typeof SpeechSynthesisUtterance === "undefined") {
                button.disabled = true;
                button.title = "La lectura en voz alta no está disponible en este navegador";
            } else {
                button.addEventListener("click", event => {
                    event.preventDefault();
                    speak(button, block);
                });
            }
            if (block.matches("label, legend")) {
                block.after(button);
                block.classList.add("speech-label");
            } else {
                block.append(button);
            }
        });
    }

    document.querySelectorAll("[data-open-settings]").forEach(button => {
        button.hidden = false;
        button.addEventListener("click", () => {
            panel.showModal();
            button.setAttribute("aria-expanded", "true");
        });
    });
    panel.addEventListener("close", () => {
        document.querySelectorAll("[data-open-settings]").forEach(button => button.setAttribute("aria-expanded", "false"));
    });
    panel.querySelector("[data-close-settings]").addEventListener("click", () => panel.close());
    panel.addEventListener("click", event => {
        const bounds = panel.getBoundingClientRect();
        if (event.target === panel && (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom)) panel.close();
    });
    form.addEventListener("submit", event => event.preventDefault());
    form.addEventListener("input", event => {
        const { name, value } = event.target;
        if (!Object.hasOwn(defaults, name)) return;
        preferences[name] = event.target.type === "range" ? Number(value) : value;
        if (name === "palette") {
            if (Object.hasOwn(palettes, value)) {
                [preferences.headerColor, preferences.bodyColor, preferences.footerColor] = palettes[value];
            }
        } else if (name.endsWith("Color")) {
            preferences.palette = "custom";
        }
        if (name === "voiceVolume" && activeButton) {
            stopSpeech();
            feedback.textContent = "Volumen actualizado. Pulsa la bocina para escuchar con el nuevo volumen.";
        }
        apply();
        save();
    });
    document.getElementById("reset-preferences").addEventListener("click", () => {
        stopSpeech();
        preferences = { ...defaults };
        apply();
        save();
    });
    window.addEventListener("message", event => {
        if (event.data?.type !== "aamr:audio-ready") return;
        const frame = Array.from(document.querySelectorAll("iframe.activity-player")).find(frame => frame.contentWindow === event.source);
        if (frame) sendVolume(frame);
    });
    document.querySelectorAll("iframe.activity-player").forEach(frame => frame.addEventListener("load", () => sendVolume(frame)));
    document.addEventListener("play", event => {
        if (event.target instanceof HTMLMediaElement) event.target.volume = preferences.activityVolume / 100;
    }, true);
    window.addEventListener("pageshow", event => {
        if (event.persisted) {
            restore();
            apply();
        }
    });
    window.addEventListener("pagehide", stopSpeech);
    restore();
    apply();
    addSpeechControls();
})();
