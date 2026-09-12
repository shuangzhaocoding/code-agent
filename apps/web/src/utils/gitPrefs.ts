export type GitDiffTarget = 'panel' | 'editor'

export const GIT_DIFF_TARGET_KEY = 'ca.git.diff.target'
export const GIT_DIFF_TARGET_EVENT = 'ca-git-diff-target'

export function isGitDiffTarget(value: unknown): value is GitDiffTarget {
  return value === 'panel' || value === 'editor'
}

export function getGitDiffTarget(defaultValue: GitDiffTarget = 'panel'): GitDiffTarget {
  try {
    const raw = localStorage.getItem(GIT_DIFF_TARGET_KEY)
    return isGitDiffTarget(raw) ? raw : defaultValue
  } catch {
    return defaultValue
  }
}

export function setGitDiffTarget(value: GitDiffTarget) {
  try {
    localStorage.setItem(GIT_DIFF_TARGET_KEY, value)
  } catch {
    /* ignore quota */
  }
  window.dispatchEvent(new CustomEvent(GIT_DIFF_TARGET_EVENT, { detail: { target: value } }))
}
