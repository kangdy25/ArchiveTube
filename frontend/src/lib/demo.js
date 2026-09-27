// Explicit development-only preview. App.vue never imports this in production.
export function createDemo(onChange) {
  const defaults = { download_dir: '/Users/demo/Downloads', format_type: 'video', video_format: 'mp4', video_quality: 'best', audio_format: 'mp3', audio_bitrate: 192, collision: 'rename', subtitle_mode: 'off', subtitle_languages: ['ko', 'en'], auto_subtitles: false, save_thumbnail: false, save_description: false, save_metadata: false, theme: 'dark', reduce_motion: false, clipboard_monitor: false, notifications: false, cookie_browser: '', cookie_profile: '' }
  const state = { success: true, revision: 0, session_id: crypto.randomUUID(), paused: false, settings: { ...defaults }, jobs: [], capabilities: { clipboard: true, notifications: true, platform: 'Darwin' } }
  const clone = value => JSON.parse(JSON.stringify(value))
  const changed = () => { state.revision++; onChange(clone(state)) }
  const art = (text, color) => `data:image/svg+xml,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180"><rect width="320" height="180" fill="${color}"/><circle cx="270" cy="35" r="100" fill="white" opacity=".06"/><path d="M135 62L185 90L135 118Z" fill="white" opacity=".7"/><text x="20" y="158" fill="white" font-family="sans-serif" font-size="16">${text}</text></svg>`)}`
  const entries = [
    ['빛과 색으로 기록하는 하루', 742, '#514482'], ['서울의 작은 공간들', 513, '#355e64'],
    ['비 오는 날의 플레이리스트', 1820, '#495b86'], ['여행을 오래 기억하는 방법', 935, '#76644c'],
    ['나만의 아카이브 만들기', 628, '#654c73'], ['공개되지 않은 영상', null, '#333c51'],
  ].map(([title, duration, color], index) => ({ index: index + 1, id: `demo${index}`, url: `https://www.youtube.com/watch?v=demo${index}`, title, duration, uploader: 'Archive Studio', thumbnail: art(title, color), is_available: index !== 5, is_live: false }))
  let timer
  function run() {
    if (timer || state.paused) return
    const job = state.jobs.find(j => j.status === 'queued')
    if (!job) return
    job.status = 'running'; changed()
    timer = setInterval(() => {
      const item = job.items.find(i => !['completed', 'skipped'].includes(i.status))
      if (!item) {
        job.status = 'completed'; job.updated_at = Date.now() / 1000; clearInterval(timer); timer = null; changed(); run(); return
      }
      item.status = 'running'; item.percent = (item.percent || 0) + 12
      item.stage = item.percent >= 96 ? 'processing' : 'downloading'
      item.downloaded_bytes = Math.round(32e6 * Math.min(item.percent, 100) / 100); item.total_bytes = 32e6; item.speed = 5e6; item.eta = 6
      if (item.percent >= 108) { item.status = 'completed'; item.stage = 'completed'; item.percent = 100; item.path = `${job.options.download_dir}/${item.title}.mp4`; item.actual_quality = '1080p'; item.file_exists = true }
      job.updated_at = Date.now() / 1000; changed()
    }, 500)
  }
  const api = {
    get_state: async () => clone(state),
    get_info: async url => {
      const current = { ...entries[0], url, success: true, subtitle_languages: ['ko', 'en'], formats: [] }
      return url.includes('list=') ? { success: true, is_playlist: true, title: '일상을 기록하는 시선 · 영상 모음', url, thumbnail: art('ARCHIVE STUDIO', '#514482'), uploader: 'Archive Studio', entries, video_count: entries.length, current_video: url.includes('v=') ? current : null } : current
    },
    save_settings: async settings => { state.settings = clone(settings); changed(); return { success: true, settings } },
    choose_folder: async () => ({ success: true, path: '/Users/demo/Movies/ArchiveTube' }),
    enqueue_downloads: async requests => {
      const ids = []
      for (const request of requests) {
        const id = crypto.randomUUID(); ids.push(id)
        state.jobs.push({ ...clone(request), id, created_at: Date.now() / 1000, updated_at: Date.now() / 1000, status: 'queued', items: request.items.map(i => ({ ...clone(i), item_id: crypto.randomUUID(), status: 'pending', percent: 0, warnings: [] })) })
      }
      changed(); run(); return { success: true, job_ids: ids }
    },
    pause_queue: async () => { state.paused = true; changed(); return { success: true } },
    resume_queue: async () => { state.paused = false; run(); changed(); return { success: true } },
    cancel_download: async id => {
      const job = state.jobs.find(j => j.id === id)
      if (job.status === 'running') { clearInterval(timer); timer = null }
      job.status = 'cancelled'; job.items.forEach(i => { if (i.status !== 'completed') i.status = 'cancelled' }); changed(); run(); return { success: true }
    },
    reorder_queue: async ids => { state.jobs.sort((a, b) => ids.indexOf(a.id) - ids.indexOf(b.id)); changed(); return { success: true } },
    delete_job: async id => { state.jobs = state.jobs.filter(j => j.id !== id); changed(); return { success: true } },
    retry_download: async (id, all) => {
      const job = state.jobs.find(j => j.id === id)
      return api.enqueue_downloads([{ ...job, items: job.items.filter(i => all || !['completed', 'skipped'].includes(i.status)) }])
    },
    get_history: async (query = '', status = 'all') => ({ success: true, jobs: clone(state.jobs.filter(j => ['completed', 'partial', 'failed', 'cancelled'].includes(j.status) && j.title.includes(query) && (status === 'all' || j.status === status)).reverse()) }),
    read_clipboard: async () => ({ success: true, text: 'https://www.youtube.com/watch?v=demo&list=demo' }),
    copy_text: async () => ({ success: true }),
    open_folder: async () => ({ success: true }),
  }
  return api
}
