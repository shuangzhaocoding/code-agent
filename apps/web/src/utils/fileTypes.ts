export const UPLOAD_ACCEPT = 'image/jpeg,image/png,image/gif,image/webp,.jpg,.jpeg,.png,.gif,.webp'
export const UPLOAD_MAX_SIZE_MB = 20
export const UPLOAD_MAX_COUNT = 8

export const attachmentFileMatchers = [
  {
    type: 'image',
    matcher: (file: File | string) => {
      if (typeof file === 'string') {
        const ext = file.split('.').pop()?.toLowerCase() ?? ''
        return ['png', 'jpg', 'jpeg', 'gif', 'webp'].includes(ext)
      }
      return ['image/jpeg', 'image/png', 'image/gif', 'image/webp'].includes(file.type)
        || (file.type.startsWith('image/') && /\.(jpe?g|png|gif|webp)$/i.test(file.name))
    },
  },
]

export function detectAttachmentFileType(file: File): string {
  return attachmentFileMatchers[0].matcher(file) ? 'image' : 'file'
}

export function detectAttachmentFileTypeFromMeta(name: string, type: string): string {
  if (['image/jpeg', 'image/png', 'image/gif', 'image/webp'].includes(type)) return 'image'
  if (type.startsWith('image/')) {
    const ext = name.split('.').pop()?.toLowerCase() ?? ''
    if (['png', 'jpg', 'jpeg', 'gif', 'webp'].includes(ext)) return 'image'
  }
  const ext = name.split('.').pop()?.toLowerCase() ?? ''
  return ['png', 'jpg', 'jpeg', 'gif', 'webp'].includes(ext) ? 'image' : 'file'
}
