let active = null;
const MIC_ERROR = "Mic blocked or unavailable. Check microphone access in your browser.";

function loadSDK() {
  return Promise.all([
    import("https://esm.sh/@pipecat-ai/client-js@1.16.0?target=es2022"),
    import("https://esm.sh/@pipecat-ai/small-webrtc-transport@1.11.2?bundle&deps=@pipecat-ai/client-js@1.16.0&target=es2022"),
  ]);
}

function close(run, reason) {
  if (active !== run) return;
  active = null;
  run.abort.abort(reason);
  run.audio.pause();
  run.audio.srcObject = null;
  void run.media?.disconnect();
  void run.client?.disconnect().catch(() => {});
}

// Pipecat owns WebRTC; this mic-only adapter owns just the browser track.
function microphone(stream, onLevel, onEnded) {
  const track = stream.getAudioTracks()[0];
  track.onended = onEnded;
  let callbacks, meter, frame;
  try {
    meter = new AudioContext();
    const analyser = meter.createAnalyser();
    analyser.fftSize = 256;
    meter.createMediaStreamSource(stream).connect(analyser);
    const samples = new Uint8Array(analyser.fftSize);
    const tick = () => {
      analyser.getByteTimeDomainData(samples);
      let peak = 0;
      for (const sample of samples) peak = Math.max(peak, Math.abs(sample - 128));
      onLevel(Math.min(1, peak / 60));
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
  } catch { /* The microphone meter is optional. */ }
  return {
    setClientOptions: (options) => { callbacks = options.callbacks; },
    initialize: async () => callbacks.onMicUpdated?.({ deviceId: track.getSettings().deviceId || "default" }),
    connect: async () => {},
    disconnect: async () => {
      track.onended = null;
      track.stop();
      cancelAnimationFrame(frame);
      if (meter) void meter.close().catch(() => {});
      meter = null;
    },
    tracks: () => ({ local: { audio: track } }),
    mediaSupport: { mic: true, cam: false, screenShare: false },
    enableMic: (enabled) => { track.enabled = enabled; },
    get isMicEnabled() { return track.enabled; },
    isCamEnabled: false,
    supportsScreenShare: false,
  };
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
  const [{ PipecatClient, LogLevel }, { SmallWebRTCTransport }] = await loadSDK();
  signal.throwIfAborted();

  const fail = (message) => {
    if (active !== run) return;
    close(run, new Error(message));
    if (run.ready) onError(message);
  };
  const disconnected = () => fail("Voice connection lost.");
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
  } catch {
    throw new Error(MIC_ERROR);
  }
  if (signal.aborted || !stream.getAudioTracks().length) {
    stream.getTracks().forEach((track) => track.stop());
    signal.throwIfAborted();
    throw new Error(MIC_ERROR);
  }
  run.media = microphone(stream, onLevel, () => fail("Microphone disconnected."));
  const client = run.client = new PipecatClient({
    transport: new SmallWebRTCTransport({ iceServers: cfg.ice, mediaManager: run.media }),
    enableMic: true,
    enableCam: false,
    disconnectOnBotDisconnect: false,
    callbacks: {
      onDisconnected: disconnected,
      onBotDisconnected: disconnected,
      onTransportStateChanged: (state) => { if (state === "error") disconnected(); },
      onTrackStarted: (track, participant) => {
        if (signal.aborted || participant?.local || track.kind !== "audio") return;
        run.audio.srcObject = new MediaStream([track]);
        run.audio.play().catch(() => fail("Your browser blocked Birbal's audio."));
      },
    },
  });
  client.setLogLevel(LogLevel.WARN);
  await client.initDevices();
  signal.throwIfAborted();
  await client.connect({ webrtcRequestParams: {
    endpoint: new URL("/api/offer", window.location.href).href,
    requestData: { session },
  } });
  if (signal.aborted) void client.disconnect().catch(() => {});
}

function setMuted(muted) { active?.client?.enableMic(!muted); }

function disconnect() {
  if (active) close(active, new Error("Voice was stopped."));
}

window.addEventListener("pagehide", disconnect);
window.BirbalVoice = { connect, disconnect, setMuted };
