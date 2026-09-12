import { onMounted, onUnmounted, ref } from 'vue'
import {
  GIT_DIFF_TARGET_EVENT,
  getGitDiffTarget,
  isGitDiffTarget,
  setGitDiffTarget,
  type GitDiffTarget,
} from '@/utils/gitPrefs'

export function useGitDiffTarget() {
  const diffTarget = ref<GitDiffTarget>(getGitDiffTarget())

  function onChanged(e: Event) {
    const next = (e as CustomEvent<{ target?: GitDiffTarget }>).detail?.target
    if (isGitDiffTarget(next)) diffTarget.value = next
  }

  function setTarget(value: GitDiffTarget) {
    if (diffTarget.value === value) return
    setGitDiffTarget(value)
    diffTarget.value = value
  }

  onMounted(() => {
    diffTarget.value = getGitDiffTarget()
    window.addEventListener(GIT_DIFF_TARGET_EVENT, onChanged as EventListener)
  })
  onUnmounted(() => {
    window.removeEventListener(GIT_DIFF_TARGET_EVENT, onChanged as EventListener)
  })

  return { diffTarget, setDiffTarget: setTarget }
}
