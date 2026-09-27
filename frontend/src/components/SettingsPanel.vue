<script setup>
import { ref, watch } from 'vue'
import { Save } from 'lucide-vue-next'
import DownloadOptions from './DownloadOptions.vue'
const props = defineProps({ settings: Object, busy: Boolean, capabilities: Object })
const emit = defineEmits(['save', 'choose-folder'])
const form = ref(JSON.parse(JSON.stringify(props.settings)))
const dirty = ref(false)
const section = ref('download')
const sections = [
  { id: 'download', label: '다운로드' },
  { id: 'archive', label: '자막·파일' },
  { id: 'display', label: '화면·편의' },
  { id: 'session', label: '로그인' },
]
watch(() => props.settings, value => { if (!dirty.value) form.value = JSON.parse(JSON.stringify(value)) }, { deep: true })
watch(() => form.value.format_type, value => {
  if (value === 'audio' && form.value.subtitle_mode === 'embed') form.value.subtitle_mode = 'file'
})
function setFolder(path) { form.value.download_dir = path; dirty.value = true }
function saved() { dirty.value = false }
defineExpose({ setFolder, saved })
</script>

<template>
  <form class="settings-layout settings-compact" @submit.prevent="emit('save', form)" @change="dirty = true" @input="dirty = true">
    <div class="settings-toolbar">
      <nav class="settings-sections" aria-label="설정 분류">
        <button v-for="item in sections" :key="item.id" type="button"
          :class="{ selected: section === item.id }" :aria-pressed="section === item.id"
          aria-controls="settings-content" @click="section = item.id">{{ item.label }}</button>
      </nav>
      <button class="button primary" :disabled="busy" type="submit"><Save :size="16" />{{ busy ? '저장 중…' : '저장' }}<span v-if="dirty" class="unsaved-dot" aria-label="저장하지 않은 변경 사항"></span></button>
    </div>
    <section id="settings-content" class="panel settings-panel" :aria-label="sections.find(item => item.id === section).label">
      <template v-if="section === 'download'">
        <DownloadOptions v-model="form" section="basic" @choose-folder="emit('choose-folder')" />
        <p class="field-hint">새 작업에 적용됩니다. 이미 등록한 작업은 바뀌지 않습니다.</p>
      </template>
      <DownloadOptions v-else-if="section === 'archive'" v-model="form" section="advanced" />
      <div v-else-if="section === 'display'" class="settings-general">
        <label>테마<select v-model="form.theme"><option value="dark">다크</option><option value="light">라이트</option><option value="system">시스템</option></select></label>
        <div class="settings-toggles">
          <label class="check"><input v-model="form.reduce_motion" type="checkbox" /> 애니메이션 줄이기</label>
          <label class="check"><input v-model="form.clipboard_monitor" type="checkbox" :disabled="!capabilities?.clipboard" /> 클립보드 링크 제안</label>
          <label class="check"><input v-model="form.notifications" type="checkbox" :disabled="!capabilities?.notifications" /> 다운로드 완료 알림</label>
          <p class="field-hint">알림을 켜면 저장 시 OS 권한을 요청합니다.</p>
          <p v-if="capabilities?.notification_error" class="inline-warning">시스템 설정에서 알림 권한을 확인하세요.</p>
        </div>
      </div>
      <template v-else>
        <div class="settings-session">
          <label>브라우저 세션<select v-model="form.cookie_browser"><option value="">사용 안 함</option><option v-for="browser in ['chrome', 'edge', 'firefox', 'safari', 'brave', 'chromium', 'opera', 'vivaldi', 'whale']" :key="browser" :value="browser" :disabled="browser === 'safari' && capabilities?.platform !== 'Darwin'">{{ browser }}</option></select></label>
          <label v-if="form.cookie_browser">프로필<input v-model="form.cookie_profile" placeholder="비워두면 기본 프로필" /></label>
        </div>
        <p class="field-hint">로그인이 필요한 영상에 사용합니다. 쿠키 값은 앱에 저장하지 않습니다.</p>
      </template>
    </section>
  </form>
</template>
