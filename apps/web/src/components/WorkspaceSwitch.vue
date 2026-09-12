<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useAppStore } from '@/stores/app'
import { useWorkspaceBrowse } from '@/composables/useWorkspaceBrowse'
import { useSshWorkspaceBrowse } from '@/composables/useSshWorkspaceBrowse'
import { useI18n } from 'vue-i18n'
import AppIcon from '@/components/AppIcon.vue'
import WorkspaceMkdirRow from '@/components/WorkspaceMkdirRow.vue'

export type WorkspaceSwitchPrefill = {
  mode: 'local' | 'ssh'
  lockMode?: boolean
  ssh_display_name?: string
  ssh_host?: string
  ssh_port?: number
  ssh_user?: string
  reuse_ssh_from?: string
}

const props = withDefaults(
  defineProps<{
    prefill?: WorkspaceSwitchPrefill | null
  }>(),
  { prefill: null },
)

const emit = defineEmits<{ close: [] }>()
const { t } = useI18n()
const store = useAppStore()
const mode = ref<'local' | 'ssh'>(props.prefill?.mode || 'local')
const lockMode = computed(() => Boolean(props.prefill?.lockMode))
const local = reactive(useWorkspaceBrowse())
const ssh = reactive(useSshWorkspaceBrowse())
const showAuthOverride = ref(false)

function localBrowseStart(): string {
  const ws = store.workspace
  if (!ws?.root_path) return '~'
  // SSH root_path is remote — never use it for local browse.
  if (String(ws.kind || 'local').toLowerCase() === 'ssh') return '~'
  return ws.root_path
}

async function ensureLocalBrowse() {
  const start = localBrowseStart()
  try {
    await local.browse(start)
  } catch (err) {
    if (start !== '~') {
      try {
        await local.browse('~')
        return
      } catch (err2) {
        local.error = local.errMessage(err2)
        return
      }
    }
    local.error = local.errMessage(err)
  }
}

onMounted(async () => {
  if (props.prefill?.mode === 'ssh') {
    mode.value = 'ssh'
    if (props.prefill.ssh_display_name) ssh.auth.display_name = props.prefill.ssh_display_name
    if (props.prefill.ssh_host) ssh.auth.host = props.prefill.ssh_host
    if (props.prefill.ssh_port) ssh.auth.port = props.prefill.ssh_port
    if (props.prefill.ssh_user) ssh.auth.username = props.prefill.ssh_user
    if (props.prefill.reuse_ssh_from) {
      ssh.reuseFromWorkspaceId = props.prefill.reuse_ssh_from
      try {
        await ssh.browse('~')
      } catch {
        showAuthOverride.value = true
      }
    }
  } else {
    mode.value = props.prefill?.mode || 'local'
    await ensureLocalBrowse()
  }
})

watch(mode, (next) => {
  if (next === 'local' && !local.path) void ensureLocalBrowse()
})

async function openLocal() {
  if (!local.path) return
  local.error = ''
  try {
    await store.addWorkspace(local.path)
    emit('close')
  } catch (err) {
    local.error = local.errMessage(err)
  }
}

async function connectSsh() {
  ssh.error = ''
  try {
    await ssh.browse(ssh.path || '~')
  } catch {
    /* set in composable */
  }
}

async function openSsh() {
  if (!ssh.path) return
  ssh.error = ''
  try {
    const payload: Parameters<typeof store.addSshWorkspace>[0] = {
      root_path: ssh.path,
      ssh_display_name: ssh.auth.display_name.trim() || undefined,
      ssh_host: ssh.auth.host.trim(),
      ssh_port: Number(ssh.auth.port) || 22,
      ssh_user: ssh.auth.username.trim(),
    }
    if (ssh.auth.password) payload.ssh_password = ssh.auth.password
    if (ssh.auth.private_key) {
      payload.ssh_private_key = ssh.auth.private_key
      payload.ssh_passphrase = ssh.auth.passphrase || undefined
    }
    if (ssh.reuseFromWorkspaceId && !ssh.auth.password && !ssh.auth.private_key) {
      payload.reuse_ssh_from = ssh.reuseFromWorkspaceId
    }
    await store.addSshWorkspace(payload)
    emit('close')
  } catch (err) {
    ssh.error = ssh.errMessage(err)
  }
}

