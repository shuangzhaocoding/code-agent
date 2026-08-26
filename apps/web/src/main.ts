import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import { i18n } from '@/i18n'
import { initTheme } from './theme'
import { installAppTooltip } from '@/utils/appTooltip'
import 'dockview-vue/dist/styles/dockview.css'
import '@opentiny/tiny-robot/dist/style.css'
import './style.css'
import './styles/markdown.css'

initTheme()

const app = createApp(App)
app.use(createPinia())
app.use(i18n)
app.mount('#app')
installAppTooltip()
