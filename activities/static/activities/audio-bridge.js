(() => {
    "use strict";
    let volume = 0.8;
    const masters = new Map();
    const AudioNodeClass = window.AudioNode;

    if (AudioNodeClass) {
        const connect = AudioNodeClass.prototype.connect;
        const disconnect = AudioNodeClass.prototype.disconnect;

        function masterFor(context) {
            if (!masters.has(context)) {
                const gain = context.createGain();
                gain.gain.value = volume;
                connect.call(gain, context.destination);
                masters.set(context, gain);
            }
            return masters.get(context);
        }

        AudioNodeClass.prototype.connect = function(destination, ...ports) {
            if (destination === this.context.destination) {
                connect.call(this, masterFor(this.context), ...ports);
                return destination;
            }
            return connect.call(this, destination, ...ports);
        };
        AudioNodeClass.prototype.disconnect = function(...args) {
            if (args[0] === this.context.destination && masters.has(this.context)) {
                args[0] = masters.get(this.context);
            }
            return disconnect.apply(this, args);
        };
    }

    function applyVolume() {
        for (const [context, master] of masters) {
            master.gain.setTargetAtTime(volume, context.currentTime, 0.02);
        }
        document.querySelectorAll("audio, video").forEach(media => { media.volume = volume; });
    }

    window.addEventListener("message", event => {
        if (event.source !== window.parent || event.data?.type !== "aamr:set-volume") return;
        const next = event.data.volume;
        if (typeof next !== "number" || !Number.isFinite(next) || next < 0 || next > 1) return;
        volume = next;
        applyVolume();
    });
    document.addEventListener("play", event => {
        if (event.target instanceof HTMLMediaElement) event.target.volume = volume;
    }, true);
    window.parent.postMessage({ type: "aamr:audio-ready" }, "*");
})();