const activeError = computed(() => (mode.value === 'local' ? local.error : ssh.error))
const sheetTitle = computed(() =>
  lockMode.value
    ? mode.value === 'ssh'
      ? '添加远程工作空间'
      : '添加本地工作空间'
    : t('workspace.title'),
)
const showCredentialFields = computed(
  () => !ssh.reusingCredentials || showAuthOverride.value,
)
</script>

<template>
  <Teleport to="body">
    <div class="mask" @click.self="emit('close')">
      <div class="sheet" role="dialog" aria-modal="true" :aria-label="sheetTitle">
        <header class="sheet-head">
          <div class="sheet-head-copy">
            <span class="sheet-kicker">{{ mode === 'ssh' ? 'SSH 远程' : '本地' }}</span>
            <h1 class="sheet-title">{{ sheetTitle }}</h1>
          </div>
          <button type="button" class="sheet-close" :title="t('common.close')" @click="emit('close')">
            <AppIcon name="close" :size="16" :stroke-width="1.75" />
          </button>
        </header>

        <div v-if="!lockMode" class="mode-tabs">
          <button type="button" class="mode-tab" :class="{ active: mode === 'local' }" @click="mode = 'local'">
            {{ t('workspace.localTab') }}
          </button>
          <button type="button" class="mode-tab" :class="{ active: mode === 'ssh' }" @click="mode = 'ssh'">
            {{ t('workspace.sshTab') }}
          </button>
        </div>

        <p class="sheet-lead">
          {{
            mode === 'local'
              ? t('workspace.lead')
              : ssh.reusingCredentials
                ? '已连接该主机，选择另一个目录作为新的工作空间。'
                : t('workspace.sshLead')
          }}
        </p>

        <template v-if="mode === 'local'">
          <section class="section">
            <h2 class="section-title">路径</h2>
            <div class="path-row">
              <AppIcon class="path-icon" name="folder" :size="15" :stroke-width="1.75" />
              <input
                v-model="local.path"
                class="path-input mono"
                :placeholder="t('workspace.pathPlaceholder')"
                @keydown.enter="openLocal"
              />
              <button type="button" class="btn primary" @click="openLocal">{{ t('common.open') }}</button>
            </div>
          </section>
        </template>
        <template v-else>
          <section class="section">
            <h2 class="section-title">连接</h2>
            <input
              v-model="ssh.auth.display_name"
              class="display-name"
              type="text"
              maxlength="120"
              :placeholder="t('workspace.sshDisplayName')"
            />
            <div class="ssh-grid" :class="{ 'no-pass': !showCredentialFields }">
              <input v-model="ssh.auth.host" class="mono" :placeholder="t('workspace.sshHost')" />
              <input
                v-model.number="ssh.auth.port"
                class="mono"
                type="number"
                min="1"
                max="65535"
                :placeholder="t('workspace.sshPort')"
              />
              <input v-model="ssh.auth.username" class="mono" :placeholder="t('workspace.sshUser')" />
              <input
                v-if="showCredentialFields"
                v-model="ssh.auth.password"
                type="password"
                :placeholder="t('workspace.sshPassword')"
              />
            </div>
            <p v-if="ssh.reusingCredentials && !showAuthOverride" class="reuse-note">
              已使用该主机已保存的凭证自动连接。
              <button type="button" class="linkish" @click="showAuthOverride = true">更换凭证</button>
            </p>
            <template v-if="showCredentialFields">
              <textarea
                v-model="ssh.auth.private_key"
                class="ssh-key mono"
                rows="3"
                :placeholder="t('workspace.sshKey')"
              />
              <input
                v-model="ssh.auth.passphrase"
                class="ssh-passphrase"
                type="password"
                :placeholder="t('workspace.sshPassphrase')"
              />
            </template>
            <div class="path-row">
              <AppIcon class="path-icon" name="folder" :size="15" :stroke-width="1.75" />
              <input
                v-model="ssh.path"
                class="path-input mono"
                :placeholder="t('workspace.sshPathPlaceholder')"
                @keydown.enter="openSsh"
              />
              <button type="button" class="btn ghost" :disabled="ssh.connecting" @click="connectSsh">
                {{ ssh.connecting ? '连接中…' : t('workspace.sshConnect') }}
              </button>
              <button type="button" class="btn primary" :disabled="!ssh.path" @click="openSsh">
                {{ t('common.open') }}
              </button>
            </div>
          </section>
        </template>

        <p v-if="activeError" class="err">{{ activeError }}</p>

        <section class="section browse">
          <h2 class="section-title">浏览</h2>
          <div class="crumbs">
            <button
              type="button"
              class="crumb-btn"
              :disabled="mode === 'local' ? !local.canGoParent : !ssh.canGoParent"
              @click="mode === 'local' ? local.goParent() : ssh.goParent()"
            >
              {{ t('common.parent') }}
            </button>
            <button
              v-if="mode === 'local'"
              type="button"
              class="crumb-btn"
              :disabled="local.atRoots"
              @click="local.startCreate"
            >
              {{ t('workspace.newFolder') }}
            </button>
            <span class="crumb-path mono">{{ mode === 'local' ? local.displayPath : ssh.displayPath }}</span>
          </div>
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
                <AppIcon name="folder" :size="15" :stroke-width="1.75" />
                <span>{{ item.name }}</span>
              </button>
            </li>
          </ul>
        </section>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.mask {
  position: fixed;
  inset: 0;
  z-index: 120;
  display: grid;
  place-items: center;
  padding: 20px;
  background: rgba(15, 23, 42, 0.42);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
}

