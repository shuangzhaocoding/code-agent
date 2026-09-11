const { contextBridge, ipcRenderer } = require('electron')

const customTitleBar = process.platform === 'win32' || process.platform === 'darwin'

contextBridge.exposeInMainWorld('codeAgentDesktop', {
  isDesktop: true,
  platform: process.platform,
  customTitleBar,
  titleBarHeight: 38,
  pickDirectory: () => ipcRenderer.invoke('desktop:pick-directory'),
  setTheme: (theme) => ipcRenderer.invoke('desktop:set-theme', theme),
  getTheme: () => ipcRenderer.invoke('desktop:get-theme'),
  newWindow: () => ipcRenderer.invoke('desktop:new-window'),
})
