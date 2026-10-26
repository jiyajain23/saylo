const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');

function load(path, context) {
  const exports = {};
  const source = ts.transpileModule(fs.readFileSync(path, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 }
  }).outputText;
  vm.runInNewContext(source, { exports, Date, ...context });
  return exports;
}

test('REST attaches a bearer token and preserves the existing response contract', async () => {
  const requests = [];
  const api = load('frontend/lib/api.ts', {
    process: { env: { NEXT_PUBLIC_API_BASE: 'http://localhost:5000' } },
    require: () => ({ getAccessToken: async () => 'token' }),
    fetch: async (url, options) => { requests.push({ url, options }); return { ok: true, json: async () => ({ sessions: [] }) }; }
  });
  assert.deepEqual(await api.listSessions(), { sessions: [] });
  assert.equal(requests[0].options.headers.Authorization, 'Bearer token');
  assert.equal(requests[0].options.cache, 'no-store');
  assert.equal(requests[0].url, 'http://localhost:5000/sessions');
});

test('REST does not send an anonymous request when the session is missing', async () => {
  let calls = 0;
  const api = load('frontend/lib/api.ts', {
    process: { env: {} },
    require: () => ({ getAccessToken: async () => { throw new Error('Please sign in'); } }),
    fetch: async () => { calls++; }
  });
  await assert.rejects(api.listSessions(), /sign in/);
  assert.equal(calls, 0);
});

test('the auth SDK singleton refreshes a nearly expired token before use', async () => {
  let clients = 0, refreshes = 0;
  const auth = load('frontend/lib/auth.ts', {
    window: {}, process: { env: { NEXT_PUBLIC_SUPABASE_URL: 'https://example.supabase.co', NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: 'public-key' } },
    require: () => ({ createClient: () => { clients++; return { auth: {
      getSession: async () => ({ data: { session: { access_token: 'old', expires_at: Date.now() / 1000 + 5 } }, error: null }),
      refreshSession: async () => { refreshes++; return { data: { session: { access_token: 'new' } }, error: null }; }
    } }; } })
  });
  assert.equal(await auth.getAccessToken(), 'new');
  auth.getSupabase();
  assert.equal(clients, 1);
  assert.equal(refreshes, 1);
});
