import { ref } from 'vue'
import type { Attachment } from '@opentiny/tiny-robot'
import { uploadFile } from '@/services/uploadService'
import { detectAttachmentFileType, detectAttachmentFileTypeFromMeta } from '@/utils/fileTypes'
import type { PendingFilePayload } from '@/types/contextUsage'

const UPLOADING_DISPLAY_NAME = '\u200b'

function createAttachmentId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

type ChatAttachment = Attachment & { mimeType?: string }

export function useChatAttachments() {
  const attachments = ref<ChatAttachment[]>([])

  function patchAttachment(id: string, patch: Partial<ChatAttachment>) {
    attachments.value = attachments.value.map((item) =>
      item.id === id ? { ...item, ...patch } : item,
    )
  }

  async function uploadAttachment(attachment: Attachment) {
    if (!('rawFile' in attachment) || !attachment.rawFile || !attachment.id) return
    const attachmentId = attachment.id
    patchAttachment(attachmentId, {
      status: 'uploading',
      message: '上传中…',
      name: UPLOADING_DISPLAY_NAME,
    })

    try {
      const uploaded = await uploadFile(attachment.rawFile)
      patchAttachment(attachmentId, {
        name: uploaded.name,
        status: 'success',
        url: uploaded.url,
        size: uploaded.size,
        message: '',
        mimeType: uploaded.type,
      })
    } catch (error) {
      patchAttachment(attachmentId, {
        status: 'error',
        name: attachment.rawFile.name,
        message: error instanceof Error ? error.message : '上传失败',
      })
    }
  }

  function addFiles(files: File[]) {
    const newItems: Attachment[] = files.map((file) => ({
      id: createAttachmentId(),
      name: UPLOADING_DISPLAY_NAME,
      rawFile: file,
      size: file.size,
      fileType: detectAttachmentFileType(file),
      status: 'uploading',
      message: '上传中…',
    }))
    attachments.value = [...attachments.value, ...newItems]
    newItems.forEach((item) => {
      void uploadAttachment(item)
    })
  }

  function removeAttachment(file: Attachment) {
    attachments.value = attachments.value.filter((item) => item.id !== file.id)
  }

  function retryUpload(file: Attachment) {
    void uploadAttachment(file)
  }

  function clearAttachments() {
    attachments.value = []
  }

  function restoreAttachments(files: PendingFilePayload[]) {
    attachments.value = files.map((file) => ({
      id: createAttachmentId(),
      name: file.name || 'file',
      url: file.url,
      size: file.size,
      mimeType: file.type,
      fileType: detectAttachmentFileTypeFromMeta(file.name || '', file.type || ''),
      status: 'success' as const,
      message: '',
    }))
  }

  function getReadyAttachments(): ChatAttachment[] {
    return attachments.value.filter((item) => item.status === 'success')
  }

  function hasUploadingAttachments(): boolean {
    return attachments.value.some((item) => item.status === 'uploading')
  }

  function getPendingFiles(): PendingFilePayload[] {
    return getReadyAttachments().map((item) => ({
      name: item.name || 'file',
      url: String(item.url || ''),
      size: Number(item.size || 0),
      type: String(item.mimeType || 'application/octet-stream'),
    }))
  }

  return {
    attachments,
    addFiles,
    removeAttachment,
    retryUpload,
    clearAttachments,
    restoreAttachments,
    getReadyAttachments,
    hasUploadingAttachments,
    getPendingFiles,
  }
}
