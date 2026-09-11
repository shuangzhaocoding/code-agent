const { app, BrowserWindow, Menu, dialog, shell, ipcMain, nativeTheme } = require('electron')
const { spawn } = require('child_process')
const http = require('http')
const path = require('path')
const fs = require('fs')

const PORT = Number(process.env.CODE_AGENT_PORT || 4060)
const HOST = process.env.CODE_AGENT_HOST || '127.0.0.1'
const HEALTH_URL = `http://${HOST}:${PORT}/api/health`
const TITLEBAR_HEIGHT = 38

const CHROME = {
  dark: { background: '#121218', overlay: '#121218', symbol: '#c4c4cc' },
  light: { background: '#ffffff', overlay: '#ffffff', symbol: '#3f3f46' },
}

/** @type {'light' | 'dark'} */
let chromeTheme = 'dark'

function themeStorePath() {
  return path.join(app.getPath('userData'), 'chrome-theme')
}

function loadStoredChromeTheme() {
  try {
    const raw = fs.readFileSync(themeStorePath(), 'utf8').trim()
    if (raw === 'light' || raw === 'dark') return raw
  } catch {
    /* first run */
  }
  try {
    return nativeTheme.shouldUseDarkColors ? 'dark' : 'light'
  } catch {
    return 'dark'
  }
}

function persistChromeTheme(theme) {
  try {
    fs.writeFileSync(themeStorePath(), theme, 'utf8')
  } catch {
    /* ignore quota / perms */
  }
}

const SPLIT_SERVICES = [
  { name: 'api', args: ['-m', 'code_agent', 'api'] },
  { name: 'worker', args: ['-m', 'code_agent', 'worker'] },
  { name: 'terminal', args: ['-m', 'code_agent', 'terminal'] },
  { name: 'preview', args: ['-m', 'code_agent', 'preview'] },
]

/** @type {Set<import('electron').BrowserWindow>} */
const windows = new Set()
/** @type {{ name: string, proc: import('child_process').ChildProcess }[]} */
let backends = []
let stopping = false
let backendLog = ''
let backendReady = false
let booting = false

function repoRoot() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'code-agent')
  }
  return path.resolve(__dirname, '../..')
}

function apiDir() {
  return path.join(repoRoot(), 'apps', 'api')
}

function bundledPythonBases() {
  const bases = []
  if (process.resourcesPath) {
    bases.push(path.join(process.resourcesPath, 'python'))
    // Legacy Windows layout from earlier builds.
    bases.push(path.join(process.resourcesPath, 'python-win'))
  }
  bases.push(
    path.join(__dirname, 'runtime', 'python-win'),
    path.join(__dirname, 'runtime', 'python-linux'),
    path.join(__dirname, 'runtime', 'python-macos'),
  )
  return bases
}

function bundledPython() {
  for (const base of bundledPythonBases()) {
    if (!base) continue
    if (process.platform === 'win32') {
      const exe = path.join(base, 'python.exe')
      if (fs.existsSync(exe)) return exe
      continue
    }
    for (const rel of ['bin/python3', 'bin/python']) {
      const exe = path.join(base, rel)
      if (fs.existsSync(exe)) return exe
    }
  }
  return null
}

function pythonCmd() {
  if (process.env.CODE_AGENT_PYTHON) return process.env.CODE_AGENT_PYTHON
  if (app.isPackaged || process.platform === 'win32') {
    const bundled = bundledPython()
    if (bundled) return bundled
  }
  // Dev on Linux/macOS: prefer a local bundle when present, else system Python.
  const bundled = bundledPython()
  if (bundled) return bundled
  return process.platform === 'win32' ? 'python' : 'python3.11'
}

/**
 * Embeddable CPython uses a *._pth file that isolates sys.path and IGNORES PYTHONPATH.
 * Inject the API package root so `python -m code_agent` can import.
 */
