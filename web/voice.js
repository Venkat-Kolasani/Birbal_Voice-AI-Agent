// Minimal browser client for Pipecat SmallWebRTC (POST /api/offer with a complete SDP).
// shortcut: no ICE trickle; waits for full ICE gathering. Fine on localhost/LAN; add trickle (PATCH /api/offer) for remote use.
let pc = null, stream = null, audioEl = null, raf = 0, ctx = null;

async function connect({ session, onLevel = () => {}, onError = () => {} } = {}) {
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
  } catch (e) {
    throw new Error("Mic blocked. Allow microphone access in your browser, or use “Type instead”.");
  }
  pc = new RTCPeerConnection({ iceServers: [{ urls: "stun:stun.l.google.com:19302" }] });
  stream.getTracks().forEach((t) => pc.addTrack(t, stream));
  pc.createDataChannel("chat");
  audioEl = new Audio(); audioEl.autoplay = true;
  pc.ontrack = (e) => { audioEl.srcObject = e.streams[0] || new MediaStream([e.track]); audioEl.play().catch(() => {}); };
  pc.onconnectionstatechange = () => {
    if (["failed", "disconnected"].includes(pc.connectionState)) onError("Voice connection lost. Use “Type instead”, or refresh to retry.");
  };
  await pc.setLocalDescription(await pc.createOffer());
  await new Promise((res) => {
    if (pc.iceGatheringState === "complete") return res();
    const t = setTimeout(res, 2500);
    pc.addEventListener("icegatheringstatechange", () => { if (pc.iceGatheringState === "complete") { clearTimeout(t); res(); } });
  });
  const r = await fetch("/api/offer", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sdp: pc.localDescription.sdp, type: pc.localDescription.type, request_data: { session } }) });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || "Voice server refused the connection.");
  await pc.setRemoteDescription(await r.json());

  ctx = new AudioContext();
  const an = ctx.createAnalyser(); an.fftSize = 256;
  ctx.createMediaStreamSource(stream).connect(an);
  const buf = new Uint8Array(an.frequencyBinCount);
  const tick = () => { an.getByteTimeDomainData(buf); let m = 0; for (const v of buf) m = Math.max(m, Math.abs(v - 128)); onLevel(Math.min(1, m / 60)); raf = requestAnimationFrame(tick); };
  tick();
}

function setMuted(m) { stream?.getAudioTracks().forEach((t) => (t.enabled = !m)); }

async function disconnect() {
  cancelAnimationFrame(raf);
  stream?.getTracks().forEach((t) => t.stop());
  pc?.close(); ctx?.close().catch(() => {});
  pc = stream = ctx = null;
}

window.BirbalVoice = { connect, disconnect, setMuted };
