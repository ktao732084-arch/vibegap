const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../vibegap/ui/web/shell.js'), 'utf8');

function harness() {
  const handlers = {}, nodes = new Map();
  const get = id => {
    if (!nodes.has(id)) nodes.set(id, {
      classList: { toggle() {}, add() {}, remove() {} },
      addEventListener(type, fn) { this[type] = fn; },
      closest(selector) { return selector === '#' + id ? this : null; },
    });
    return nodes.get(id);
  };
  const window = { addEventListener(type, fn) { (handlers[type] ||= []).push(fn); } };
  const document = { body: get('body'), getElementById: get, hasFocus: () => false,
    addEventListener() {} };
  vm.runInNewContext(source, { window, document, setInterval() {} });
  handlers.pywebviewready.forEach(fn => fn());
  let opens = 0;
  window.shell.toggleOverlay = () => { opens++; };
  function fire(type, x, y, options = {}) {
    const event = { target: get('status-text'), button: 0, detail: 1,
      screenX: x, screenY: y, clientX: 20, clientY: 10,
      preventDefault() { this.prevented = true; },
      stopImmediatePropagation() { this.stopped = true; }, ...options };
    for (const fn of handlers[type] || []) {
      fn(event);
      if (event.stopped) break;
    }
    if (type === 'click' && !event.stopped && event.target.click) event.target.click(event);
    return event;
  }
  return { fire, get, opens: () => opens };
}

test('ordinary click and small hand jitter still open the book chooser', () => {
  const h = harness();
  h.fire('mousedown', 100, 100);
  h.fire('mousemove', 102, 102);
  h.fire('mouseup', 102, 102);
  h.fire('click', 102, 102);
  assert.equal(h.opens(), 1);
});

test('window drag suppresses click even with constant client coordinates or a return to origin', () => {
  const h = harness();
  h.fire('mousedown', 100, 100);
  h.fire('mousemove', 140, 130);
  h.fire('mousemove', 100, 100);
  h.fire('mouseup', 100, 100);
  assert.equal(h.fire('click', 100, 100).prevented, true);
  assert.equal(h.opens(), 0);
  h.fire('mousedown', 100, 100);
  h.fire('mouseup', 100, 100);
  h.fire('click', 100, 100);
  assert.equal(h.opens(), 1);
});

test('mouseup displacement detects native moves when mousemove was not delivered', () => {
  const h = harness();
  h.fire('mousedown', 100, 100);
  h.fire('mouseup', 150, 100);
  h.fire('click', 150, 100);
  assert.equal(h.opens(), 0);
});

test('interrupted drag cannot click on release but does not poison the next gesture', () => {
  const h = harness();
  h.fire('mousedown', 100, 100);
  h.fire('blur', 100, 100);
  h.fire('click', 100, 100);
  assert.equal(h.opens(), 0);
  h.fire('mousedown', 100, 100);
  h.fire('mouseup', 100, 100);
  h.fire('click', 100, 100);
  assert.equal(h.opens(), 1);
});

test('keyboard activation and other controls are unaffected', () => {
  const h = harness();
  h.fire('click', 0, 0, { detail: 0 });
  assert.equal(h.opens(), 1);
  const target = h.get('btn-settings');
  h.fire('mousedown', 100, 100, { target });
  h.fire('mouseup', 110, 100, { target });
  assert.equal(h.fire('click', 110, 100, { target }).stopped, undefined);
  assert.equal(h.opens(), 2);
});
