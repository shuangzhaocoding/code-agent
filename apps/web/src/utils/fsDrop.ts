/** Relative path stamped onto File objects collected from a directory drop. */
export const CA_RELATIVE_PATH = '__caRelativePath'

export type DropFile = File & { webkitRelativePath?: string; [CA_RELATIVE_PATH]?: string }

export function fileRelativePath(file: DropFile): string {
  const raw =
    (typeof file[CA_RELATIVE_PATH] === 'string' && file[CA_RELATIVE_PATH]) ||
    (typeof file.webkitRelativePath === 'string' && file.webkitRelativePath) ||
    file.name ||
    ''
  return raw
    .replace(/\\/g, '/')
    .replace(/^\/+/, '')
    .split('/')
    .filter((p) => p && p !== '.' && p !== '..')
    .join('/')
}

function readAllDirectoryEntries(reader: FileSystemDirectoryReader): Promise<FileSystemEntry[]> {
  return new Promise((resolve, reject) => {
    const all: FileSystemEntry[] = []
    const readBatch = () => {
      reader.readEntries(
        (batch) => {
          if (!batch.length) {
            resolve(all)
            return
          }
          all.push(...batch)
          readBatch()
        },
        reject,
      )
    }
    readBatch()
  })
}

function entryToFile(entry: FileSystemFileEntry): Promise<File> {
  return new Promise((resolve, reject) => entry.file(resolve, reject))
}

async function walkEntry(entry: FileSystemEntry, prefix: string, out: DropFile[]) {
  if (entry.isFile) {
    const file = (await entryToFile(entry as FileSystemFileEntry)) as DropFile
    const rel = `${prefix}${file.name}`
    Object.defineProperty(file, CA_RELATIVE_PATH, { value: rel, configurable: true })
    out.push(file)
    return
  }
  if (!entry.isDirectory) return
  const dir = entry as FileSystemDirectoryEntry
  const children = await readAllDirectoryEntries(dir.createReader())
  const nextPrefix = `${prefix}${dir.name}/`
  for (const child of children) {
    await walkEntry(child, nextPrefix, out)
  }
}

/** Collect OS drag-drop files, preserving folder structure when possible. */
export async function collectDataTransferFiles(dt: DataTransfer | null | undefined): Promise<DropFile[]> {
  if (!dt) return []
  const items = dt.items
  if (items?.length) {
    const entries: FileSystemEntry[] = []
    for (let i = 0; i < items.length; i++) {
      const entry = items[i].webkitGetAsEntry?.()
      if (entry) entries.push(entry)
    }
    if (entries.length) {
      const out: DropFile[] = []
      for (const entry of entries) {
        await walkEntry(entry, '', out)
      }
      if (out.length) return out
    }
  }
  return Array.from(dt.files || []) as DropFile[]
}
