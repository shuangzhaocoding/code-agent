<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useAppStore } from '@/stores/app'
import { currentTheme, toggleTheme, type Theme } from '@/theme'
import { useWorkspaceBrowse } from '@/composables/useWorkspaceBrowse'
import { useSshWorkspaceBrowse } from '@/composables/useSshWorkspaceBrowse'
import { useI18n } from 'vue-i18n'
import AppIcon from '@/components/AppIcon.vue'
import LanguageSelect from '@/components/LanguageSelect.vue'
import BrandMark from '@/components/BrandMark.vue'
import WorkspaceMkdirRow from '@/components/WorkspaceMkdirRow.vue'

import { formatWorkspaceOpenedAt } from '@/utils/relativeTime'

const { t } = useI18n()
const store = useAppStore()
const theme = ref<Theme>(currentTheme())
const mode = ref<'local' | 'ssh'>('local')
const local = reactive(useWorkspaceBrowse('~'))
const ssh = reactive(useSshWorkspaceBrowse())

const isDesktop = Boolean((window as Window & { codeAgentDesktop?: { isDesktop?: boolean; pickDirectory?: () => Promise<string | null> } }).codeAgentDesktop?.isDesktop)

onMounted(async () => {
  await store.loadWorkspaces()
  await local.browse('~')
})

async function openLocal() {
  if (!local.path) return
  local.error = ''
  try {
    await store.addWorkspace(local.path)
  } catch (err) {
    local.error = local.errMessage(err)
  }
}

async function connectSsh() {
  ssh.error = ''
  try {
    await ssh.browse(ssh.path || '~')
  } catch {
    /* error set in composable */
  }
}

async function openSsh() {
  if (!ssh.path) return
  ssh.error = ''
  try {
    await store.addSshWorkspace({
      root_path: ssh.path,
      ssh_display_name: ssh.auth.display_name.trim() || undefined,
      ssh_host: ssh.auth.host.trim(),
      ssh_port: Number(ssh.auth.port) || 22,
      ssh_user: ssh.auth.username.trim(),
      ssh_password: ssh.auth.password || undefined,
      ssh_private_key: ssh.auth.private_key || undefined,
      ssh_passphrase: ssh.auth.passphrase || undefined,
    })
  } catch (err) {
    ssh.error = ssh.errMessage(err)
  }
}

async function pickNativeFolder() {
  const desktop = (window as Window & { codeAgentDesktop?: { pickDirectory?: () => Promise<string | null> } }).codeAgentDesktop
  if (!desktop?.pickDirectory) return
  local.error = ''
  try {
    const chosen = await desktop.pickDirectory()
    if (!chosen) return
    local.path = chosen
    await local.browse(chosen)
  } catch (err) {
    local.error = local.errMessage(err)
  }
}

function onToggleTheme() {
  theme.value = toggleTheme()
}