function prepareEmbeddablePath(pythonExe, apiPath) {
  if (!pythonExe || !apiPath) return
  const dir = path.dirname(pythonExe)
  let pthName
  try {
    pthName = fs.readdirSync(dir).find((name) => name.endsWith('._pth'))
  } catch {
    return
  }
  if (!pthName) return
  const apiEntry = apiPath.replace(/\\/g, '/')
  const body = ['python311.zip', '.', 'Lib/site-packages', apiEntry, 'import site', ''].join('\n')
  fs.writeFileSync(path.join(dir, pthName), body, 'utf8')
}

function appendBackendLog(chunk, name) {
  const text = chunk.toString()
  const tagged = text
    .split(/\r?\n/)
    .filter((line) => line.length)
    .map((line) => `[${name}] ${line}`)
    .join('\n')
  if (!tagged) return
  backendLog = (backendLog + tagged + '\n').slice(-12000)
  console.log(tagged)
}

function backendLogTail(max = 1800) {
  const text = backendLog.trim()
  if (!text) return '(no backend output)'
  return text.length > max ? text.slice(-max) : text
}

function splashPath() {
  return path.join(__dirname, 'splash.html')
}

function primaryWindow() {
  return BrowserWindow.getFocusedWindow() || [...windows].find((w) => !w.isDestroyed()) || null
}

function setSplashStatus(win, text, opts = {}) {
  const target = win && !win.isDestroyed() ? win : primaryWindow()
  if (!target || target.isDestroyed()) return
  target.webContents
    .executeJavaScript(
      `window.setSplashStatus && window.setSplashStatus(${JSON.stringify(text)}, ${JSON.stringify({
        detail: opts.detail || '',
        error: !!opts.error,
      })})`,
      true,
    )
    .catch(() => {})
}

function applyChromeToWindow(win) {
  if (!win || win.isDestroyed()) return
  const colors = CHROME[chromeTheme]
  win.setBackgroundColor(colors.background)
  if (process.platform === 'win32' && typeof win.setTitleBarOverlay === 'function') {
    try {
      win.setTitleBarOverlay({
        color: colors.overlay,
        symbolColor: colors.symbol,
        height: TITLEBAR_HEIGHT,
      })
    } catch {
      // ignore unsupported hosts
    }
  }
  win.webContents
    .executeJavaScript(
      `window.setSplashTheme && window.setSplashTheme(${JSON.stringify(chromeTheme)})`,
      true,
    )
    .catch(() => {})
}

function applyWindowChrome(theme) {
  const next = theme === 'light' ? 'light' : 'dark'
  chromeTheme = next
  nativeTheme.themeSource = next
  persistChromeTheme(next)
  for (const win of windows) {
    applyChromeToWindow(win)
  }
}

function windowChromeOptions() {
  const colors = CHROME[chromeTheme]
  if (process.platform === 'darwin') {
    return {
      titleBarStyle: 'hiddenInset',
      trafficLightPosition: { x: 14, y: 12 },
    }
  }
  if (process.platform === 'win32') {
    return {
      titleBarStyle: 'hidden',
      titleBarOverlay: {
        color: colors.overlay,
        symbolColor: colors.symbol,
        height: TITLEBAR_HEIGHT,
      },
    }
  }
  return {}
}

function toggleDevTools(win) {
  const target = win && !win.isDestroyed() ? win : primaryWindow()
  if (!target || target.isDestroyed()) return
  const wc = target.webContents
  if (wc.isDevToolsOpened()) wc.closeDevTools()
  else wc.openDevTools({ mode: 'detach' })
}

function bindDevToolsShortcuts(win) {
  win.webContents.on('before-input-event', (event, input) => {
    if (input.type !== 'keyDown') return
    const key = String(input.key || '').toLowerCase()
    const isF12 = key === 'f12'
    const isChord =
      process.platform === 'darwin'
        ? key === 'i' && input.meta && input.alt
        : key === 'i' && input.control && input.shift
    // Ctrl/Cmd+Shift+N → new window (IDE habit; avoid stealing from renderer when possible)
    const isNewWindow =
      key === 'n' && input.shift && (process.platform === 'darwin' ? input.meta : input.control)
    if (isNewWindow) {
      event.preventDefault()
      void openNewWindow()
      return
    }
    if (!isF12 && !isChord) return
    event.preventDefault()
    toggleDevTools(win)
  })
}

