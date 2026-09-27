export function duration(seconds) {
  if (seconds === null || seconds === undefined) return '길이 미확인'
  const value = Math.max(0, Math.floor(seconds))
  const h = Math.floor(value / 3600), m = Math.floor(value % 3600 / 60), s = value % 60
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}` : `${m}:${String(s).padStart(2, '0')}`
}
export function bytes(value) {
  if (value === null || value === undefined) return '계산 중'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let amount = value, index = 0
  while (amount >= 1024 && index < 4) { amount /= 1024; index++ }
  return `${amount.toFixed(index ? 1 : 0)} ${units[index]}`
}
export const statusLabels = {
  queued: '대기 중', running: '진행 중', cancelling: '취소 요청 중', interrupted: '재개 대기',
  completed: '완료', skipped: '건너뜀', partial: '일부 실패', failed: '실패', cancelled: '취소됨', pending: '대기 중',
  preparing: '준비 중', downloading: '다운로드 중', processing: '병합·변환 중', extras: '자막·보관 정보 처리 중', saving: '파일 저장 중',
}
export const terminal = ['completed', 'partial', 'failed', 'cancelled']
export function counts(job) {
  const items = job.items || []
  return {
    completed: items.filter(i => i.status === 'completed').length,
    skipped: items.filter(i => i.status === 'skipped').length,
    failed: items.filter(i => i.status === 'failed').length,
    remaining: items.filter(i => !['completed', 'skipped', 'failed'].includes(i.status)).length,
  }
}
