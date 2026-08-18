import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import { initTheme } from './theme'
import 'dockview-vue/dist/styles/dockview.css'
import '@opentiny/tiny-robot/dist/style.css'
import './style.css'

initTheme()

const app = createApp(App)
app.use(createPinia())
app.mount('#app')
