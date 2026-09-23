const { contextBridge, ipcRenderer } = require('electron')

const customTitleBar = true
const needsWindowControls = process.platform === 'linux'

contextBridge.exposeInMainWorld('codeAgentDesktop', {
  isDesktop: true,
  platform: process.platform,
  customTitleBar,
  needsWindowControls,
  titleBarHeight: 38,
  pickDirectory: () => ipcRenderer.invoke('desktop:pick-directory'),
  setTheme: (theme) => ipcRenderer.invoke('desktop:set-theme', theme),
  getTheme: () => ipcRenderer.invoke('desktop:get-theme'),
  newWindow: () => ipcRenderer.invoke('desktop:new-window'),
  setTitle: (title) => ipcRenderer.invoke('desktop:set-title', title),
  openExternal: (url) => ipcRenderer.invoke('desktop:open-external', url),
  openPath: (targetPath) => ipcRenderer.invoke('desktop:open-path', targetPath),
  windowMinimize: () => ipcRenderer.invoke('desktop:window-minimize'),
  windowMaximizeToggle: () => ipcRenderer.invoke('desktop:window-maximize-toggle'),
  windowClose: () => ipcRenderer.invoke('desktop:window-close'),
  isMaximized: () => ipcRenderer.invoke('desktop:window-is-maximized'),
  notify: (payload) => ipcRenderer.invoke('desktop:notify', payload),
})

ipcRenderer.on('desktop:window-state', (_event, payload) => {
  window.dispatchEvent(new CustomEvent('ca-desktop-window-state', { detail: payload || {} }))
})