/**
 * @param {{ showSplash?: boolean }} [opts]
 * @returns {import('electron').BrowserWindow}
 */
function createWindow(opts = {}) {
  const showSplash = opts.showSplash !== false
  const colors = CHROME[chromeTheme]
  const win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1100,
    minHeight: 700,
    title: 'Code Agent',
    backgroundColor: colors.background,
    autoHideMenuBar: true,
    show: false,
    ...windowChromeOptions(),
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  })

  windows.add(win)
  bindDevToolsShortcuts(win)

  win.once('ready-to-show', () => {
    if (!win.isDestroyed()) win.show()
  })

  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })

  win.on('closed', () => {
    windows.delete(win)
  })

  if (showSplash) {
    win.loadFile(splashPath(), { query: { theme: chromeTheme } })
  }
  return win
}

function loadAppInto(win) {
  if (!win || win.isDestroyed()) return
  setSplashStatus(win, '服务已就绪，正在打开界面…')
  win.loadURL(`http://${HOST}:${PORT}/`)
}

function waitSplashReady(win) {
  return new Promise((resolve) => {
    if (!win || win.isDestroyed()) {
      resolve()
      return
    }
    if (!win.webContents.isLoading()) {
      resolve()
      return
    }
    win.webContents.once('did-finish-load', () => resolve())
  })
}

function probeHealth() {
  return new Promise((resolve) => {
    const req = http.get(HEALTH_URL, (res) => {
      res.resume()
      resolve(res.statusCode && res.statusCode < 500)
    })
    req.on('error', () => resolve(false))
    req.setTimeout(1500, () => {
      req.destroy()
      resolve(false)
    })
  })
}

async function waitForBackend(timeoutMs = 120000) {
  const started = Date.now()
  while (Date.now() - started < timeoutMs) {
    const api = backends.find((b) => b.name === 'api')
    // Only API is required for health; other split services may restart independently.
    if (api && api.proc.exitCode != null) return false
    if (await probeHealth()) return true
    await new Promise((r) => setTimeout(r, 400))
  }
  return false
}

function killProcessTree(proc) {
  if (!proc || proc.killed || proc.pid == null) return
  try {
    if (process.platform === 'win32') {
      spawn('taskkill', ['/pid', String(proc.pid), '/f', '/t'], {
        stdio: 'ignore',
        windowsHide: true,
      })
    } else {
      proc.kill('SIGTERM')
    }
  } catch {
    // ignore
  }
}

function startBackend() {
  const cwd = apiDir()
  if (!fs.existsSync(cwd)) {
    throw new Error(`API directory missing: ${cwd}`)
  }
  const py = pythonCmd()
  if (!py || (path.isAbsolute(py) && !fs.existsSync(py))) {
    throw new Error(`Python runtime not found: ${py}`)
  }

  prepareEmbeddablePath(py, cwd)

  backendLog = ''
  backends = []
  const env = {
    ...process.env,
    CODE_AGENT_HOST: HOST,
    CODE_AGENT_PORT: String(PORT),
    // Desktop split: api gateway + worker + terminal + preview.
    CODE_AGENT_RUNTIME_PROFILE: 'split',
    CODE_AGENT_AGENT_WORKER: 'external',
    CODE_AGENT_TERMINAL_MODE: 'standalone',
    CODE_AGENT_PREVIEW_MODE: 'standalone',
    PYTHONUNBUFFERED: '1',
    // Still set for non-embeddable interpreters; embeddable relies on ._pth above.
    PYTHONPATH: [cwd, process.env.PYTHONPATH || ''].filter(Boolean).join(path.delimiter),
  }

  for (const svc of SPLIT_SERVICES) {
    const proc = spawn(py, svc.args, {
      cwd,
      env,
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
      shell: false,
    })
    backends.push({ name: svc.name, proc })

    proc.stdout.on('data', (chunk) => appendBackendLog(chunk, svc.name))
    proc.stderr.on('data', (chunk) => appendBackendLog(chunk, svc.name))
    proc.on('error', (err) => {
      appendBackendLog(String(err), svc.name)
      console.error(`[${svc.name}] spawn error`, err)
    })
    proc.on('exit', (code, signal) => {
      if (!stopping && windows.size > 0) {
        dialog.showErrorBox(
          'Code Agent backend stopped',
          `${svc.name} exited (code=${code}, signal=${signal || 'none'}).\nPython: ${py}\n\n${backendLogTail()}`,
        )
      }
    })
  }
}

