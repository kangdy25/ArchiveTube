<script setup>
import { computed } from 'vue'
import { FolderOpen, SlidersHorizontal } from 'lucide-vue-next'
const props = defineProps({ modelValue: { type: Object, required: true }, advancedOpen: Boolean, disabled: Boolean, section: { type: String, default: 'all' } })
const emit = defineEmits(['update:modelValue', 'choose-folder'])
const set = (key, value) => emit('update:modelValue', { ...props.modelValue, [key]: value })
const languages = computed({ get: () => props.modelValue.subtitle_languages.join(', '), set: value => set('subtitle_languages', [...new Set(value.split(',').map(s => s.trim()).filter(Boolean))]) })
</script>

<template>
  <fieldset class="options" :disabled="disabled">
    <legend class="sr-only">다운로드 옵션</legend>
    <template v-if="section !== 'advanced'">
    <div class="options-grid">
      <label>저장 방식<select :value="modelValue.format_type" @change="set('format_type', $event.target.value)"><option value="video">영상</option><option value="audio">오디오</option></select></label>
      <template v-if="modelValue.format_type === 'video'">
        <label>파일 형식<select :value="modelValue.video_format" @change="set('video_format', $event.target.value)"><option value="mp4">MP4</option><option value="webm">WebM</option></select></label>
        <label>영상 화질<select :value="modelValue.video_quality" @change="set('video_quality', $event.target.value)"><option value="best">최고 화질</option><option value="1080">1080p 이하</option><option value="720">720p 이하</option></select></label>
      </template>
      <template v-else>
        <label>파일 형식<select :value="modelValue.audio_format" @change="set('audio_format', $event.target.value)"><option value="mp3">MP3</option><option value="m4a">M4A · 원본 품질</option></select></label>
        <label v-if="modelValue.audio_format === 'mp3'">음질<select :value="modelValue.audio_bitrate" @change="set('audio_bitrate', Number($event.target.value))"><option :value="320">320kbps</option><option :value="192">192kbps</option><option :value="128">128kbps</option></select></label>
        <p v-else class="field-hint">원본 AAC 오디오를 변환 없이 보관합니다.</p>
      </template>
    </div>
    <label class="folder-label">저장 위치<div class="folder-control"><input :value="modelValue.download_dir" @change="set('download_dir', $event.target.value)" placeholder="저장 폴더의 전체 경로" /><button type="button" class="icon-button" aria-label="저장 폴더 선택" @click="emit('choose-folder')"><FolderOpen :size="18" /></button></div></label>
    </template>
    <component :is="section === 'advanced' ? 'div' : 'details'" v-if="section !== 'basic'" :open="advancedOpen" class="advanced-options" :class="{ 'standalone-options': section === 'advanced' }">
      <summary v-if="section !== 'advanced'"><SlidersHorizontal :size="15" /> 고급 옵션 <span>자막 · 추가 파일 · 중복 처리</span></summary>
      <div class="advanced-body">
        <div class="options-grid two">
          <label>같은 이름의 파일<select :value="modelValue.collision" @change="set('collision', $event.target.value)"><option value="rename">이름 변경하여 저장</option><option value="skip">기존 파일 건너뛰기</option><option value="overwrite">기존 파일 덮어쓰기</option></select></label>
          <label>자막<select :value="modelValue.subtitle_mode" @change="set('subtitle_mode', $event.target.value)"><option value="off">저장 안 함</option><option value="file">별도 파일로 저장</option><option value="embed" :disabled="modelValue.format_type === 'audio'">영상에 삽입 + 별도 저장</option></select></label>
        </div>
        <p v-if="modelValue.collision === 'overwrite'" class="field-hint">같은 이름의 기존 파일은 새 다운로드가 완료되면 교체됩니다.</p>
        <template v-if="modelValue.subtitle_mode !== 'off'">
          <label>자막 언어 <input v-model="languages" placeholder="ko, en, ja" /><small>언어 코드를 쉼표로 구분하세요. 없는 자막은 건너뜁니다.</small></label>
          <label class="check"><input type="checkbox" :checked="modelValue.auto_subtitles" @change="set('auto_subtitles', $event.target.checked)" /> 자동 생성 자막 포함</label>
          <p v-if="modelValue.format_type === 'audio'" class="field-hint">오디오는 자막을 별도 파일로 저장합니다.</p>
        </template>
        <div class="check-grid">
          <label class="check"><input type="checkbox" :checked="modelValue.save_thumbnail" @change="set('save_thumbnail', $event.target.checked)" /> 썸네일 저장</label>
          <label class="check"><input type="checkbox" :checked="modelValue.save_description" @change="set('save_description', $event.target.checked)" /> 영상 설명 저장</label>
          <label class="check"><input type="checkbox" :checked="modelValue.save_metadata" @change="set('save_metadata', $event.target.checked)" /> 영상 정보 JSON 저장</label>
        </div>
      </div>
    </component>
  </fieldset>
</template>
