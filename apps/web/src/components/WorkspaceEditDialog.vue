<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAppStore, type Workspace } from '@/stores/app'
import AppIcon from '@/components/AppIcon.vue'
import { loadExtraHostGroups, rememberHostGroup } from '@/utils/sshHostGroups'

const props = defineProps<{
  workspaces: Workspace[]
  label: string
  knownGroups?: string[]
}>()
const emit = defineEmits<{ close: [] }>()

const { t } = useI18n()
const store = useAppStore()
const saving = ref(false)
const error = ref('')

const sample = props.workspaces[0]
const hasSecret = props.workspaces.some((w) => w.has_ssh_secret)

const form = reactive({
  ssh_display_name: (sample?.ssh_display_name || '').trim(),
  ssh_group: (sample?.ssh_group || '').trim(),
  ssh_host: sample?.ssh_host || '',
  ssh_port: sample?.ssh_port || 22,
  ssh_user: sample?.ssh_user || '',
  ssh_password: '',
  ssh_private_key: '',
  ssh_passphrase: '',
})

const groupOptions = computed(() => {
  const set = new Set<string>([...(props.knownGroups || []), ...loadExtraHostGroups()])
  for (const ws of store.recentWorkspaces) {
    const g = (ws.ssh_group || '').trim()
    if (g) set.add(g)
  }
  const cur = form.ssh_group.trim()
  if (cur) set.add(cur)
  return [...set].sort((a, b) => a.localeCompare(b))
})

const endpointHint = computed(() => {
  const host = form.ssh_host.trim() || 'host'
  const port = Number(form.ssh_port) || 22
  const user = form.ssh_user.trim()
  return user ? `${user}@${host}:${port}` : `${host}:${port}`
})

