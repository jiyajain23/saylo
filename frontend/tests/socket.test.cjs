const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');

function setup() {
  let socket;
  class FakeWebSocket {
    static OPEN = 1;
    static CONNECTING = 0;
    static CLOSED = 3;
    readyState = 0;
    sent = [];
    constructor(url) { this.url = url; socket = this; }
    send(message) { this.sent.push(JSON.parse(message)); }
    close() { this.readyState = 3; this.onclose?.(); }
  }
  const exports = {};
  const source = ts.transpileModule(fs.readFileSync('frontend/lib/socket.ts', 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 }
  }).outputText;
  vm.runInNewContext(source, { exports, require: () => ({ API_BASE: 'http://localhost:5000' }),
    URL, WebSocket: FakeWebSocket, console, setTimeout, clearTimeout });
  const received = [];
  const client = exports.openLiveSocket({ sessionId: 'fixture', accessToken: 'private-access-token', onAi() {}, onUserTranscript: text => received.push(text),
    onNudge() {}, onError() {} });
  socket.readyState = 1;
  socket.onopen();
  return { socket, client, received };
}

test('final audio end waits for matching acknowledgement', async () => {
  const { socket, client, received } = setup();
  let finished = false;
  const result = client.finishAudio(200).then(() => { finished = true; });
  const request = socket.sent.at(-1);
  assert.equal(request.type, 'audio_end');
  assert.equal(request.final, true);
  socket.onmessage({ data: JSON.stringify({ type: 'audio_ended', requestId: 'wrong', ok: true }) });
  await Promise.resolve();
  assert.equal(finished, false);
  socket.onmessage({ data: JSON.stringify({ type: 'user_text', text: 'last words' }) });
  socket.onmessage({ data: JSON.stringify({ type: 'audio_ended', requestId: request.requestId, ok: true }) });
  await result;
  assert.deepEqual(received, ['last words']);
});

test('JWT is sent only in hello, never in the WebSocket URL or media messages', () => {
  const { socket, client } = setup();
  assert.deepEqual(JSON.parse(JSON.stringify(socket.sent[0])), { type: 'hello', sessionId: 'fixture', accessToken: 'private-access-token' });
  assert.equal(socket.url, 'ws://localhost:5000/ws');
  client.sendAudioChunk('AAA=');
  assert.equal(socket.sent.at(-1).accessToken, undefined);
});

test('disconnect rejects pending completion', async () => {
  const { socket, client } = setup();
  const result = client.finishAudio(200);
  socket.close();
  await assert.rejects(result, /closed/);
});

test('timeout does not authorize session completion', async () => {
  const { client } = setup();
  await assert.rejects(client.finishAudio(10), /not confirmed/);
});

test('typed answer contract is preserved and starter is explicit control input', () => {
  const { socket, client } = setup();
  client.sendUserText('my answer');
  assert.equal(JSON.stringify(socket.sent.at(-1)), JSON.stringify({ type: 'user_text', sessionId: 'fixture', text: 'my answer' }));
  client.sendUserText('begin interview', true);
  assert.equal(socket.sent.at(-1).isControl, true);
});

test('unsolicited completion acknowledgement is ignored', () => {
  const { socket } = setup();
  assert.doesNotThrow(() => socket.onmessage({ data: JSON.stringify({ type: 'audio_ended', ok: true }) }));
});

test('cleanup after closing does not queue media or throw', async () => {
  const { socket, client } = setup();
  socket.close();
  const before = socket.sent.length;
  assert.doesNotThrow(() => client.endAudio());
  assert.equal(socket.sent.length, before);
  await assert.rejects(client.finishAudio(100), /closed/);
});
