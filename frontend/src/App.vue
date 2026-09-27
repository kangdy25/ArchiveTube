<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Archive, ArrowDownToLine, ClipboardPaste, Search, History, Settings2, FolderOpen, Plus, ArrowRight, ListOrdered, Pause, Play, X, CheckCircle2, AlertCircle, LoaderCircle, Link, Inbox } from 'lucide-vue-next'
import MediaCard from './components/MediaCard.vue'
import JobCard from './components/JobCard.vue'
import SettingsPanel from './components/SettingsPanel.vue'
import { terminal } from './lib/format'
import { youtubeUrls } from './lib/selection'

const tab = ref('download'), input = ref(''), analyzing = ref(false), connected = ref(false)
const state = ref({ jobs: [], paused: false, settings: null, revision: -1, session_id: '' })
const capabilities = ref({}), drafts = ref([]), historyJobs = ref([])
const historySearch = ref(''), historyFilter = ref('all'), notice = ref(null), busy = ref(false)
const clipboardSuggestion = ref(''), settingsPanel = ref(null), cards = new Map()
const demo = import.meta.env.DEV && new URLSearchParams(location.search).get('demo') === '1'
let api, polling, noticeTimer, historyTimer, historyRequest = 0, disposed = false, connecting = false
const seenClipboard = new Set()
const pendingJobs = computed(() => state.value.jobs.filter(j => !terminal.includes(j.status)))
const queuedJobs = computed(() => pendingJobs.value.filter(j => !['running', 'cancelling'].includes(j.status)))
const activeJob = computed(() => pendingJobs.value.find(j => ['running', 'cancelling'].includes(j.status)))
const latestJob = computed(() => [...state.value.jobs].filter(j => terminal.includes(j.status)).sort((a, b) => b.updated_at - a.updated_at)[0])
const completedCount = computed(() => state.value.jobs.reduce((n, j) => n + j.items.filter(i => i.status === 'completed').length, 0))
const historyCount = computed(() => state.value.jobs.filter(j => terminal.includes(j.status)).length)
const systemDark = window.matchMedia('(prefers-color-scheme: dark)')

