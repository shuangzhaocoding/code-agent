export function draftCommitFromPaths(paths: string[], subject: string) {
  const names = paths.filter(Boolean)
  const title = subject.trim() || (names.length === 1 ? names[0].split('/').pop() || subject : subject)
  if (!names.length) return title
  const body = names.slice(0, 24).map((p) => `- ${p}`).join('\n')
  const extra = names.length > 24 ? `\n- … +${names.length - 24}` : ''
  return `${title}\n\n${body}${extra}`
}
