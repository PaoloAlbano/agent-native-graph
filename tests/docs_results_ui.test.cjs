const {test} = require('node:test');
const assert = require('node:assert/strict');
const {createDisclosure, matchesQid} = require('../docs/site/results-ui.js');

class Element {
  children = [];
  open = false;
  append(child) { child.parent = this; this.children.push(child); }
  addEventListener(name, handler) { this[name] = handler; }
  get lastChild() { return this.children.at(-1); }
  remove() { this.parent.children.splice(this.parent.children.indexOf(this), 1); }
}
const document = { createElement: () => new Element() };

test('closed disclosures do not serialize or render responses', () => {
  let serializations = 0;
  const value = {toJSON() { serializations++; return 'x'.repeat(2400000); }};
  const panel = createDisclosure(document, 'Response', value);
  assert.equal(serializations, 0);
  assert.equal(panel.children.length, 1);
  panel.open = true;
  panel.toggle();
  assert.equal(serializations, 1);
  assert.equal(panel.lastChild.textContent.length, 20000);
  assert.match(panel.children[1].textContent, /Download/);
  panel.toggle();
  assert.equal(serializations, 1);
  panel.open = false;
  panel.toggle();
  assert.equal(panel.children.length, 1);
});

test('QID search accepts partial IDs, not question text', () => {
  assert.equal(matchesQid('ABC-123', ' abc '), true);
  assert.equal(matchesQid('ABC-123', 'company'), false);
});
