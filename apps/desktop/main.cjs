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

const SPLIT_SERVICES = [
  { name: 'api', args: ['-m', 'code_agent', 'api'] },
  { name: 'worker', args: ['-m', 'code_agent', 'worker'] },
  { name: 'terminal', args: ['-m', 'code_agent', 'terminal'] },
  { name: 'preview', args: ['-m', 'code_agent', 'preview'] },
]

let mainWindow = null
/** @type {{ name: string, proc: import('child_process').ChildProcess }[]} */
let backends = []
let stopping = false
let backendLog = ''

function repoRoot() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'code-agent')
  }
  return path.resolve(__dirname, '../..')
}

function apiDir() {
  return path.join(repoRoot(), 'apps', 'api')
}

function bundledPythonWin() {
  const candidates = [
    path.join(process.resourcesPath || '', 'python-win', 'python.exe'),
    path.join(__dirname, 'runtime', 'python-win', 'python.exe'),
  ]
  return candidates.find((p) => p && fs.existsSync(p)) || null
}

function pythonCmd() {
  if (process.env.CODE_AGENT_PYTHON) return process.env.CODE_AGENT_PYTHON
  if (app.isPackaged || process.platform === 'win32') {
    const bundled = bundledPythonWin()
    if (bundled) return bundled
  }
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

function setSplashStatus(text, opts = {}) {
  if (!mainWindow || mainWindow.isDestroyed()) return
  mainWindow.webContents
    .executeJavaScript(
      `window.setSplashStatus && window.setSplashStatus(${JSON.stringify(text)}, ${JSON.stringify({
        detail: opts.detail || '',
        error: !!opts.error,
      })})`,
      true,
    )
    .catch(() => {})
}

function applyWindowChrome(theme) {
  const next = theme === 'light' ? 'light' : 'dark'
  chromeTheme = next
  nativeTheme.themeSource = next
  const colors = CHROME[next]
  if (!mainWindow || mainWindow.isDestroyed()) return
  mainWindow.setBackgroundColor(colors.background)
  if (process.platform === 'win32' && typeof mainWindow.setTitleBarOverlay === 'function') {
    try {
      mainWindow.setTitleBarOverlay({
        color: colors.overlay,
        symbolColor: colors.symbol,
        height: TITLEBAR_HEIGHT,
      })
    } catch {
      // ignore unsupported hosts
    }
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

function createWindow() {
  const colors = CHROME[chromeTheme]
  mainWindow = new BrowserWindow({
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

  mainWindow.once('ready-to-show', () => {
    if (mainWindow && !mainWindow.isDestroyed()) mainWindow.show()
  })

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })

  mainWindow.loadFile(splashPath())
  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

function loadApp() {
  if (!mainWindow || mainWindow.isDestroyed()) return
  setSplashStatus('服务已就绪，正在打开界面…')
  mainWindow.loadURL(`http://${HOST}:${PORT}/`)
}

function waitSplashReady() {
  return new Promise((resolve) => {
    if (!mainWindow || mainWindow.isDestroyed()) {
      resolve()
      return
    }
    if (!mainWindow.webContents.isLoading()) {
      resolve()
      return
    }
    mainWindow.webContents.once('did-finish-load', () => resolve())
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
      if (!stopping && mainWindow) {
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
  for (const { proc } of backends) {
    killProcessTree(proc)
  }
  backends = []
}

async function boot() {
  createWindow()
  const splashReady = waitSplashReady()
  const alreadyUp = await probeHealth()
  if (alreadyUp) {
    await splashReady
    loadApp()
    return
  }

  try {
    startBackend()
  } catch (err) {
    await splashReady
    setSplashStatus('后端启动失败', { error: true, detail: String(err) })
    dialog.showErrorBox('Failed to start backend', String(err))
    app.quit()
    return
  }

  await splashReady
  setSplashStatus('正在启动服务…')
  const ok = await waitForBackend()
  if (!ok) {
    const detail = `Could not reach ${HEALTH_URL}.\nPython: ${pythonCmd()}\n\n${backendLogTail()}`
    setSplashStatus('启动超时', { error: true, detail })
    dialog.showErrorBox('Backend startup timeout', detail)
    stopBackend()
    app.quit()
    return
  }
  loadApp()
}

const gotLock = app.requestSingleInstanceLock()
if (!gotLock) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore()
      mainWindow.focus()
    }
  })
  ipcMain.handle('desktop:pick-directory', async () => {
    const win = BrowserWindow.getFocusedWindow() || mainWindow
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
  app.whenReady().then(() => {
    // Hide File / Edit / View etc. native menu bar (packaged desktop UX).
    // In-app TopMenuBar owns menus; OS title bar chrome follows app theme via desktop:set-theme.
    Menu.setApplicationMenu(null)
    nativeTheme.themeSource = chromeTheme
    return boot()
  })
}

app.on('before-quit', () => {
  stopBackend()
})

app.on('window-all-closed', () => {
  stopBackend()
  app.quit()
})