const recents = computed(() => store.recentWorkspaces)
const activeError = computed(() => (mode.value === 'local' ? local.error : ssh.error))
</script>
<template>
  <div class="launch-page">
    <header class="launch-header">
      <div class="launch-brand">
        <BrandMark :size="24" />
        <span>Code Agent</span>
      </div>
      <div class="launch-actions">
        <LanguageSelect compact />
        <button type="button" class="launch-theme" :title="t('theme.toggle')" @click="onToggleTheme">
          <AppIcon :name="theme === 'dark' ? 'sun' : 'moon'" :size="16" />
        </button>
      </div>
    </header>

    <main class="launch-body">
      <div class="mode-tabs">
        <button type="button" class="mode-tab" :class="{ active: mode === 'local' }" @click="mode = 'local'">
          {{ t('workspace.localTab') }}
        </button>
        <button type="button" class="mode-tab" :class="{ active: mode === 'ssh' }" @click="mode = 'ssh'">
          {{ t('workspace.sshTab') }}
        </button>
      </div>

      <template v-if="mode === 'local'">
        <div class="launch-path">
          <AppIcon name="folder" :size="15" />
          <input v-model="local.path" :placeholder="t('workspace.pathPlaceholder')" @keydown.enter="openLocal" />
          <button v-if="isDesktop" type="button" class="btn" @click="pickNativeFolder">{{ t('workspace.pickFolder') }}</button>
          <button type="button" class="btn btn-primary" @click="openLocal">{{ t('common.open') }}</button>
        </div>
      </template>
      <template v-else>
        <div class="ssh-form-wrap">
          <input
            v-model="ssh.auth.display_name"
            class="ssh-display-name"
            type="text"
            maxlength="120"
            :placeholder="t('workspace.sshDisplayName')"
          />
          <div class="ssh-form">
            <input v-model="ssh.auth.host" :placeholder="t('workspace.sshHost')" />
            <input v-model.number="ssh.auth.port" type="number" min="1" max="65535" :placeholder="t('workspace.sshPort')" />
            <input v-model="ssh.auth.username" :placeholder="t('workspace.sshUser')" />
            <input v-model="ssh.auth.password" type="password" :placeholder="t('workspace.sshPassword')" />
          </div>
        </div>
        <textarea
          v-model="ssh.auth.private_key"
          class="ssh-key"
          rows="3"
          :placeholder="t('workspace.sshKey')"
        />
        <input
          v-model="ssh.auth.passphrase"
          class="ssh-passphrase"
          type="password"
          :placeholder="t('workspace.sshPassphrase')"
        />
        <div class="launch-path">
          <AppIcon name="folder" :size="15" />
          <input v-model="ssh.path" :placeholder="t('workspace.sshPathPlaceholder')" @keydown.enter="openSsh" />
          <button type="button" class="btn" :disabled="ssh.connecting" @click="connectSsh">
            {{ t('workspace.sshConnect') }}
          </button>
          <button type="button" class="btn btn-primary" :disabled="!ssh.path" @click="openSsh">
            {{ t('common.open') }}
          </button>
        </div>
      </template>
      <p v-if="activeError" class="launch-err">{{ activeError }}</p>

      <div class="launch-split">
        <section class="launch-col">
          <h2>{{ t('workspace.recent') }}</h2>
          <p v-if="!recents.length" class="launch-empty">{{ t('workspace.emptyRecent') }}</p>
          <button
            v-for="ws in recents"
            :key="ws.id"
            type="button"
            class="recent-item"
            :title="ws.display_path || ws.root_path"
            @click="store.selectWorkspace(ws.id)"
          >
            <AppIcon name="folder" :size="15" />
            <span class="recent-copy">
              <span class="recent-head">
                <strong>{{ ws.name }}</strong>
                <time v-if="ws.last_opened_at" class="recent-time">{{ formatWorkspaceOpenedAt(ws.last_opened_at) }}</time>
              </span>
              <span class="recent-path">{{ ws.display_path || ws.root_path }}</span>
            </span>
          </button>
        </section>

        <section class="launch-col">
          <div class="browse-head">
            <h2>{{ mode === 'local' ? t('workspace.browse') : t('workspace.sshBrowse') }}</h2>
            <div class="browse-actions">
              <button
                v-if="mode === 'local'"
                type="button"
                class="browse-up"
                :disabled="local.atRoots"
                @click="local.startCreate"
              >
                {{ t('workspace.newFolder') }}
              </button>
              <button
                type="button"
                class="browse-up"
                :disabled="mode === 'local' ? !local.canGoParent : !ssh.canGoParent"
                @click="mode === 'local' ? local.goParent() : ssh.goParent()"
              >
                {{ t('common.parent') }}
              </button>
            </div>
          </div>
          <p class="browse-path" :title="mode === 'local' ? local.displayPath : ssh.displayPath">
            {{ mode === 'local' ? local.displayPath : ssh.displayPath }}
          </p>
          <ul class="dirs">
            <li v-if="mode === 'local' && local.creating">
              <WorkspaceMkdirRow
                :key="local.createKey"
                :model-value="local.createValue"
                @update:model-value="local.createValue = $event"
                @commit="local.commitCreate"
                @cancel="local.cancelCreate"
              />
            </li>
            <li v-for="item in mode === 'local' ? local.dirs : ssh.dirs" :key="item.path">
              <button
                type="button"
                class="dir-item"
                @click="mode === 'local' ? local.browse(item.path) : ssh.browse(item.path)"
              >
                <AppIcon name="folder" :size="15" />
                {{ item.name }}
              </button>
            </li>
          </ul>
        </section>
      </div>
    </main>
  </div>