async function save() {
  if (saving.value || !props.workspaces.length) return
  const host = form.ssh_host.trim()
  const user = form.ssh_user.trim()
  const port = Number(form.ssh_port) || 22
  if (!host || !user) {
    error.value = '主机和用户名不能为空'
    return
  }
  saving.value = true
  error.value = ''
  try {
    const group = form.ssh_group.trim()
    const payload: Record<string, string | number> = {
      ssh_display_name: form.ssh_display_name.trim(),
      ssh_group: group,
      ssh_host: host,
      ssh_port: port,
      ssh_user: user,
    }
    if (form.ssh_password.trim()) payload.ssh_password = form.ssh_password
    if (form.ssh_private_key.trim()) payload.ssh_private_key = form.ssh_private_key
    if (form.ssh_passphrase.trim()) payload.ssh_passphrase = form.ssh_passphrase

    for (const ws of props.workspaces) {
      await store.updateWorkspace(ws.id, payload)
    }
    if (group) rememberHostGroup(group)
    emit('close')
  } catch (err) {
    const raw = err instanceof Error ? err.message : String(err)
    try {
      const parsed = JSON.parse(raw) as { message?: string }
      error.value = parsed.message || raw
    } catch {
      error.value = raw
    }
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Teleport to="body">
    <div class="mask" @click.self="emit('close')">
      <div class="sheet" role="dialog" aria-modal="true" :aria-label="t('workspace.panel.editHost')">
        <header class="sheet-head">
          <div class="sheet-head-copy">
            <span class="sheet-kicker">SSH</span>
            <h1 class="sheet-title">{{ t('workspace.panel.editHost') }}</h1>
          </div>
          <button type="button" class="sheet-close" :title="t('common.close')" @click="emit('close')">
            <AppIcon name="close" :size="16" :stroke-width="1.75" />
          </button>
        </header>

        <p class="sheet-lead">
          {{ t('workspace.panel.editHostLead', { n: workspaces.length }) }}
        </p>

        <section class="section">
          <h2 class="section-title">{{ t('workspace.panel.hostDisplay') }}</h2>
          <label class="field">
            <span>{{ t('workspace.sshDisplayName') }}</span>
            <input
              v-model="form.ssh_display_name"
              type="text"
              maxlength="120"
              :placeholder="endpointHint"
              @keydown.enter="save"
            />
            <span class="hint">{{ t('workspace.panel.hostDisplayHint', { endpoint: endpointHint }) }}</span>
          </label>
          <label class="field">
            <span>{{ t('workspace.panel.hostGroup') }}</span>
            <input
              v-model="form.ssh_group"
              type="text"
              maxlength="120"
              list="ca-host-group-options"
              :placeholder="t('workspace.panel.hostGroupPlaceholder')"
              @keydown.enter="save"
            />
            <datalist id="ca-host-group-options">
              <option v-for="name in groupOptions" :key="name" :value="name" />
            </datalist>
            <span class="hint">{{ t('workspace.panel.hostGroupHint') }}</span>
          </label>
        </section>

        <section class="section">
          <h2 class="section-title">{{ t('workspace.panel.hostConnection') }}</h2>
          <div class="ssh-grid">
            <label class="field host">
              <span>{{ t('workspace.sshHost') }}</span>
              <input v-model="form.ssh_host" class="mono" type="text" placeholder="IP / hostname" />
            </label>
            <label class="field port">
              <span>{{ t('workspace.sshPort') }}</span>
              <input v-model.number="form.ssh_port" class="mono" type="number" min="1" max="65535" />
            </label>
            <label class="field user">
              <span>{{ t('workspace.sshUser') }}</span>
              <input v-model="form.ssh_user" class="mono" type="text" />
            </label>
            <label class="field pass">
              <span>{{ t('workspace.sshPassword') }}</span>
              <input
                v-model="form.ssh_password"
                type="password"
                :placeholder="hasSecret ? t('workspace.panel.keepSecret') : t('workspace.sshPassword')"
              />
            </label>
          </div>
          <label class="field">
            <span>{{ t('workspace.sshKey') }}</span>
            <textarea
              v-model="form.ssh_private_key"
              class="ssh-key mono"
              rows="3"
              :placeholder="hasSecret ? t('workspace.panel.keepKey') : t('common.optional')"
            />
          </label>
          <label class="field">
            <span>{{ t('workspace.sshPassphrase') }}</span>
            <input
              v-model="form.ssh_passphrase"
              type="password"
              :placeholder="hasSecret ? t('workspace.panel.keepSecret') : t('common.optional')"
            />
          </label>
        </section>

        <p v-if="error" class="err">{{ error }}</p>

        <footer class="actions">
          <button type="button" class="btn btn-ghost" :disabled="saving" @click="emit('close')">
            {{ t('common.cancel') }}
          </button>
          <button type="button" class="btn btn-primary" :disabled="saving" @click="save">
            {{ saving ? t('common.saving') : t('common.save') }}
          </button>
        </footer>
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
  width: min(640px, 100%);
  max-height: min(86vh, 680px);
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

.sheet-lead {
  margin: 0 0 16px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-secondary);
}

.sheet-lead strong {
  color: var(--text-h);
  font-weight: 600;
}

.section {
  margin-bottom: 14px;
  padding: 12px 12px 4px;
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

.field {
  display: flex;
  flex-direction: column;
  gap: 5px;
  margin-bottom: 10px;
}

.field > span:first-child {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}

.field input,
.ssh-key {
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

.field input::placeholder,
.ssh-key::placeholder {
  font-size: 11.5px;
  color: color-mix(in srgb, var(--text-muted) 72%, transparent);
  opacity: 1;
}

.field input.mono,
.ssh-key.mono {
  font-family: var(--mono);
  font-size: 12.5px;
}

.field input:focus,
.ssh-key:focus {
  border-color: color-mix(in srgb, var(--primary) 55%, var(--border));
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--primary) 16%, transparent);
}

.hint {
  font-size: 11px;
  line-height: 1.4;
  color: var(--text-muted);
}

.ssh-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) 78px minmax(0, 1fr) minmax(0, 1fr);
  gap: 8px;
}

.ssh-key {
  height: auto;
  min-height: 72px;
  padding: 8px 10px;
  width: 100%;
  resize: vertical;
  line-height: 1.45;
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

.actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 4px;
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
}

.btn:disabled {
  opacity: 0.55;
  cursor: default;
}

.btn.ghost:hover:not(:disabled) {
  background: var(--code-bg);
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

@media (max-width: 560px) {
  .ssh-grid {
    grid-template-columns: 1fr 78px;
  }
  .ssh-grid .user,
  .ssh-grid .pass {
    grid-column: 1 / -1;
  }
}
</style>
