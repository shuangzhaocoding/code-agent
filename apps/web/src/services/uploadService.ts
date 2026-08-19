import type { PendingFilePayload } from '@/types/contextUsage'

export interface UploadedFile {
  name: string
  url: string
  size: number
  type: string
}

export async function uploadFile(file: File): Promise<UploadedFile> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch('/api/uploads', {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    const raw = await response.text()
    throw new Error(raw || '上传失败')
  }

  return response.json() as Promise<UploadedFile>
}

export type { PendingFilePayload }