function applyState(value) {
  if (value.session_id === state.value.session_id && value.revision < state.value.revision) return
  state.value = value
  if (value.capabilities) capabilities.value = value.capabilities
}
function showNotice(text, error = false, detail = '') {
  clearTimeout(noticeTimer)
  notice.value = { text, error, detail }
  if (!error) noticeTimer = setTimeout(() => { notice.value = null }, 4500)
}
async function call(name, ...args) {
  if (!api || !connected.value) throw new Error('데스크톱 앱과 연결되지 않았습니다. 앱을 실행하고 다시 연결하세요.')
  const result = await api[name](...args)
  if (!result?.success) { const error = new Error(result?.error || '요청을 처리하지 못했습니다.'); error.detail = result?.detail; throw error }
  return result
}
async function refresh() { if (api) applyState(await call('get_state')) }
async function connect() {
  if (connecting || disposed) return
  connecting = true
  try {
    if (import.meta.env.DEV && demo) api = (await import('./lib/demo')).createDemo(applyState)
    else api = window.pywebview?.api
    if (!api) { connected.value = false; return }
    connected.value = true
    await refresh()
  } catch (error) { connected.value = false; showNotice(error.message, true) }
  finally { connecting = false }
}
async function analyze() {
  if (analyzing.value || !input.value.trim()) return
  const urls = input.value.trim().split(/\s+/)
  if (urls.length > 100) return showNotice('URL은 한 번에 100개까지 분석할 수 있습니다.', true)
  analyzing.value = true
  tab.value = 'download'
  for (const url of [...new Set(urls)]) {
    const id = crypto.randomUUID()
    drafts.value.push({ id, url, loading: true, error: null, info: null })
    const draft = drafts.value.find(d => d.id === id)
    try {
      if (!youtubeUrls(url).length) throw new Error('YouTube 영상 또는 재생목록 URL을 입력하세요.')
      draft.info = await call('get_info', url)
    } catch (error) { draft.error = error.message; draft.detail = error.detail }
    finally { draft.loading = false }
  }
  analyzing.value = false
  input.value = ''
}
async function retryAnalysis(draft) {
  draft.loading = true; draft.error = null
  try { draft.info = await call('get_info', draft.url) }
  catch (error) { draft.error = error.message; draft.detail = error.detail }
  finally { draft.loading = false }
}
async function act(action) {
  if (busy.value) return
  busy.value = true
  try { await action(); await refresh(); if (tab.value === 'history') await loadHistory() }
  catch (error) { showNotice(error.message, true, error.detail) }
  finally { busy.value = false }
}
async function enqueue(request, draftId) {
  await act(async () => {
    await call('enqueue_downloads', [request])
    drafts.value = drafts.value.filter(d => d.id !== draftId)
    showNotice(state.value.paused ? '대기열에 추가했습니다. 재개를 누르면 시작합니다.' : '다운로드 대기열에 추가했습니다.')
  })
}
async function jobAction(name, job, argument) {
  await act(async () => {
    if (name === 'copy_text') { await call(name, argument); showNotice('클립보드에 복사했습니다.'); return }
    if (name === 'retry_download') { await call(name, job.id, Boolean(argument)); tab.value = 'download'; showNotice('재시도 작업을 대기열에 추가했습니다.'); return }
    await call(name, job.id)
    if (name === 'delete_job') showNotice('목록에서 제거했습니다. 저장된 파일은 유지됩니다.')
  })
}
async function moveJob(id, direction) {
  const ids = queuedJobs.value.map(j => j.id), index = ids.indexOf(id), target = index + direction
  if (target < 0 || target >= ids.length) return
  ;[ids[index], ids[target]] = [ids[target], ids[index]]
  await act(() => call('reorder_queue', ids))
}
async function chooseFolder(draftId) {
  try {
    const result = await call('choose_folder')
    if (result.path) { if (draftId) cards.get(draftId)?.setFolder(result.path); else settingsPanel.value?.setFolder(result.path) }
  } catch (error) { showNotice(error.message, true) }
}
async function saveSettings(values) {
  await act(async () => { await call('save_settings', JSON.parse(JSON.stringify(values))); settingsPanel.value?.saved(); showNotice('설정을 저장했습니다.') })
}
async function paste() {
  try { input.value = (await call('read_clipboard')).text; document.querySelector('#url-input')?.focus() }
  catch (error) { showNotice(error.message, true) }
}
async function detectClipboard() {
  if (!connected.value || !state.value.settings?.clipboard_monitor) return
  try {
    const text = (await call('read_clipboard')).text
    const urls = youtubeUrls(text).join('\n')
    if (!urls || seenClipboard.has(urls)) return
    seenClipboard.add(urls)
    clipboardSuggestion.value = urls
  } catch { /* Manual paste remains available and exposes errors on explicit use. */ }
}
function acceptClipboard() {
  input.value = [input.value.trim(), clipboardSuggestion.value].filter(Boolean).join('\n')
  clipboardSuggestion.value = ''
}
async function loadHistory() {
  if (!connected.value) return
  const request = ++historyRequest
  try {
    const result = await call('get_history', historySearch.value, historyFilter.value)
    if (request === historyRequest) historyJobs.value = result.jobs
  }
  catch (error) { showNotice(error.message, true) }
}
function applyTheme() {
  const settings = state.value.settings
  document.documentElement.dataset.theme = settings?.theme === 'system' ? (systemDark.matches ? 'dark' : 'light') : settings?.theme || 'dark'
  document.documentElement.dataset.reducedMotion = String(Boolean(settings?.reduce_motion))
}
watch(() => state.value.settings, applyTheme, { deep: true })
watch([tab, historySearch, historyFilter, () => state.value.revision], () => {
  if (tab.value === 'history') { clearTimeout(historyTimer); historyTimer = setTimeout(loadHistory, 150) }
})
onMounted(async () => {
  window.archiveStateChanged = applyState
  window.addEventListener('pywebviewready', connect)
  window.addEventListener('focus', detectClipboard)
  systemDark.addEventListener('change', applyTheme)
  await connect()
  polling = setInterval(async () => {
    if (!connected.value) { if (window.pywebview?.api) await connect(); return }
    try { await refresh() } catch { connected.value = false }
  }, 3000)
})
onBeforeUnmount(() => {
  disposed = true; clearInterval(polling); clearTimeout(historyTimer); clearTimeout(noticeTimer)
  window.removeEventListener('pywebviewready', connect); window.removeEventListener('focus', detectClipboard)
  systemDark.removeEventListener('change', applyTheme); delete window.archiveStateChanged
})
</script>

