const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { parseState } = require('../Model.js');

assert.equal(parseState('bad json'), null);
assert.equal(parseState('null'), null);
assert.equal(parseState('[]'), null);
assert.equal(parseState(JSON.stringify({ mode: '<img src=x>' })), null);
assert.equal(parseState(' '.repeat(16385)), null);
const state = parseState(JSON.stringify({ mode: 'automatic', lux: 303, temperature_kelvin: 6151,
  target_kelvin: 6150, error: '<img src="https://example.invalid">',
  settings: { minimum_kelvin: 5000, smoothing_seconds: 45 } }));
assert.equal(state.lux, 303);
assert.equal(state.settings.minimum_kelvin, 5000);
assert.ok(state.error.startsWith('<img')); // Rendered as plain text, never interpreted.
assert.equal(parseState(JSON.stringify({ mode: 'automatic', lux: -1 })).lux, null);
assert.equal(parseState(JSON.stringify({ mode: 'automatic', lux: '303' })).lux, null);
const root = path.resolve(__dirname, '..');
const plain = fs.readFileSync(path.join(root, 'PlainText.qml'), 'utf8');
assert.match(plain, /textFormat:\s*Text\.PlainText/);
const widget = fs.readFileSync(path.join(root, 'BarWidget.qml'), 'utf8');
assert.match(widget, /PlainText\s*\{[^}]*text:\s*root\.telemetry\.error/s);
assert.match(widget, /tooltipText:\s*""/); // No untrusted text in host-owned tooltip sinks.
console.log('PASS: bounded telemetry, invalid input, markup-shaped input, plain-text sinks');
