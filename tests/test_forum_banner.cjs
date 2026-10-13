const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

async function setup(posts = [], reduced = false, pathname = '/') {
  const timers = new Map();
  let timerId = 0;
  const text = {
    scrollWidth: 300, offsetWidth: 300, listeners: {},
    style: {setProperty() {}}, classList: {remove() {}, add() {}},
    addEventListener(name, callback) { this.listeners[name] = callback; },
  };
  const link = {setAttribute() {}};
  const banner = {hidden: true, querySelector: (selector) => ({
    '[data-forum-banner-link]': link, '[data-forum-banner-text]': text,
    '.forum-banner-track': {clientWidth: 500},
  })[selector]};
  const doc = {hidden: false, listeners: {}, querySelector: () => banner,
    addEventListener(name, callback) { this.listeners[name] = callback; }};
  const ui = {banner, link, text, doc, timers, posts, requests: 0, fail: false};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../app/static/js/forum-banner.js'), 'utf8'), {
    document: doc,
    window: {location: {pathname}, matchMedia: () => ({matches: reduced, addEventListener() {}})},
    Math: {random: () => 0, floor: Math.floor, max: Math.max},
    fetch: async () => { ui.requests++; return {ok: !ui.fail, json: async () => ({posts: ui.posts})}; },
    setTimeout: (callback, delay) => { timers.set(++timerId, {callback, delay}); return timerId; },
    clearTimeout: (id) => timers.delete(id),
  });
  await new Promise(setImmediate);
  ui.runTimer = async (delay) => {
    const entry = [...timers].find(([, timer]) => timer.delay === delay);
    assert.ok(entry, `Expected timer ${delay}ms`);
    timers.delete(entry[0]);
    await entry[1].callback();
  };
  return ui;
}

const posts = [
  {id: '1', title: 'Hẹn ra sân', author_name: 'Lan', url: '/dien-dan/1'},
  {id: '2', title: 'Chia sẻ kinh nghiệm', author_name: 'Hùng', url: '/dien-dan/2'},
];

test('one pass hides the banner, waits 20 seconds, then shows a different post', async () => {
  const ui = await setup(posts);
  assert.equal(ui.banner.hidden, false);
  assert.equal(ui.link.href, '/dien-dan/1');
  assert.match(ui.text.textContent, /Lan chia sẻ: Hẹn ra sân/);
  assert.equal(ui.timers.size, 0);
  ui.text.listeners.animationend({animationName: 'forum-banner-pass'});
  assert.equal(ui.banner.hidden, true);
  assert.equal([...ui.timers.values()][0].delay, 20000);
  await ui.runTimer(20000);
  assert.equal(ui.banner.hidden, false);
  assert.equal(ui.link.href, '/dien-dan/2');
  assert.equal(ui.requests, 2);
});

test('empty feed stays hidden and retries; refreshed feed excludes deleted posts', async () => {
  const ui = await setup([]);
  assert.equal(ui.banner.hidden, true);
  ui.posts = posts;
  await ui.runTimer(20000);
  assert.equal(ui.banner.hidden, false);
  ui.text.listeners.animationend({animationName: 'forum-banner-pass'});
  ui.posts = [posts[1]];
  await ui.runTimer(20000);
  assert.equal(ui.link.href, '/dien-dan/2');
});

test('current thread is skipped and post text is assigned as plain text', async () => {
  const ui = await setup([posts[0], {...posts[1], title: '<script>alert(1)</script>'}], false, '/dien-dan/1');
  assert.equal(ui.link.href, '/dien-dan/2');
  assert.match(ui.text.textContent, /<script>/);
});

test('reduced motion shows static text briefly, then waits 20 seconds', async () => {
  const ui = await setup(posts, true);
  await ui.runTimer(8000);
  assert.equal(ui.banner.hidden, true);
  assert.equal([...ui.timers.values()][0].delay, 20000);
});

test('background tabs hide the banner and stop timers until visible again', async () => {
  const ui = await setup(posts);
  ui.doc.hidden = true;
  ui.doc.listeners.visibilitychange();
  assert.equal(ui.banner.hidden, true);
  assert.equal(ui.timers.size, 0);
  ui.doc.hidden = false;
  ui.doc.listeners.visibilitychange();
  await ui.runTimer(20000);
  assert.equal(ui.banner.hidden, false);
});

test('feed failure hides banner and schedules another attempt', async () => {
  const ui = await setup(posts);
  ui.text.listeners.animationend({animationName: 'forum-banner-pass'});
  ui.fail = true;
  await ui.runTimer(20000);
  assert.equal(ui.banner.hidden, true);
  assert.equal([...ui.timers.values()][0].delay, 20000);
});
