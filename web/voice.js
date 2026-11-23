let active = null;
const MIC_ERROR = "Mic blocked or unavailable. Check microphone access in your browser.";

function loadSDK() {
  return Promise.all([
    import("https://esm.sh/@pipecat-ai/client-js@1.16.0?target=es2022"),
    import("https://esm.sh/@pipecat-ai/small-webrtc-transport@1.11.2?bundle&deps=@pipecat-ai/client-js@1.16.0&target=es2022"),
  ]);
}

function release(run) {
  if (!run.client) return;
  run.mic?.stop();
  run.media.tracks().local.audio?.stop();
  void run.client.disconnect()
    .catch(() => {})
    .then(() => run.media.disconnect())
    .catch(() => {});
}

function close(run, reason) {
  if (active !== run) return;
  active = null;
  run.abort.abort(reason);
  run.audio.pause();
  run.audio.srcObject = null;
  release(run);
}

async function connect({ session, lang = "auto", onLevel = () => {}, onError = () => {} } = {}) {
  if (active) throw new Error("Voice is already connecting or connected.");
  const run = { abort: new AbortController(), audio: new Audio() };
  active = run;
  const signal = run.abort.signal;
  const aborted = new Promise((_, reject) => signal.addEventListener("abort", () => reject(signal.reason), { once: true }));
  const timer = setTimeout(() => close(run, new Error("Voice could not connect in time.")), 15000);
  try {
    await Promise.race([start(run, session, lang, onLevel, onError), aborted]);
    signal.throwIfAborted();
    run.ready = true;
  } catch (err) {
    const error = err instanceof Error ? err : new Error("Voice could not connect.");
    close(run, error);
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

async function start(run, session, lang, onLevel, onError) {
  const signal = run.abort.signal;
  const response = await fetch(`/api/voice?lang=${encodeURIComponent(lang)}`, { signal });
  if (!response.ok) throw new Error("Voice is unavailable.");
  const cfg = await response.json();
  if (!cfg.ready) throw new Error(cfg.why || "Voice is unavailable.");
  const [{ PipecatClient, LogLevel }, { SmallWebRTCTransport, WavMediaManager }] = await loadSDK();
  signal.throwIfAborted();
  // Each attempt owns its media; the default Daily manager may reuse a call object.
  run.media = new WavMediaManager();

  const fail = (message) => {
    if (active !== run) return;
    close(run, new Error(message));
    if (run.ready) onError(message);
  };
  const disconnected = () => fail("Voice connection lost.");
  const client = run.client = new PipecatClient({
    transport: new SmallWebRTCTransport({ iceServers: cfg.ice, mediaManager: run.media }),
    enableMic: true,
    enableCam: false,
    disconnectOnBotDisconnect: false,
    callbacks: {
      onDisconnected: disconnected,
      onBotDisconnected: disconnected,
      onTransportStateChanged: (state) => { if (state === "error") disconnected(); },
      onDeviceError: (error) => { if (error.devices.includes("mic")) fail(MIC_ERROR); },
      onLocalAudioLevel: (level) => { if (!signal.aborted) onLevel(level); },
      onTrackStarted: (track, participant) => {
        if (track.kind !== "audio") return;
        if (participant?.local) {
          if (signal.aborted) track.stop();
          else run.mic = track;
          return;
        }
        if (signal.aborted) return;
        run.audio.srcObject = new MediaStream([track]);
        run.audio.play().catch(() => fail("Your browser blocked Birbal's audio."));
      },
    },
  });
  client.setLogLevel(LogLevel.WARN);
  try {
    try {
      await client.initDevices();
    } catch {
      throw new Error(MIC_ERROR);
    }
    signal.throwIfAborted();
    if (!run.media.tracks().local.audio) throw new Error(MIC_ERROR);
    await client.connect({ webrtcRequestParams: {
      endpoint: new URL("/api/offer", window.location.href).href,
      requestData: { session },
    } });
  } finally {
    // Browsers can grant microphone access after a timed-out permission prompt.
    if (signal.aborted) release(run);
  }
}

function setMuted(muted) { active?.client?.enableMic(!muted); }

function disconnect() {
  if (active) close(active, new Error("Voice was stopped."));
}

window.addEventListener("pagehide", disconnect);
window.BirbalVoice = { connect, disconnect, setMuted };
