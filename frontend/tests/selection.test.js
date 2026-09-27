import test from 'node:test'
import assert from 'node:assert/strict'
import { changeSelection, filterEntries, parseRange, youtubeUrls } from '../src/lib/selection.js'
import { bytes, counts, duration } from '../src/lib/format.js'

const entries = Array.from({ length: 12 }, (_, index) => ({ index: index + 1, title: `영상 ${index + 1}`, is_available: index !== 4 }))
test('range selection preserves original indices and excludes unavailable items', () => {
  assert.deepEqual(parseRange('1–6, 10, 3', entries), [1, 2, 3, 4, 6, 10])
  for (const range of ['0', '7-2', 'x', '5', '999']) assert.throws(() => parseRange(range, entries))
})
test('filtered quick selection preserves hidden selections', () => {
  const visible = filterEntries(entries, '영상 1', false)
  assert.deepEqual(changeSelection([2], visible, 'all'), [1, 2, 10, 11, 12])
  assert.deepEqual(changeSelection([1, 2, 10], visible, 'clear'), [2])
  assert.deepEqual(changeSelection([1, 2, 10], visible, 'invert'), [2, 11, 12])
})
test('first and last five respect displayed available order', () => {
  assert.deepEqual(changeSelection([], entries, 'first'), [1, 2, 3, 4, 6])
  assert.deepEqual(changeSelection([], entries, 'last'), [8, 9, 10, 11, 12])
})
test('clipboard extracts only valid YouTube URLs without duplicates', () => {
  assert.deepEqual(youtubeUrls('text https://youtu.be/abc https://youtube.com.attacker.test/watch?v=x https://youtu.be/abc'), ['https://youtu.be/abc'])
  assert.deepEqual(youtubeUrls('https://youtube.com/@channel'), [])
})
test('unknown duration and transfer values do not imply live or zero', () => {
  assert.equal(duration(null), '길이 미확인'); assert.equal(duration(3601), '1:00:01')
  assert.equal(bytes(null), '계산 중'); assert.equal(bytes(0), '0 B')
  assert.deepEqual(counts({ items: ['completed', 'failed', 'cancelled', 'skipped'].map(status => ({ status })) }), { completed: 1, failed: 1, skipped: 1, remaining: 1 })
})
