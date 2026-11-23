const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "../web/voice.js"), "utf8");

function deferred() {
  let resolve, reject;
  const promise = new Promise((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}

function setup({ hasMic = true } = {}) {
  const timers = new Map();
  const permission = deferred(), requestedMic = deferred();
  const handshake = deferred(), offered = deferred();
  let stopped = false, meterClosed = false, meterCancelled = false;
  let callbacks, signal, id = 0;
  const mic = { enabled: true, getSettings: () => ({}), stop: () => { stopped = true; } };
  const tracks = hasMic ? [mic] : [];
  const window = { location: { href: "https://birbal.test/start" }, addEventListener() {} };
  class Transport {
    constructor(options) { this.media = options.mediaManager; }
  }
  class Client {
    constructor(options) {
      callbacks = options.callbacks;
      this.media = options.transport.media;
      this.media.setClientOptions(options);
    }
    setLogLevel() {}
    initDevices() { return this.media.initialize(); }
    connect(params) { offered.resolve(params); return handshake.promise; }
    async disconnect() { await this.media.disconnect(); callbacks.onDisconnected(); }
  }
  vm.runInNewContext(source + "\nloadSDK = fakeSDK;", {
    window, AbortController, URL, Error,
    fakeSDK: async () => [{ PipecatClient: Client, LogLevel: { WARN: 2 } }, {
      SmallWebRTCTransport: Transport,
    }],
    navigator: { mediaDevices: { getUserMedia: async () => {
      requestedMic.resolve();
      await permission.promise;
      return { getAudioTracks: () => tracks, getTracks: () => tracks };
    } } },
    fetch: async (url, options) => {
      signal = options.signal;
      return { ok: true, json: async () => ({ ready: true, ice: [] }) };
    },
    Audio: class { pause() {} },
    AudioContext: class {
      createAnalyser() { return {}; }
      createMediaStreamSource() { return { connect() {} }; }
      async close() { meterClosed = true; }
    },
    requestAnimationFrame: () => 1,
    cancelAnimationFrame: () => { meterCancelled = true; },
    setTimeout: (callback, ms) => { timers.set(++id, { callback, ms }); return id; },
    clearTimeout: (timer) => timers.delete(timer),
  });
  return {
    client: window.BirbalVoice, permission, requestedMic, offered, handshake,
    endMic: () => mic.onended(),
    loseConnection: () => callbacks.onDisconnected(),
    fireTimer: (ms) => {
      const timer = [...timers.values()].find((t) => t.ms === ms);
      assert.ok(timer);
      timer.callback();
    },
    cleaned: () => stopped && signal.aborted,
    meterReleased: () => meterClosed && meterCancelled,
  };
}

test("refused offer releases the microphone", async () => {
  const t = setup();
  t.permission.resolve();
  const connecting = t.client.connect({ session: "fixture" });
  await t.offered.promise;
  t.handshake.reject(new Error("Voice is busy."));
  await assert.rejects(connecting, /Voice is busy/);
  assert.equal(t.cleaned(), true);
  assert.equal(t.meterReleased(), true);
});

test("unanswered permission times out and releases media even if granted later", async () => {
  const t = setup();
  const connecting = t.client.connect({ session: "fixture" });
  await t.requestedMic.promise;
  t.fireTimer(15000);
  await assert.rejects(connecting, /could not connect in time/);
  t.permission.resolve();
  await new Promise(setImmediate);
  assert.equal(t.cleaned(), true);
});

test("waits for bot-ready and reports loss once for the current interview", async () => {
  const t = setup();
  t.permission.resolve();
  const errors = [];
  let connected = false;
  const connecting = t.client.connect({ session: "fixture", onError: (message) => errors.push(message) })
    .then(() => { connected = true; });
  const { webrtcRequestParams } = await t.offered.promise;
  assert.equal(webrtcRequestParams.endpoint, "https://birbal.test/api/offer");
  assert.equal(webrtcRequestParams.requestData.session, "fixture");
  assert.equal(connected, false);
  t.handshake.resolve();
  await connecting;
  t.loseConnection();
  t.loseConnection();
  assert.deepEqual(errors, ["Voice connection lost."]);
  assert.equal(t.cleaned(), true);
});

test("a microphone device error ends the attempt without waiting for negotiation", async () => {
  const t = setup();
  const connecting = t.client.connect({ session: "fixture" });
  await t.requestedMic.promise;
  t.permission.reject(new Error("NotAllowedError"));
  await assert.rejects(connecting, /Mic blocked or unavailable/);
});

test("initialization without a microphone is rejected before negotiation", async () => {
  const t = setup({ hasMic: false });
  const connecting = t.client.connect({ session: "fixture" });
  t.permission.resolve();
  await assert.rejects(connecting, /Mic blocked or unavailable/);
});

test("removing the active microphone releases audio and reports a failure", async () => {
  const t = setup();
  t.permission.resolve();
  const errors = [];
  const connecting = t.client.connect({ session: "fixture", onError: (message) => errors.push(message) });
  await t.offered.promise;
  t.handshake.resolve();
  await connecting;
  t.endMic();
  assert.deepEqual(errors, ["Microphone disconnected."]);
  assert.equal(t.cleaned(), true);
  assert.equal(t.meterReleased(), true);
});