:global(html[data-theme='dark']) .mask {
  background: rgba(0, 0, 0, 0.62);
}

.sheet {
  width: min(720px, 100%);
  max-height: min(86vh, 720px);
  overflow: auto;
  padding: 18px 20px 16px;
  border: 1px solid color-mix(in srgb, var(--border) 80%, var(--text-h));
  border-radius: 14px;
  background: var(--panel-bg);
  box-shadow:
    0 0 0 1px color-mix(in srgb, var(--text-h) 4%, transparent),
    0 18px 50px rgba(15, 23, 42, 0.22),
    0 4px 14px rgba(15, 23, 42, 0.1);
}

:global(html[data-theme='dark']) .sheet {
  background: color-mix(in srgb, var(--panel-bg) 92%, #fff 8%);
  border-color: color-mix(in srgb, var(--border) 70%, #fff);
  box-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.06),
    0 22px 56px rgba(0, 0, 0, 0.55),
    0 6px 18px rgba(0, 0, 0, 0.35);
}

.sheet-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 6px;
}

.sheet-kicker {
  display: block;
  margin-bottom: 4px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--primary);
}

.sheet-title {
  margin: 0;
  font-size: 17px;
  font-weight: 650;
  letter-spacing: -0.02em;
  color: var(--text-h);
  line-height: 1.3;
}

.sheet-close {
  width: 30px;
  height: 30px;
  margin-top: -2px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--text-muted);
  display: grid;
  place-items: center;
  cursor: pointer;
  flex-shrink: 0;
}

.sheet-close:hover {
  background: var(--code-bg);
  color: var(--text-h);
}

.mode-tabs {
  display: flex;
  gap: 6px;
  margin: 10px 0 10px;
}

.mode-tab {
  height: 30px;
  padding: 0 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 12.5px;
  font-weight: 550;
  cursor: pointer;
}

.mode-tab.active {
  border-color: color-mix(in srgb, var(--primary) 35%, var(--border));
  background: color-mix(in srgb, var(--primary) 12%, transparent);
  color: var(--text-h);
}

.sheet-lead {
  margin: 0 0 14px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-secondary);
}

.section {
  margin-bottom: 12px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: color-mix(in srgb, var(--code-bg) 55%, var(--panel-bg));
}

.section-title {
  margin: 0 0 10px;
  font-size: 11px;
  font-weight: 650;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--text-muted);
}

.path-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.path-icon {
  flex-shrink: 0;
  color: var(--text-muted);
}

