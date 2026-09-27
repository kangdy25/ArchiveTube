export function parseRange(text, entries) {
  const indices = new Set(entries.filter(e => e.is_available).map(e => e.index))
  const result = new Set()
  if (!text.trim()) throw new Error('범위를 입력하세요. 예: 1–10, 15')
  for (const token of text.split(',')) {
    const match = token.trim().match(/^(\d+)\s*(?:[-–]\s*(\d+))?$/)
    if (!match) throw new Error('범위 형식을 확인하세요. 예: 1–10, 15')
    const start = Number(match[1]), end = Number(match[2] || match[1])
    if (!Number.isSafeInteger(start) || !Number.isSafeInteger(end) || start < 1 || end < start) {
      throw new Error('범위는 1 이상, 작은 순번부터 입력하세요.')
    }
    for (const index of indices) if (index >= start && index <= end) result.add(index)
  }
  if (!result.size) throw new Error('입력한 범위에 선택 가능한 영상이 없습니다.')
  return [...result].sort((a, b) => a - b)
}

export function filterEntries(entries, search, hideUnavailable) {
  return entries.filter(e => (!hideUnavailable || e.is_available) && e.title.toLocaleLowerCase().includes(search.toLocaleLowerCase()))
}

export function changeSelection(selected, visible, action) {
  const next = new Set(selected)
  let eligible = visible.filter(e => e.is_available).map(e => e.index)
  if (action === 'first') eligible = eligible.slice(0, 5)
  if (action === 'last') eligible = eligible.slice(-5)
  for (const index of eligible) {
    if (action === 'clear' || (action === 'invert' && next.has(index))) next.delete(index)
    else next.add(index)
  }
  return [...next].sort((a, b) => a - b)
}

export function youtubeUrls(text) {
  return [...new Set(text.split(/\s+/).filter(value => {
    try {
      const url = new URL(value)
      const allowed = ['youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com', 'youtu.be', 'www.youtu.be']
      return ['https:', 'http:'].includes(url.protocol) && allowed.includes(url.hostname) && !url.username && !url.password
        && (url.hostname.endsWith('youtu.be') ? url.pathname.length > 1 : (url.searchParams.has('v') || url.searchParams.has('list') || /^\/(shorts|live|embed)\/[^/]+/.test(url.pathname)))
    } catch { return false }
  }))]
}