</template>
<style scoped>
.launch-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--page-bg);
}
.launch-header {
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 14px 0 12px;
  background: var(--sidebar-bg);
  border-bottom: var(--border-width) solid var(--border);
  flex-shrink: 0;
}
.launch-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 600;
  font-size: 14px;
  color: var(--text-h);
  letter-spacing: -0.02em;
}
.launch-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.launch-theme {
  width: 32px;
  height: 32px;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  display: grid;
  place-items: center;
}
.launch-theme:hover {
  background: var(--code-bg);
  color: var(--text-h);
}
.launch-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  max-width: 960px;
  width: 100%;
  margin: 0 auto;
}
.mode-tabs {
  display: flex;
  gap: 4px;
}
.mode-tab {
  border: var(--border-width) solid var(--border);
  background: transparent;
  color: var(--text-secondary);
  border-radius: var(--radius-sm);
  padding: 6px 12px;
  font-size: 12px;
  cursor: pointer;
}
.mode-tab.active {
  background: var(--code-bg);
  color: var(--text-h);
  border-color: color-mix(in srgb, var(--primary) 40%, var(--border));
}
.ssh-form-wrap {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.ssh-display-name {
  width: 100%;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--panel-bg);
  color: var(--text-h);
  padding: 8px 10px;
  font-size: 13px;
}
.ssh-display-name::placeholder,
.ssh-form input::placeholder,
.ssh-key::placeholder {
  font-size: 11.5px;
  color: color-mix(in srgb, var(--text-muted) 72%, transparent);
  opacity: 1;
}
.ssh-form {
  display: grid;
  grid-template-columns: 1.6fr 0.6fr 1fr 1fr;
  gap: 8px;
}
.ssh-form input,
.ssh-key,
.ssh-passphrase {
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--panel-bg);
  color: var(--text-h);
  padding: 8px 10px;
  font-size: 13px;
  font-family: var(--mono);
}
.ssh-key {
  width: 100%;
  resize: vertical;
  min-height: 64px;
}
.ssh-passphrase {
  width: 100%;
  margin-top: 8px;
}
.launch-path {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 36px;
  padding: 0 6px 0 10px;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--panel-bg);
  color: var(--text-muted);
}
.launch-path input {
  flex: 1;
  min-width: 0;
  border: 0;
  background: transparent;
  color: var(--text-h);
  outline: none;
  font-size: 13px;
  font-family: var(--mono);
}
.launch-path .btn {
  height: 28px;
  padding: 0 12px;
  font-size: 12px;
}
.launch-err {
  margin: 0;
  color: var(--error-text);
  font-size: 12px;
}
.browse-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}
.launch-split {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr);
  gap: 12px;
}
.launch-col {
  min-height: 0;
  display: flex;
  flex-direction: column;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-md);
  background: var(--panel-bg);
  overflow: auto;
}
.launch-col h2,
.browse-head h2 {
  margin: 0;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-muted);
}
.launch-col > h2 {
  padding: 10px 12px;
  border-bottom: var(--border-width) solid var(--border);
}
.launch-empty {
  margin: 0;
  padding: 24px 12px;
  font-size: 13px;
  color: var(--text-muted);
}
.recent-item,
.dir-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 12px;
  border: 0;
  background: transparent;
  color: var(--text);
  font-size: 13px;
  text-align: left;
  cursor: pointer;
}
.recent-item:hover,
.dir-item:hover {
  background: var(--code-bg);
  color: var(--text-h);
}
.recent-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.recent-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  min-width: 0;
}
.recent-head strong {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-h);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.recent-time {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--text-secondary);
  font-variant-numeric: tabular-nums;
}
.recent-path {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.browse-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: var(--border-width) solid var(--border);
}
.browse-up {
  border: 0;
  background: transparent;
  color: var(--primary);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
}
.browse-up:disabled {
  opacity: 0.4;
  cursor: default;
}
.browse-up:hover {
  background: var(--code-bg);
}
.browse-path {
  margin: 0;
  padding: 8px 12px;
  font-family: var(--mono);
  font-size: 11px;
  color: var(--text-muted);
  border-bottom: var(--border-width) solid var(--border);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dirs {
  list-style: none;
  margin: 0;
  padding: 4px;
  overflow: auto;
  flex: 1;
}
@media (max-width: 720px) {
  .launch-split {
    grid-template-columns: 1fr;
  }
}
</style>