.path-input,
.display-name,
.ssh-grid input,
.ssh-key,
.ssh-passphrase {
  height: 34px;
  border: 1px solid var(--border);
  border-radius: 9px;
  background: var(--panel-bg);
  color: var(--text-h);
  padding: 0 10px;
  font-size: 13px;
  font: inherit;
  outline: none;
  transition: border-color 0.12s ease, box-shadow 0.12s ease;
}

.display-name {
  width: 100%;
  margin-bottom: 8px;
}

.path-input {
  flex: 1;
  min-width: 0;
}

.path-input.mono,
.ssh-grid input.mono,
.ssh-key.mono {
  font-family: var(--mono);
  font-size: 12.5px;
}

.path-input::placeholder,
.display-name::placeholder,
.ssh-grid input::placeholder,
.ssh-key::placeholder,
.ssh-passphrase::placeholder {
  font-size: 11.5px;
  color: color-mix(in srgb, var(--text-muted) 72%, transparent);
  opacity: 1;
}

.path-input:focus,
.display-name:focus,
.ssh-grid input:focus,
.ssh-key:focus,
.ssh-passphrase:focus {
  border-color: color-mix(in srgb, var(--primary) 55%, var(--border));
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--primary) 16%, transparent);
}

.ssh-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) 78px minmax(0, 1fr) minmax(0, 1fr);
  gap: 8px;
  margin-bottom: 8px;
}

.ssh-grid.no-pass {
  grid-template-columns: minmax(0, 1.6fr) 78px minmax(0, 1.2fr);
}

.reuse-note {
  margin: 0 0 8px;
  font-size: 12px;
  line-height: 1.45;
  color: var(--text-muted);
}

.linkish {
  border: 0;
  padding: 0;
  background: transparent;
  color: var(--primary);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.ssh-key {
  display: block;
  width: 100%;
  height: auto;
  min-height: 72px;
  margin-bottom: 8px;
  padding: 8px 10px;
  resize: vertical;
  line-height: 1.45;
}

.ssh-passphrase {
  display: block;
  width: 100%;
  margin-bottom: 8px;
}

.btn {
  height: 34px;
  padding: 0 14px;
  border: 1px solid var(--border);
  border-radius: 9px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 550;
  cursor: pointer;
  flex-shrink: 0;
  white-space: nowrap;
}

.btn:disabled {
  opacity: 0.55;
  cursor: default;
}

.btn.ghost:hover:not(:disabled) {
  background: color-mix(in srgb, var(--text-h) 6%, transparent);
  color: var(--text-h);
}

.btn.primary {
  border-color: transparent;
  background: var(--primary);
  color: #fff;
}

.btn.primary:hover:not(:disabled) {
  background: var(--primary-hover);
}

.err {
  margin: 0 0 12px;
  padding: 8px 10px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--error-text) 10%, transparent);
  color: var(--error-text);
  font-size: 12.5px;
  line-height: 1.4;
}

.browse {
  margin-bottom: 0;
}

.crumbs {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.crumb-btn {
  height: 26px;
  padding: 0 8px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--panel-bg);
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
}

.crumb-btn:hover:not(:disabled) {
  color: var(--text-h);
}

.crumb-btn:disabled {
  opacity: 0.45;
  cursor: default;
}

.crumb-path {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: var(--text-muted);
}

.dirs {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 280px;
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--panel-bg);
}

.dir-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  padding: 0 10px;
  border: 0;
  border-bottom: 1px solid color-mix(in srgb, var(--border) 70%, transparent);
  background: transparent;
  color: var(--text);
  font-size: 13px;
  text-align: left;
  cursor: pointer;
}

.dirs li:last-child .dir-item {
  border-bottom: 0;
}

.dir-item:hover {
  background: color-mix(in srgb, var(--text-h) 4.5%, transparent);
  color: var(--text-h);
}

@media (max-width: 640px) {
  .ssh-grid {
    grid-template-columns: 1fr 78px;
  }
  .ssh-grid input:nth-child(3),
  .ssh-grid input:nth-child(4) {
    grid-column: 1 / -1;
  }
  .path-row {
    flex-wrap: wrap;
  }
  .path-input {
    flex: 1 1 100%;
  }
}
</style>
