const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('codeAgentDesktop', {
  isDesktop: true,
  platform: process.platform,
  pickDirectory: () => ipcRenderer.invoke('desktop:pick-directory'),
})
