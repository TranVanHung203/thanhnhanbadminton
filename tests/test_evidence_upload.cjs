const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class Element {
  constructor() { this.listeners = {}; this.children = []; this.value = ''; }
  addEventListener(event, callback) { this.listeners[event] = callback; }
  setAttribute() {}
  append(...children) { this.children.push(...children); }
  replaceChildren() { this.children = []; }
  querySelectorAll() { return this.children.flatMap((item) => item.children.filter((child) => child.type === 'button')); }
}

function setup() {
  const input = new Element();
  const list = new Element();
  const status = new Element();
  const form = new Element();
  const submit = new Element();
  const errors = new Element();
  form.elements = {month: {value: '2026-10'}, evidence_urls: {value: ''}};
  form.querySelector = () => submit;
  const elements = {
    '#match-form': form, '[data-evidence-files]': input,
    '[data-evidence-list]': list, '[data-upload-status]': status,
    '[data-form-errors]': errors,
  };
  const requests = [];
  const context = vm.createContext({
    document: {
      querySelector: (selector) => elements[selector] || null,
      querySelectorAll: () => [], createElement: () => new Element(),
    },
    FormData: class {
      constructor() { this.values = []; }
      append(key, value) { this.values.push([key, value]); }
      entries() { return this.values[Symbol.iterator](); }
    },
    fetch: async (url, options) => {
      requests.push({url, options});
      return context.response;
    },
    setTimeout: () => {},
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../app/static/js/app.js'), 'utf8'), context);
  const choose = (...files) => {
    input.files = files;
    input.value = 'chosen';
    input.listeners.change();
  };
  return {input, list, status, form, submit, context, requests, choose};
}

const photo = (name, size = 1024) => ({name, size, lastModified: 1});

test('single and multiple selections accumulate, cancel keeps photos, duplicates are ignored', () => {
  const ui = setup();
  ui.choose(photo('a.jpg'));
  ui.choose(photo('b.jpg'), photo('c.jpg'));
  ui.choose();
  ui.choose(photo('a.jpg'));
  assert.equal(ui.list.children.length, 3);
  assert.match(ui.status.textContent, /3\/6/);
  assert.equal(ui.input.value, '');
});

test('remove allows selecting the same photo again and reset clears the list', () => {
  const ui = setup();
  ui.choose(photo('a.jpg'), photo('b.jpg'));
  ui.list.children[0].children[1].listeners.click();
  assert.equal(ui.list.children.length, 1);
  ui.choose(photo('a.jpg'));
  assert.equal(ui.list.children.length, 2);
  ui.form.listeners.reset();
  assert.equal(ui.list.children.length, 0);
  assert.equal(ui.status.hidden, true);
});

test('limits apply across selections and oversized files do not discard valid photos', () => {
  const ui = setup();
  ui.choose(photo('too-large.jpg', 12 * 1024 * 1024 + 1), photo('a.jpg'));
  assert.equal(ui.list.children.length, 1);
  assert.match(ui.status.textContent, /12 MB/);
  ui.choose(...['b', 'c', 'd', 'e', 'f', 'g'].map((name) => photo(`${name}.jpg`)));
  assert.equal(ui.list.children.length, 6);
  assert.match(ui.status.textContent, /tối đa 6/);
});

test('failed upload keeps all accumulated photos for retry and re-enables controls', async () => {
  const ui = setup();
  ui.choose(photo('a.jpg'));
  ui.choose(photo('b.jpg'));
  ui.context.response = {ok: false, json: async () => ({message: 'Upload failed'})};
  await ui.form.listeners.submit({preventDefault() {}});
  assert.equal(ui.requests.length, 1);
  assert.deepEqual(ui.requests[0].options.body.values.filter(([key]) => key === 'files').map(([, file]) => file.name), ['a.jpg', 'b.jpg']);
  assert.equal(ui.list.children.length, 2);
  assert.equal(ui.input.disabled, false);
  assert.equal(ui.submit.disabled, false);
});

test('successful upload clears pending photos and preserves URLs if match submission fails', async () => {
  const ui = setup();
  ui.choose(photo('a.jpg'));
  ui.context.response = {ok: true, json: async () => ({files: [{url: 'https://drive.google.com/photo'}]})};
  ui.context.fetch = async (url, options) => {
    ui.requests.push({url, options});
    if (url === '/api/evidence') return ui.context.response;
    throw new Error('Match submission failed');
  };
  await ui.form.listeners.submit({preventDefault() {}});
  assert.equal(ui.list.children.length, 0);
  assert.equal(ui.form.elements.evidence_urls.value, 'https://drive.google.com/photo');
  await ui.form.listeners.submit({preventDefault() {}});
  assert.equal(ui.requests.filter((request) => request.url === '/api/evidence').length, 1);
});
