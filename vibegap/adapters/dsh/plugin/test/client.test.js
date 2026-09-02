"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

function loadClient() {
  let registration;
  const effects = [];
  const React = {
    createElement() { return null; },
    useEffect(effect, dependencies) { effects.push({ effect, dependencies }); },
    useState(value) { return [value, function noop() {}]; },
  };
  const store = {
    getSnapshot() { return {}; },
    set() {},
    subscribe() { return function unsubscribe() {}; },
    update() {},
  };
  const context = {
    AbortSignal: { timeout() { return { addEventListener() {} }; } },
    Audio: function Audio() {},
    Date,
    Math,
    clearTimeout,
    console,
    document: {
      activeElement: null,
      addEventListener() {},
      removeEventListener() {},
    },
    fetch,
    setTimeout,
    window: {
      __ModuleLoader__: { load(value) { registration = value; } },
    },
  };
  const source = fs.readFileSync(path.join(__dirname, "..", "lib", "client.js"), "utf8");
  vm.runInNewContext(source, context, { filename: "client.js" });
  const api = registration.factory(function localRequire(id) {
    if (id === "react") return React;
    if (id === "@deepseek-ai/dsh-client-ui-primitives") return { Button() {} };
    if (id === "@deepseek-ai/dsh-client-runtime/client") {
      return { createSnapshotStore() { return store; } };
    }
    throw new Error("unexpected client dependency: " + id);
  });
  return { api, context, effects };
}

test("package manifest is BOM-free JSON", function () {
  const raw = fs.readFileSync(path.join(__dirname, "..", "package.json"));
  assert.notDeepEqual(Array.from(raw.subarray(0, 3)), [0xef, 0xbb, 0xbf]);
  assert.equal(JSON.parse(raw.toString("utf8")).name, "dsh-vibegap");
});

test("daemon presence suppresses only automatic popup", function () {
  const helpers = loadClient().api.__test;
  assert.equal(helpers.canAutoPopup("probing"), true);
  assert.equal(helpers.canAutoPopup("local"), true);
  assert.equal(helpers.canAutoPopup("daemon"), false);
  assert.equal(helpers.canAutoPopup("disconnected"), false);
});

test("disconnect keeps the last shared word instead of showing first-use UI", function () {
  const helpers = loadClient().api.__test;
  const word = { name: "bridge", trans: ["桥梁"], position: 4, total: 10 };
  const selected = helpers.activeSelection(
    { ordered: [], word: null },
    [{ mode: "disconnected", word }, function noop() {}],
  );
  assert.equal(selected.word.name, "bridge");
  assert.equal(selected.connectionLost, true);
  assert.equal(selected.remoteUnavailable, true);
});

test("all daemon failures preserve the shared word and never fork local progress", function () {
  const failure = loadClient().api.__test.daemonFailureState;
  const word = { name: "bridge", trans: ["桥梁"], position: 4, total: 10 };
  assert.deepEqual(
    JSON.parse(JSON.stringify(failure({ mode: "daemon", word }))),
    { mode: "disconnected", word },
  );
  assert.equal(failure({ mode: "disconnected", word }).word.name, "bridge");
  assert.deepEqual(
    JSON.parse(JSON.stringify(failure({ mode: "probing", word: null }))),
    { mode: "local", word: null },
  );
});

test("typing listener dependencies do not include the per-render config object", function () {
  const loaded = loadClient();
  const card = { current: {} };
  loaded.api.__test.useTyping({
    visible: true,
    focused: true,
    word: "cat",
    busy: false,
    card,
  });
  assert.deepEqual(
    Array.from(loaded.effects.at(-1).dependencies),
    [true, true, "cat", false],
  );
});

test("typing handler reads the latest config without being rebound", function () {
  const loaded = loadClient();
  const card = { current: {} };
  let typed = -1;
  let typos = 0;
  let shook = false;
  const ref = {
    current: {
      card,
      word: "cat",
      typed: 0,
      revealed: false,
      setTyped(value) { typed = value; },
      setTypos(update) { typos = update(typos); },
      setRevealed() {},
      setPeeked() {},
      hide() {},
      complete() {},
      shake() { shook = true; },
    },
  };
  loaded.context.document.activeElement = card.current;
  const handler = loaded.api.__test.createTypingHandler(ref);
  handler({ key: "c", preventDefault() {} });
  assert.equal(typed, 1);

  ref.current.typed = 1;
  handler({ key: "z", preventDefault() {} });
  assert.equal(typed, 0);
  assert.equal(typos, 1);
  assert.equal(shook, true);
});

test("wordbook normalization drops invalid entries", function () {
  const normalize = loadClient().api.__test.normalizeWords;
  const words = normalize([
    { name: "valid", trans: ["有效", 1], usphone: "ˈvælɪd" },
    { name: "", trans: ["bad"] },
  ]);
  assert.equal(words.length, 1);
  assert.equal(words[0].name, "valid");
  assert.deepEqual(Array.from(words[0].trans), ["有效"]);
});