function stopBackend() {
  stopping = true
  backendReady = false
  for (const { proc } of backends) {
    killProcessTree(proc)
  }
  backends = []
}

async function openNewWindow() {
  if (backendReady || (await probeHealth())) {
    backendReady = true
    const win = createWindow({ showSplash: false })
    win.loadURL(`http://${HOST}:${PORT}/`)
    return win
  }
  // Backend still starting: open splash window; boot() will load the app when ready.
  const win = createWindow({ showSplash: true })
  if (!booting) void boot(win)
  return win
}

function focusExistingWindow() {
  const win = primaryWindow()
  if (!win) return false
  if (win.isMinimized()) win.restore()
  win.focus()
  return true
}

/**
 * @param {import('electron').BrowserWindow | null} [seedWin]
 */
async function boot(seedWin = null) {
  if (booting) return
  booting = true
  const win = seedWin && !seedWin.isDestroyed() ? seedWin : createWindow({ showSplash: true })
  const splashReady = waitSplashReady(win)
  try {
    const alreadyUp = await probeHealth()
    if (alreadyUp) {
      backendReady = true
      await splashReady
      for (const w of [...windows]) {
        if (!w.isDestroyed()) loadAppInto(w)
      }
      return
    }

    try {
      startBackend()
    } catch (err) {
      await splashReady
      setSplashStatus(win, '后端启动失败', { error: true, detail: String(err) })
      dialog.showErrorBox('Failed to start backend', String(err))
      app.quit()
      return
    }

    await splashReady
    setSplashStatus(win, '正在启动服务…')
    const ok = await waitForBackend()
    if (!ok) {
      const detail = `Could not reach ${HEALTH_URL}.\nPython: ${pythonCmd()}\n\n${backendLogTail()}`
      setSplashStatus(win, '启动超时', { error: true, detail })
      dialog.showErrorBox('Backend startup timeout', detail)
      stopBackend()
      app.quit()
      return
    }
    backendReady = true
    for (const w of [...windows]) {
      if (!w.isDestroyed()) loadAppInto(w)
    }
  } finally {
    booting = false
  }
}

const gotLock = app.requestSingleInstanceLock()
if (!gotLock) {
  app.quit()
} else {
  app.on('second-instance', () => {
    // Cursor-like: another launch opens a new window (shared backend).
    if (backendReady) {
      void openNewWindow()
      return
    }
    if (!focusExistingWindow()) void openNewWindow()
  })
  ipcMain.handle('desktop:pick-directory', async () => {
    const win = primaryWindow()
    const result = await dialog.showOpenDialog(win || undefined, {
      properties: ['openDirectory', 'createDirectory'],
    })
    if (result.canceled || !result.filePaths.length) return null
    return result.filePaths[0]
  })
  ipcMain.handle('desktop:set-theme', (_event, theme) => {
    applyWindowChrome(theme === 'light' ? 'light' : 'dark')
    return chromeTheme
  })
  ipcMain.handle('desktop:get-theme', () => chromeTheme)
  ipcMain.handle('desktop:new-window', async () => {
    const win = await openNewWindow()
    return Boolean(win && !win.isDestroyed())
  })
  app.whenReady().then(() => {
    // Hide File / Edit / View etc. native menu bar (packaged desktop UX).
    Menu.setApplicationMenu(null)
    chromeTheme = loadStoredChromeTheme()
    nativeTheme.themeSource = chromeTheme
    return boot()
  })
  app.on('activate', () => {
    // macOS dock click with no windows open.
    if (windows.size === 0) void openNewWindow()
  })
}

app.on('before-quit', () => {
  stopBackend()
})

app.on('window-all-closed', () => {
  // Keep process on macOS until explicit quit (Dock activate can reopen).
  if (process.platform === 'darwin') return
  stopBackend()
  app.quit()
})
