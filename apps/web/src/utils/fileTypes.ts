export const UPLOAD_ACCEPT = 'image/*,.png,.jpg,.jpeg,.gif,.webp,.bmp,.svg'
export const UPLOAD_MAX_SIZE_MB = 20
export const UPLOAD_MAX_COUNT = 8

export const attachmentFileMatchers = [
  {
    type: 'image',
    matcher: (file: File | string) => {
      if (typeof file === 'string') {
        const ext = file.split('.').pop()?.toLowerCase() ?? ''
        return ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg'].includes(ext)
      }
      return file.type.startsWith('image/')
    },
  },
]

export function detectAttachmentFileType(file: File): string {
  return file.type.startsWith('image/') ? 'image' : 'file'
}

export function detectAttachmentFileTypeFromMeta(name: string, type: string): string {
  if (type.startsWith('image/')) return 'image'
  const ext = name.split('.').pop()?.toLowerCase() ?? ''
  return ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg'].includes(ext) ? 'image' : 'file'
}