<template>
  <div class="app-shell">
    <header class="app-header"><a class="brand" href="#" @click.prevent="tab = 'download'"><span class="brand-mark"><Archive :size="23" /></span><span>ArchiveTube<small>나만의 미디어 아카이브</small></span></a><div class="header-actions"><span class="connection-indicator" :class="{ online: connected }"><i></i>{{ demo ? '데모 모드' : connected ? '연결됨' : '연결 대기' }}</span><button class="icon-button" aria-label="기본 다운로드 폴더 열기" :disabled="!connected" @click="act(() => call('open_folder'))"><FolderOpen :size="19" /></button></div></header>
    <nav class="tabs" aria-label="주 메뉴"><button :class="{ selected: tab === 'download' }" :aria-current="tab === 'download' ? 'page' : undefined" @click="tab = 'download'"><ArrowDownToLine :size="17" />다운로드<span v-if="pendingJobs.length" class="tab-count">{{ pendingJobs.length }}</span></button><button :class="{ selected: tab === 'history' }" :aria-current="tab === 'history' ? 'page' : undefined" @click="tab = 'history'"><History :size="17" />기록<span v-if="historyCount" class="tab-count">{{ historyCount }}</span></button><button :class="{ selected: tab === 'settings' }" :aria-current="tab === 'settings' ? 'page' : undefined" @click="tab = 'settings'"><Settings2 :size="17" />설정</button></nav>
    <main>
      <div v-if="demo" class="demo-banner">화면 확인용 데모입니다. 실제 파일은 다운로드하지 않습니다.</div>
      <div v-if="!connected" class="connection-banner" role="status"><AlertCircle :size="20" /><div><strong>데스크톱 앱에 연결해 주세요</strong><p>ArchiveTube 앱을 실행하면 다운로드·기록·설정을 사용할 수 있습니다.</p></div><button class="button small" @click="connect">연결 다시 확인</button></div>
      <section v-if="tab === 'download'" aria-labelledby="download-title">
        <div class="page-heading"><div><span class="eyebrow">나의 미디어 라이브러리</span><h1 id="download-title">좋아하는 영상을, 오래도록.</h1><p>영상과 재생목록을 원하는 형식으로 정리해 보관하세요.</p></div><div class="library-stat"><strong>{{ completedCount }}</strong><span>보관한 영상</span></div></div>
        <div class="workspace-grid">
          <div class="download-workspace">
            <section class="panel input-panel"><header class="step-heading"><span>01</span><h2>URL 분석</h2><span class="subtle">여러 링크를 한 번에</span></header><form @submit.prevent="analyze"><label class="sr-only" for="url-input">YouTube URL · 여러 개는 줄바꿈으로 입력</label><textarea id="url-input" v-model="input" placeholder="YouTube 영상 또는 재생목록 URL을 붙여넣으세요.&#10;여러 링크는 줄바꿈으로 구분할 수 있어요." rows="3" :disabled="analyzing" @keydown.ctrl.enter.prevent="analyze" @keydown.meta.enter.prevent="analyze"></textarea><div class="input-actions"><button type="button" class="text-button" :disabled="!connected || analyzing" @click="paste"><ClipboardPaste :size="16" />붙여넣기</button><span class="keyboard-hint">⌘ / Ctrl + Enter</span><button type="submit" class="button primary" :disabled="!connected || analyzing || !input.trim()"><LoaderCircle v-if="analyzing" :size="16" class="spin" /><Search v-else :size="16" />{{ analyzing ? '분석 중…' : '링크 분석' }}</button></div></form></section>
            <div v-if="clipboardSuggestion" class="clipboard-suggestion"><Link :size="18" /><span>클립보드에서 새 YouTube 링크를 찾았습니다.</span><button class="text-button" @click="acceptClipboard">입력창에 추가</button><button class="icon-button" aria-label="클립보드 제안 닫기" @click="clipboardSuggestion = ''"><X :size="15" /></button></div>
            <div v-if="drafts.length" class="step-heading outside"><span>02</span><h2>항목과 저장 옵션</h2></div>
            <template v-for="draft in drafts" :key="draft.id">
              <div v-if="draft.loading" class="panel analysis-loading" role="status"><LoaderCircle :size="22" class="spin" /><div><strong>영상 정보를 가져오고 있습니다</strong><p>{{ draft.url }}</p></div></div>
              <div v-else-if="draft.error" class="panel analysis-error" role="alert"><AlertCircle :size="20" /><div><strong>{{ draft.error }}</strong><p>{{ draft.url }}</p><details v-if="draft.detail"><summary>기술 상세</summary><pre>{{ draft.detail }}</pre></details><div class="row-actions"><button class="button small" @click="retryAnalysis(draft)">다시 분석</button><button class="button small" @click="tab = 'settings'">설정 열기</button><button class="button small" @click="drafts = drafts.filter(d => d.id !== draft.id)">닫기</button></div></div></div>
              <MediaCard v-else-if="draft.info && state.settings" :ref="el => el ? cards.set(draft.id, el) : cards.delete(draft.id)" :info="draft.info" :settings="state.settings" :busy="busy" :has-queue="pendingJobs.length > 0" @download="enqueue($event, draft.id)" @remove="drafts = drafts.filter(d => d.id !== draft.id)" @choose-folder="chooseFolder(draft.id)" />
            </template>
            <div v-if="!drafts.length" class="empty-workspace"><div class="empty-art"><Archive :size="34" /><span class="orbit-dot"></span></div><h2>보관할 첫 링크를 추가해 보세요</h2><p>재생목록에서 원하는 영상만 골라<br />MP4, WebM, MP3, M4A로 저장할 수 있어요.</p><div class="feature-chips"><span>화질 선택</span><span>자막 함께 저장</span><span>자동 순차 다운로드</span></div></div>
          </div>
          <aside class="queue-sidebar" aria-label="다운로드 대기열"><div class="queue-heading"><div><ListOrdered :size="19" /><h2>다운로드 큐</h2><span class="tab-count">{{ pendingJobs.length }}</span></div><button v-if="pendingJobs.length" class="icon-button" :aria-label="state.paused ? '대기열 재개' : '다음 작업 시작 일시정지'" :disabled="busy" @click="act(() => call(state.paused ? 'resume_queue' : 'pause_queue'))"><Play v-if="state.paused" :size="17" /><Pause v-else :size="17" /></button></div>
            <div v-if="state.paused" class="queue-paused"><Pause :size="15" /><p>대기열이 일시정지되었습니다.<br /><small>재개하면 미완료 작업부터 시작합니다.</small></p><button class="button small" :disabled="busy" @click="act(() => call('resume_queue'))">재개</button></div>
            <p class="queue-caption">한 번에 하나씩, 순서대로 저장합니다.</p>
            <JobCard v-if="activeJob" :job="activeJob" :busy="busy" @action="jobAction" />
            <JobCard v-for="(job, index) in queuedJobs" :key="job.id" :job="job" :busy="busy" :can-move-up="index > 0" :can-move-down="index < queuedJobs.length - 1" @action="jobAction" @move="moveJob" />
            <div v-if="!pendingJobs.length" class="empty-queue"><Inbox :size="30" /><strong>대기 중인 작업이 없어요</strong><span>분석한 영상을 다운로드하면<br />여기에서 진행 상황을 볼 수 있어요.</span></div>
            <template v-if="latestJob"><div class="recent-heading"><span>최근 완료한 작업</span><button class="text-button" @click="tab = 'history'">전체 기록 <ArrowRight :size="13" /></button></div><JobCard :job="latestJob" :busy="busy" @action="jobAction" /><button v-if="!pendingJobs.length" class="button full" @click="input = ''; nextTick(() => document.querySelector('#url-input')?.focus())"><Plus :size="15" />새 URL 분석</button></template>
          </aside>
        </div>
      </section>
      <section v-if="tab === 'history'" aria-labelledby="history-title"><div class="page-heading"><div><span class="eyebrow">내 기기에 쌓이는 기록</span><h1 id="history-title">다운로드 기록</h1><p>저장한 파일을 찾고, 중단된 작업을 다시 시작하세요.</p></div><button class="button" :disabled="!connected" @click="loadHistory"><History :size="16" />새로고침</button></div><div class="history-toolbar"><div class="search-field"><Search :size="17" /><input v-model="historySearch" placeholder="제목으로 기록 검색" aria-label="다운로드 기록 검색" /></div><select v-model="historyFilter" aria-label="기록 상태 필터"><option value="all">모든 상태</option><option value="completed">완료</option><option value="partial">일부 실패</option><option value="failed">실패</option><option value="cancelled">취소됨</option></select></div><div class="history-grid"><JobCard v-for="job in historyJobs" :key="job.id" :job="job" history :busy="busy" @action="jobAction" /></div><div v-if="!historyJobs.length" class="empty-workspace"><History :size="36" /><h2>표시할 기록이 없습니다</h2><p>완료되거나 취소한 작업이 여기에 저장됩니다.</p></div></section>
      <section v-if="tab === 'settings'" class="settings-page" aria-labelledby="settings-title"><div class="page-heading"><h1 id="settings-title">설정</h1></div><SettingsPanel v-if="state.settings" ref="settingsPanel" :settings="state.settings" :capabilities="capabilities" :busy="busy" @save="saveSettings" @choose-folder="chooseFolder()" /></section>
    </main>
    <footer v-if="tab !== 'settings'" class="app-footer"><span>ArchiveTube</span><span>보관할 권한이 있는 콘텐츠에 사용하세요.</span></footer>
    <div v-if="notice" class="toast" :class="{ error: notice.error }" :role="notice.error ? 'alert' : 'status'"><AlertCircle v-if="notice.error" :size="19" /><CheckCircle2 v-else :size="19" /><div>{{ notice.text }}<details v-if="notice.detail"><summary>기술 상세</summary><pre>{{ notice.detail }}</pre></details></div><button class="icon-button" aria-label="알림 닫기" @click="notice = null"><X :size="16" /></button></div>
  </div>
</template>
