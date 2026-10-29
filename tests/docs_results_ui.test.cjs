const {test} = require('node:test');
const assert = require('node:assert/strict');
const {createDisclosure, createTrajectory, focusQuestion, outcome, matchesQid} = require('../docs/site/results-ui.js');

class Element {
  constructor(tagName) { this.tagName = tagName; }
  children = [];
  open = false;
  append(child) { child.parent = this; this.children.push(child); }
  addEventListener(name, handler) { this[name] = handler; }
  get lastChild() { return this.children.at(-1); }
  querySelector(tag) { return this.children.find(c => c.tagName === tag) || this.children.map(c => c.querySelector(tag)).find(Boolean); }
  scrollIntoView(options) { this.scrolled = options; }
  focus(options) { this.focused = options || true; }
  remove() { this.parent.children.splice(this.parent.children.indexOf(this), 1); }
}
const document = { createElement: (tag) => new Element(tag) };
const elements = (e) => [e, ...e.children.flatMap(elements)];
const text = (e) => elements(e).map(n => n.textContent || '').join(' ');

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

test('comparison explains a parse failure with zero tools instead of a silent empty flow', () => {
  const record = {ok: false, matches_answer_json: false, llm_call_count: 1,
    tool_call_count: 0, transcript: [], failure_class: 'json_decode',
    error: "JSONDecodeError: Expecting ':' delimiter: line 1 column 6 (char 5)"};
  const flow = createTrajectory(document, record);
  assert.equal(outcome(record), 'Execution failed');
  assert.match(text(flow), /0 recorded steps/);
  assert.match(text(flow), /No tool was executed/);
  assert.match(text(flow), /JSONDecodeError: Expecting ':' delimiter/);
  assert.match(text(flow), /failed response text and tool arguments were not archived/);
  assert.equal(elements(flow).filter(n => n.tagName === 'li').length, 0);
});

test('counted calls without saved steps are not described as unexecuted', () => {
  const flow = createTrajectory(document, {tool_call_count: 2, transcript: []});
  assert.match(text(flow), /No tool steps were saved/);
  assert.doesNotMatch(text(flow), /No tool was executed/);
});

test('comparison and run pages share ordered steps with clickable handle lineage', () => {
  let serializations = 0;
  const record = {ok: true, matches_answer_json: true, transcript: [
    {action: {tool: 'node_scan', args: {label: 'Person'}}, result: {handle: 'h1', matched_count: 2,
      preview: {toJSON() { serializations++; return ['large preview']; }}}},
    {action: {tool: 'fetch', args: {from: 'h1'}}, result: {returned_count: 2, columns: ['name']}}
  ]};
  const flow = createTrajectory(document, record, 'comparison-ana');
  assert.equal(serializations, 0);
  assert.equal(outcome(record), 'Exact benchmark match');
  assert.deepEqual(elements(flow).filter(n => n.tagName === 'h4').map(n => n.textContent), ['node_scan', 'fetch']);
  assert.match(text(flow), /Created h1 · 2 matching rows/);
  assert.match(text(flow), /2 returned rows · Columns: name/);
  const handle = elements(flow).find(n => n.tagName === 'button' && n.textContent === 'h1');
  const response = elements(flow).find(n => n.id === 'comparison-ana-step-0');
  handle.click();
  assert.equal(response.open, true);
  assert.equal(response.scrolled.block, 'center');
  assert.equal(response.querySelector('summary').focused, true);
});

test('recovered tool errors remain visible without marking the final answer failed', () => {
  const record = {ok: true, matches_answer_json: true, transcript: [
    {action: {tool: 'expand'}, result: {error: 'Unknown handle: h1'}},
    {action: {tool: 'fetch'}, result: {returned_count: 1}}
  ]};
  assert.match(text(createTrajectory(document, record)), /Tool error: Unknown handle: h1/);
  assert.equal(outcome(record), 'Exact benchmark match');
  assert.equal(outcome({ok: true, matches_answer_json: false}), 'Executed, but answer mismatch');
});

test('a deep-linked question is scrolled into view and its heading receives focus', () => {
  const panel = document.createElement('section');
  const heading = document.createElement('h3');
  panel.append(heading);
  focusQuestion(panel);
  assert.equal(panel.scrolled.block, 'start');
  assert.equal(heading.tabIndex, -1);
  assert.deepEqual(heading.focused, {preventScroll: true});
});
