import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Playback } from '../src/playback.ts';

const stage = (id, role) => ({ id, type: 'stage', data: { role } });
const speech = (id, text) => ({ id, type: 'speech', data: { text } });

test('a burst stays in order and waits for the reader before the next speaker', () => {
  const queue = new Playback();
  queue.sync([stage(1, 'defesa'), speech(2, 'Uma fala.'), stage(3, 'oposicao'), speech(4, 'Outra fala.')]);
  queue.tick(900);
  queue.tick(100);
  assert.equal(queue.visible[1].data.text, 'Uma');
  queue.tick(1000);
  assert.equal(queue.waiting, true);
  queue.tick(60000);
  assert.equal(queue.cursor, 1);
  assert.equal(queue.visible.some(e => e.id === 3), false);
  queue.next();
  queue.tick(900);
  assert.equal(queue.visible.at(-1).data.role, 'oposicao');
});

test('pause freezes text; faster playback advances more characters without splitting emoji', () => {
  const queue = new Playback();
  queue.sync([speech(1, 'Olá 👩 é uma fala em português.')]);
  queue.tick(100);
  const before = queue.visible[0].data.text;
  queue.paused = true;
  queue.tick(10000);
  assert.equal(queue.visible[0].data.text, before);
  queue.paused = false;
  queue.speed = 2;
  queue.tick(100);
  assert.equal(queue.visible[0].data.text, 'Olá 👩 é um');
});

test('automatic reading holds the full speech and shows the result only afterwards', () => {
  const queue = new Playback();
  queue.automatic = true;
  queue.sync([speech(1, 'Fala.'), { id: 2, type: 'result', data: {} }]);
  queue.tick(1000);
  queue.tick(3499);
  assert.equal(queue.visible.some(e => e.type === 'result'), false);
  queue.tick(1);
  queue.tick(80);
  assert.equal(queue.visible.at(-1).type, 'result');
  assert.equal(queue.pending, false);
});

test('new arrivals, replay and showing all preserve original text and unique events', () => {
  const queue = new Playback();
  const first = speech(1, 'Argumento original.');
  queue.sync([first]);
  queue.tick(100);
  assert.equal(first.data.text, 'Argumento original.');
  queue.sync([first, speech(2, 'Nova fala.')]);
  queue.showAll();
  assert.deepEqual(queue.visible.map(e => e.id), [1, 2]);
  queue.reset();
  queue.tick(100);
  assert.equal(queue.visible.length, 1);
  assert.ok(queue.visible[0].data.text.length < first.data.text.length);
});

test('advancing during a stage never drops its event', () => {
  const queue = new Playback();
  queue.sync([stage(1, 'juiz'), speech(2, 'Decisão.')]);
  queue.next();
  assert.equal(queue.visible[0].data.role, 'juiz');
  queue.next();
  assert.equal(queue.visible[1].data.text, 'Decisão.');
  assert.equal(queue.waiting, true);
});
