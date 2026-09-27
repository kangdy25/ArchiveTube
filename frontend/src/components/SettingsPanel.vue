<script setup>
import { ref, watch } from 'vue'
import { Save, Palette, Settings2, ShieldCheck, Bell, FolderOpen } from 'lucide-vue-next'
import DownloadOptions from './DownloadOptions.vue'
const props = defineProps({ settings: Object, busy: Boolean, capabilities: Object })
const emit = defineEmits(['save', 'choose-folder'])
const form = ref(JSON.parse(JSON.stringify(props.settings)))
const dirty = ref(false)
watch(() => props.settings, value => { if (!dirty.value) form.value = JSON.parse(JSON.stringify(value)) }, { deep: true })
function setFolder(path) { form.value.download_dir = path; dirty.value = true }
function saved() { dirty.value = false }
defineExpose({ setFolder, saved })
</script>

<template>
  <form class="settings-layout" @submit.prevent="emit('save', form)" @change="dirty = true" @input="dirty = true">
    <section class="panel settings-panel"><header class="section-heading"><Settings2 :size="20" /><div><h2>다운로드 기본값</h2><p>새로 분석하는 영상에 적용됩니다. 대기열의 옵션은 유지됩니다.</p></div></header><DownloadOptions v-model="form" advanced-open @choose-folder="emit('choose-folder')" /></section>
    <div class="settings-side">
      <section class="panel settings-panel"><header class="section-heading"><Palette :size="20" /><div><h2>화면</h2><p>작업 공간을 편안하게</p></div></header><label>테마<select v-model="form.theme"><option value="dark">다크</option><option value="light">라이트</option><option value="system">시스템 설정</option></select></label><label class="check"><input v-model="form.reduce_motion" type="checkbox" /> 애니메이션 줄이기</label></section>
      <section class="panel settings-panel"><header class="section-heading"><Bell :size="20" /><div><h2>작업 편의 기능</h2></div></header><label class="check"><input v-model="form.clipboard_monitor" type="checkbox" :disabled="!capabilities?.clipboard" /> 클립보드 URL 자동 감지</label><p class="field-hint">앱으로 돌아올 때 새 YouTube URL을 제안합니다. 자동으로 다운로드하지 않습니다.</p><label class="check"><input v-model="form.notifications" type="checkbox" :disabled="!capabilities?.notifications" /> 대기열 완료 시 시스템 알림</label><p class="field-hint">저장 시 OS 알림 권한을 요청합니다. 취소된 작업만 있으면 알리지 않습니다.</p><p v-if="capabilities?.notification_error" class="inline-warning">알림을 표시하지 못했습니다. OS 알림 설정과 앱 서명을 확인하세요.</p></section>
      <section class="panel settings-panel"><header class="section-heading"><ShieldCheck :size="20" /><div><h2>브라우저 로그인 세션</h2><p>로그인이 필요한 콘텐츠에 사용</p></div></header><label>쿠키를 가져올 브라우저<select v-model="form.cookie_browser"><option value="">사용 안 함</option><option v-for="browser in ['chrome', 'edge', 'firefox', 'safari', 'brave', 'chromium', 'opera', 'vivaldi', 'whale']" :key="browser" :value="browser" :disabled="browser === 'safari' && capabilities?.platform !== 'Darwin'">{{ browser }}</option></select></label><label v-if="form.cookie_browser">프로필 이름 또는 경로<input v-model="form.cookie_profile" placeholder="비워두면 기본 프로필" /></label><p class="field-hint">분석과 다운로드에 동일한 세션을 사용합니다. 쿠키 값은 앱 기록에 저장하지 않습니다.</p></section>
    </div>
    <footer class="settings-save"><span>{{ dirty ? '저장하지 않은 변경 사항이 있습니다.' : '설정은 이 기기에 저장됩니다.' }}</span><button class="button primary" :disabled="busy" type="submit"><Save :size="16" />{{ busy ? '저장 중…' : '설정 저장' }}</button></footer>
  </form>
</template>
