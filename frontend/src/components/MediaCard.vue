<script setup>
import { computed, ref, watch } from 'vue'
import { ArrowDownToLine, Search, X, ListVideo, ImageOff } from 'lucide-vue-next'
import DownloadOptions from './DownloadOptions.vue'
import { changeSelection, filterEntries, parseRange } from '../lib/selection'
import { duration } from '../lib/format'
const props = defineProps({ info: Object, settings: Object, hasQueue: Boolean, busy: Boolean })
const emit = defineEmits(['download', 'remove', 'choose-folder'])
const scope = ref(props.info.is_playlist ? 'playlist' : 'single')
const options = ref(JSON.parse(JSON.stringify(props.settings)))
const selected = ref((props.info.entries || []).filter(e => e.is_available).map(e => e.index))
const search = ref(''), range = ref(''), rangeError = ref(''), hideUnavailable = ref(false)
const brokenImages = ref(new Set())
const entries = computed(() => props.info.entries || [])
const visible = computed(() => filterEntries(entries.value, search.value, hideUnavailable.value))
const page = ref(1)
const pageSize = 8
const pageCount = computed(() => Math.max(1, Math.ceil(visible.value.length / pageSize)))
const pageEntries = computed(() => visible.value.slice((page.value - 1) * pageSize, page.value * pageSize))
watch([search, hideUnavailable], () => { page.value = 1 })
const media = computed(() => scope.value === 'single' ? (props.info.current_video || props.info) : props.info)
const chosen = computed(() => scope.value === 'single' ? [media.value] : entries.value.filter(e => selected.value.includes(e.index) && e.is_available))
const hiddenCount = computed(() => selected.value.filter(i => !visible.value.some(e => e.index === i)).length)
const totalDuration = computed(() => chosen.value.reduce((sum, e) => sum + (e.duration || 0), 0))
const unknownDuration = computed(() => chosen.value.filter(e => e.duration == null).length)
const quick = action => { selected.value = changeSelection(selected.value, visible.value, action) }
const applyRange = () => {
  try { selected.value = [...new Set([...selected.value, ...parseRange(range.value, entries.value)])]; rangeError.value = '' }
  catch (error) { rangeError.value = error.message }
}
function download() {
  if (!chosen.value.length || props.busy) return
  emit('download', { url: media.value.url, title: media.value.title, scope: scope.value,
    items: chosen.value, options: { ...options.value, subtitle_mode: options.value.format_type === 'audio' && options.value.subtitle_mode === 'embed' ? 'file' : options.value.subtitle_mode } })
}
watch(() => options.value.format_type, value => { if (value === 'audio' && options.value.subtitle_mode === 'embed') options.value.subtitle_mode = 'file' })
function setFolder(path) { options.value.download_dir = path }
defineExpose({ setFolder })
</script>

<template>
  <article class="panel media-card">
    <div class="media-heading">
      <div class="media-thumbnail"><img v-if="media.thumbnail && !brokenImages.has('main')" :src="media.thumbnail" :alt="media.title + ' 썸네일'" @error="brokenImages.add('main')" /><ImageOff v-else :size="24" /><span v-if="media.is_live" class="live-badge">실시간</span></div>
      <div class="media-heading-copy"><span class="eyebrow"><ListVideo :size="13" /> {{ scope === 'playlist' ? `재생목록 · ${entries.length}개` : '단일 영상' }}</span><h3 :title="media.title">{{ media.title }}</h3><p>{{ media.uploader || 'YouTube' }}<template v-if="scope === 'single'"> · {{ duration(media.duration) }}</template></p></div>
      <button class="icon-button" aria-label="분석 결과 닫기" @click="emit('remove')"><X :size="18" /></button>
    </div>
    <div v-if="info.current_video" class="segmented" aria-label="다운로드 범위"><button :class="{ selected: scope === 'playlist' }" :aria-pressed="scope === 'playlist'" @click="scope = 'playlist'">재생목록</button><button :class="{ selected: scope === 'single' }" :aria-pressed="scope === 'single'" @click="scope = 'single'">현재 영상만</button></div>
    <p v-for="warning in info.warnings" :key="warning" class="inline-warning">{{ warning }}</p>
    <section v-if="scope === 'playlist'" class="playlist-section" aria-label="다운로드할 영상 선택">
      <div class="search-field"><Search :size="16" /><input v-model="search" aria-label="재생목록 제목 검색" placeholder="목록에서 영상 검색" /></div>
      <div class="selection-tools"><button @click="quick('all')">전체 선택</button><button @click="quick('clear')">선택 해제</button><button @click="quick('invert')">선택 반전</button><button @click="quick('first')">처음 5개</button><button @click="quick('last')">마지막 5개</button></div>
      <div class="range-tools"><input v-model="range" aria-label="영상 순번 범위" placeholder="범위: 1–10, 15" @keydown.enter.prevent="applyRange" /><button class="button small" @click="applyRange">범위 추가</button><label class="check"><input v-model="hideUnavailable" type="checkbox" /> 사용 불가 숨기기</label></div>
      <p v-if="rangeError" role="alert" class="inline-error">{{ rangeError }}</p>
      <div class="playlist-list">
        <label v-for="entry in pageEntries" :key="entry.index" class="playlist-row" :class="{ unavailable: !entry.is_available, checked: selected.includes(entry.index) }">
          <input v-model="selected" type="checkbox" :value="entry.index" :disabled="!entry.is_available" :aria-label="entry.title + ' 선택'" />
          <span class="entry-number">{{ String(entry.index).padStart(2, '0') }}</span>
          <div class="entry-thumbnail"><img v-if="entry.thumbnail && !brokenImages.has(entry.index)" :src="entry.thumbnail" :alt="entry.title + ' 썸네일'" loading="lazy" @error="brokenImages.add(entry.index)" /><ImageOff v-else :size="16" /></div>
          <div class="entry-copy"><span :title="entry.title">{{ entry.title }}</span><small>{{ entry.uploader || '업로더 정보 없음' }}</small></div>
          <span class="entry-duration">{{ !entry.is_available ? '사용 불가' : entry.is_live ? '실시간' : duration(entry.duration) }}</span>
        </label>
        <p v-if="!visible.length" class="empty-inline">검색 결과가 없습니다.</p>
      </div>
      <nav v-if="pageCount > 1" class="playlist-pagination" aria-label="재생목록 페이지">
        <span role="status" aria-live="polite">{{ page }} / {{ pageCount }} 페이지 · 검색 결과 {{ visible.length }}개</span>
        <div><button class="button small" :disabled="page === 1" @click="page--">이전</button><button class="button small" :disabled="page === pageCount" @click="page++">다음</button></div>
      </nav>
      <p class="selection-hint">빠른 선택은 다른 페이지를 포함한 검색·필터 결과 전체에 적용됩니다.<span v-if="hiddenCount"> 필터 밖 {{ hiddenCount }}개 선택 유지</span></p>
    </section>
    <div class="card-options"><DownloadOptions v-model="options" @choose-folder="emit('choose-folder')" /></div>
    <footer class="download-bar"><div><strong>{{ chosen.length }}개 선택 <span>· {{ duration(totalDuration) }}</span></strong><small v-if="unknownDuration">길이 미확인 {{ unknownDuration }}개 제외</small><small :title="options.download_dir">{{ options.download_dir }}</small></div><button class="button primary" :disabled="!chosen.length || busy" @click="download"><ArrowDownToLine :size="17" />{{ busy ? '등록 중…' : hasQueue ? '대기열에 추가' : '다운로드' }}</button></footer>
  </article>
</template>
