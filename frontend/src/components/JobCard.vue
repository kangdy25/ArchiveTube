<script setup>
import { computed } from 'vue'
import { FolderOpen, Copy, RotateCcw, Square, Trash2, ArrowUp, ArrowDown, LoaderCircle, CheckCircle2, AlertCircle } from 'lucide-vue-next'
import { bytes, duration, counts, statusLabels, terminal } from '../lib/format'
const props = defineProps({ job: Object, history: Boolean, busy: Boolean, canMoveUp: Boolean, canMoveDown: Boolean })
const emit = defineEmits(['action', 'move'])
const tally = computed(() => counts(props.job))
const current = computed(() => props.job.items.find(i => i.status === 'running'))
const active = computed(() => ['running', 'cancelling'].includes(props.job.status))
const ended = computed(() => terminal.includes(props.job.status))
const retryable = computed(() => ended.value && props.job.items.some(i => !['completed', 'skipped'].includes(i.status)))
const progress = computed(() => (tally.value.completed + tally.value.skipped) / props.job.items.length * 100)
const action = (name, arg) => emit('action', name, props.job, arg)
function copyLog() {
  action('copy_text', props.job.items.map(i => `${i.title}: ${statusLabels[i.status]}\n${i.error || ''}\n${i.error_detail || ''}\n${(i.warnings || []).join('\n')}`).join('\n\n'))
}
</script>

<template>
  <article class="job-card" :class="{ active, failed: ['partial', 'failed'].includes(job.status) }">
    <div class="job-top"><span class="status-pill" :class="job.status" aria-live="polite"><LoaderCircle v-if="active" :size="13" class="spin" /><CheckCircle2 v-else-if="job.status === 'completed'" :size="13" /><AlertCircle v-else-if="['partial', 'failed'].includes(job.status)" :size="13" />{{ statusLabels[job.status] }}</span><span class="job-format">{{ (job.options.format_type === 'video' ? job.options.video_format : job.options.audio_format).toUpperCase() }} · {{ job.items.length }}개</span></div>
    <h3 :title="job.title">{{ job.title }}</h3>
    <p v-if="history" class="job-date">{{ new Date(job.created_at * 1000).toLocaleString('ko-KR') }}</p>
    <div v-if="current" class="current-item"><p>{{ current.title }}</p><span>{{ job.status === 'cancelling' ? '취소 요청 중 · 진행 중인 변환은 완료 후 중단합니다' : statusLabels[current.stage] }}</span>
      <progress v-if="current.percent != null" :value="current.percent" max="100" :aria-label="current.title + ' 전송 진행률'" /><div v-else class="indeterminate" role="progressbar" aria-label="처리 중"></div>
      <div v-if="current.stage === 'downloading'" class="transfer-meta"><span>{{ bytes(current.downloaded_bytes) }} / {{ bytes(current.total_bytes) }}</span><span>{{ current.speed == null ? '속도 계산 중' : bytes(current.speed) + '/s' }} · {{ current.eta == null ? '남은 시간 계산 중' : duration(current.eta) + ' 남음' }}</span></div>
    </div>
    <div class="job-counts"><span>완료 <b>{{ tally.completed }}</b></span><span v-if="tally.skipped">건너뜀 <b>{{ tally.skipped }}</b></span><span :class="{ 'text-danger': tally.failed }">실패 <b>{{ tally.failed }}</b></span><span>남음 <b>{{ tally.remaining }}</b></span></div>
    <progress class="overall-progress" :value="progress" max="100" aria-label="전체 항목 저장 완료 비율" />
    <div class="job-actions">
      <template v-if="active"><button class="button small" :disabled="busy || job.status === 'cancelling'" @click="action('cancel_download')"><Square :size="13" />취소</button></template>
      <template v-else-if="!ended"><button class="icon-button" aria-label="대기 작업 위로" :disabled="!canMoveUp || busy" @click="emit('move', job.id, -1)"><ArrowUp :size="15" /></button><button class="icon-button" aria-label="대기 작업 아래로" :disabled="!canMoveDown || busy" @click="emit('move', job.id, 1)"><ArrowDown :size="15" /></button><button class="button small" :disabled="busy" @click="action('delete_job')"><Trash2 :size="13" />제거</button></template>
      <template v-else>
        <button v-if="tally.completed || tally.skipped" class="button small" :disabled="busy" @click="action('open_folder')"><FolderOpen :size="14" />폴더 열기</button>
        <button v-if="retryable" class="button small" :disabled="busy" @click="action('retry_download', false)"><RotateCcw :size="13" />{{ job.status === 'cancelled' ? '남은 항목 재시도' : '실패 항목 재시도' }}</button>
      </template>
    </div>
    <details v-if="ended || history" class="result-details">
      <summary>항목별 결과 · 상세 정보</summary>
      <ul><li v-for="item in job.items" :key="item.item_id">
        <strong>{{ item.title }}</strong>
        <span :class="{ 'text-danger': item.status === 'failed' }">{{ statusLabels[item.status] }}<template v-if="item.actual_quality"> · {{ item.actual_quality }}</template></span>
        <small v-if="item.path" class="file-path">{{ item.path }}<b v-if="item.file_exists === false" class="text-danger"> · 파일이 이동되거나 삭제됨</b></small>
        <p v-if="item.error" class="inline-error">{{ item.error }}</p>
        <details v-if="item.error_detail"><summary>오류 기술 상세</summary><pre>{{ item.error_detail }}</pre></details>
        <p v-for="warning in item.warnings" :key="warning" class="inline-warning">{{ warning }}</p>
      </li></ul>
      <button class="button small" @click="copyLog"><Copy :size="13" />결과 로그 복사</button>
    </details>
    <div v-if="history" class="history-actions"><button @click="action('copy_text', job.url)">URL 복사</button><button :disabled="busy" @click="action('retry_download', true)">같은 옵션으로 다시 다운로드</button><button :disabled="busy" class="text-danger" @click="action('delete_job')">기록 삭제</button></div>
  </article>
</template>
