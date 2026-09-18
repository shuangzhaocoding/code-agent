<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import AppIcon from '@/components/AppIcon.vue'
import type { Conversation, Workspace } from '@/stores/app'
import { useAppStore } from '@/stores/app'
import { formatRelativeTime } from '@/utils/relativeTime'

export type HostGroupLike = {
  key: string
  label: string
  kind: 'local' | 'ssh'
  workspaces: Workspace[]
}

const props = defineProps<{
  group: HostGroupLike
  open: boolean
  active: boolean
  draggableHost?: boolean
  nested?: boolean
  creatingId: string | null
  switchingId: string | null
  removingId: string | null
  openingId: string | null
  editingId: string | null
  editingTitle: string
  previewLimit: number
  isExpanded: (id: string) => boolean
  showsAll: (id: string) => boolean
  sortedConvs: (wsId: string) => Conversation[]
  visibleConvs: (wsId: string) => Conversation[]
  hiddenCount: (wsId: string) => number
  loading: Record<string, boolean>
  errors: Record<string, string>
  statusByKey: Map<string, { tone: string; label: string; icon: string } | undefined>
  isPinned: (wsId: string, id: string) => boolean
  turnCount: (wsId: string, conv: Conversation) => number
}>()

const emit = defineEmits<{
  'toggle-host': []
  'edit-host': [e: MouseEvent]
  'add-workspace': [e: MouseEvent]
  'host-contextmenu': [e: MouseEvent]
  'ws-contextmenu': [ws: Workspace, e: MouseEvent]
  'dragstart': [e: DragEvent]
  'dragend': []
  'host-tip': [e: MouseEvent]
  'host-tip-hide': []
  'ws-tip': [ws: Workspace, e: MouseEvent]
  'ws-tip-hide': []
  'toggle-expand': [wsId: string]
  'new-session': [ws: Workspace, e: MouseEvent]
  'open-workspace': [ws: Workspace, e: MouseEvent]
  'remove-workspace': [ws: Workspace, e: MouseEvent]
  'retry-convs': [wsId: string]
  'open-conv': [ws: Workspace, conv: Conversation]
  'update:editingTitle': [v: string]
  'rename-keydown': [wsId: string, id: string, e: KeyboardEvent]
  'rename-blur': [wsId: string, id: string]
  'start-rename': [conv: Conversation, e: MouseEvent]
  'toggle-pin': [wsId: string, id: string, e: MouseEvent]
  'archive': [wsId: string, conv: Conversation, e: MouseEvent]
  'delete-conv': [wsId: string, id: string, e: MouseEvent]
  'toggle-show-all': [wsId: string]
}>()

const { t } = useI18n()
const store = useAppStore()

function basename(path: string) {
  const parts = path.replace(/[\\/]+$/, '').split(/[\\/]/)
  return parts[parts.length - 1] || path
}

function onRowDragStart(e: DragEvent) {
  if (!props.draggableHost) {
    e.preventDefault()
    return
  }
  const row = e.currentTarget as HTMLElement | null
  row?.classList.add('is-dragging')
  emit('dragstart', e)
}

function onRowDragEnd(e: DragEvent) {
  const row = e.currentTarget as HTMLElement | null
  row?.classList.remove('is-dragging')
  emit('dragend')
}

const blockClass = computed(() => ({
  current: props.active,
  nested: props.nested,
}))
</script>

<template>
  <div class="host-block" :class="blockClass">
    <div
      class="host-row"
      :class="{ draggable: draggableHost }"
      :draggable="Boolean(draggableHost)"
      :title="draggableHost ? t('workspace.panel.dragHostHint') : undefined"
      @dragstart="onRowDragStart"
      @dragend="onRowDragEnd"
      @mouseenter="emit('host-tip', $event)"
      @mouseleave="emit('host-tip-hide')"
      @contextmenu.prevent.stop="emit('host-contextmenu', $event)"
    >
      <div
        class="host-main"
        role="button"
        tabindex="0"
        @click="emit('toggle-host')"
        @keydown.enter.prevent="emit('toggle-host')"
        @keydown.space.prevent="emit('toggle-host')"
      >
        <AppIcon
          class="host-chev"
          :name="open ? 'chevron-down' : 'chevron-right'"
          :size="11"
          :stroke-width="2"
        />
        <AppIcon
          class="host-icon"
          :class="{ 'is-ssh': group.kind === 'ssh' }"
          :name="group.kind === 'ssh' ? 'globe' : 'folder'"
          :size="13"
          :stroke-width="1.75"
        />
        <span class="host-label">{{ group.label }}</span>
        <span v-if="group.kind === 'ssh'" class="host-ssh-mark" title="SSH">SSH</span>
      </div>
      <div class="host-end">
        <span class="host-count">{{ group.workspaces.length }}</span>
        <div class="host-tools">
          <button
            v-if="group.kind === 'ssh'"
            type="button"
            class="host-tool"
            draggable="false"
            :title="t('workspace.panel.editHost')"
            @click="emit('edit-host', $event)"
            @dragstart.stop.prevent
          >
            <AppIcon name="pencil" :size="13" :stroke-width="1.75" />
          </button>
          <button
            type="button"
            class="host-tool"
            draggable="false"
            :title="group.kind === 'ssh' ? t('workspace.panel.addRemoteWorkspace') : t('workspace.panel.addLocalWorkspace')"
            @click="emit('add-workspace', $event)"
            @dragstart.stop.prevent
          >
            <AppIcon name="plus" :size="13" :stroke-width="1.75" />
          </button>
        </div>
        <span v-if="active" class="host-dot" :title="t('workspace.panel.currentHost')" />
      </div>
    </div>

    <ul v-if="open" class="ws-list">
      <li
        v-for="ws in group.workspaces"
        :key="ws.id"
        class="ws-group"
        :class="{ current: ws.id === store.workspaceId, open: isExpanded(ws.id) }"
      >
        <div
          class="ws-row"
          @mouseenter="emit('ws-tip', ws, $event)"
          @mouseleave="emit('ws-tip-hide')"
          @contextmenu.prevent.stop="emit('ws-contextmenu', ws, $event)"
        >
          <button type="button" class="ws-main" @click="emit('toggle-expand', ws.id)">
            <AppIcon
              class="ws-chev"
              :name="isExpanded(ws.id) ? 'chevron-down' : 'chevron-right'"
              :size="12"
              :stroke-width="2"
            />
            <AppIcon class="ws-icon" name="folder" :size="14" :stroke-width="1.75" />
            <span class="ws-copy">
              <span class="ws-name">{{ ws.name || basename(ws.root_path) }}</span>
              <span
                v-if="ws.root_missing || (ws.id === store.workspaceId && store.workspaceRootMissing)"
                class="ws-missing-badge"
              >{{ t('workspace.panel.rootMissingBadge') }}</span>
            </span>
          </button>
          <div class="ws-end">
            <div class="ws-tools">
              <button
                type="button"
                class="ws-tool"
                :title="t('workspace.panel.newSession')"
                :disabled="creatingId === ws.id"
                @click="emit('new-session', ws, $event)"
              >
                <AppIcon name="plus" :size="13" :stroke-width="1.75" />
              </button>
              <button
                v-if="ws.id !== store.workspaceId"
                type="button"
                class="ws-tool text"
                :disabled="switchingId === ws.id"
                @click="emit('open-workspace', ws, $event)"
              >
                {{ t('workspace.panel.open') }}
              </button>
              <button
                type="button"
                class="ws-tool danger"
                :title="t('workspace.panel.removeWorkspace')"
                :disabled="removingId === ws.id"
                @click="emit('remove-workspace', ws, $event)"
              >
                <AppIcon name="trash" :size="13" :stroke-width="1.75" />
              </button>
            </div>
            <span v-if="ws.id === store.workspaceId" class="ws-dot" :title="t('workspace.panel.currentWorkspace')" />
          </div>
        </div>

        <div v-if="isExpanded(ws.id)" class="ws-sessions">
          <p v-if="loading[ws.id]" class="hint">{{ t('workspace.panel.loading') }}</p>
          <p v-else-if="errors[ws.id]" class="hint err">
            <span>{{ errors[ws.id] }}</span>
            <button type="button" class="hint-retry" @click="emit('retry-convs', ws.id)">
              {{ t('workspace.panel.retry') }}
            </button>
          </p>
          <p v-else-if="!sortedConvs(ws.id).length" class="hint">{{ t('workspace.panel.noSessions') }}</p>

          <div
            v-for="conv in visibleConvs(ws.id)"
            :key="conv.id"
            class="conv-row"
            :class="{
              active: conv.id === store.conversationId && ws.id === store.workspaceId,
              pinned: isPinned(ws.id, conv.id),
              opening: openingId === conv.id,
            }"
            :aria-busy="openingId === conv.id"
            @click="emit('open-conv', ws, conv)"
          >
            <span class="conv-status-slot">
              <span
                v-if="openingId === conv.id"
                class="conv-status opening"
                :title="t('workspace.panel.opening')"
                :aria-label="t('workspace.panel.opening')"
              >
                <AppIcon class="spin" name="loader" :size="12" :stroke-width="1.75" />
              </span>
              <template v-else v-for="st in [statusByKey.get(`${ws.id}:${conv.id}`)]" :key="`${conv.id}-status`">
                <span
                  v-if="st"
                  class="conv-status"
                  :class="st.tone"
                  :title="st.label"
                  :aria-label="st.label"
                >
                  <AppIcon :name="st.icon as any" :size="12" :stroke-width="1.75" />
                </span>
              </template>
            </span>
            <span class="conv-copy">
              <input
                v-if="editingId === conv.id"
                class="conv-rename-input"
                type="text"
                maxlength="300"
                :value="editingTitle"
                :aria-label="t('workspace.panel.rename')"
                @click.stop
                @input="emit('update:editingTitle', ($event.target as HTMLInputElement).value)"
                @keydown="emit('rename-keydown', ws.id, conv.id, $event)"
                @blur="emit('rename-blur', ws.id, conv.id)"
              />
              <span v-else class="conv-title" :title="conv.title">{{ conv.title }}</span>
            </span>
            <span class="conv-meta">
              <span v-if="!editingId" class="conv-time">
                {{ formatRelativeTime(conv.updated_at || conv.created_at) }}
              </span>
            </span>
            <span class="conv-actions">
              <button type="button" class="conv-action" :title="t('workspace.panel.rename')" @click="emit('start-rename', conv, $event)">
                <AppIcon name="pencil" :size="13" :stroke-width="1.75" />
              </button>
              <button
                type="button"
                class="conv-action"
                :class="{ on: isPinned(ws.id, conv.id) }"
                :title="isPinned(ws.id, conv.id) ? t('workspace.panel.unpin') : t('workspace.panel.pin')"
                @click="emit('toggle-pin', ws.id, conv.id, $event)"
              >
                <AppIcon name="pin" :size="13" :stroke-width="1.75" />
              </button>
              <button
                type="button"
                class="conv-action"
                :title="conv.archived ? t('workspace.panel.unarchive') : t('workspace.panel.archive')"
                @click="emit('archive', ws.id, conv, $event)"
              >
                <AppIcon name="inbox" :size="13" :stroke-width="1.75" />
              </button>
              <button
                type="button"
                class="conv-action danger"
                :title="t('workspace.panel.deleteSession')"
                @click="emit('delete-conv', ws.id, conv.id, $event)"
              >
                <AppIcon name="trash" :size="13" :stroke-width="1.75" />
              </button>
            </span>
            <span class="conv-turns">{{ t('workspace.panel.turns', { n: turnCount(ws.id, conv) }) }}</span>
          </div>

          <button
            v-if="hiddenCount(ws.id)"
            type="button"
            class="show-more"
            @click="emit('toggle-show-all', ws.id)"
          >
            {{ t('workspace.panel.showMore', { n: hiddenCount(ws.id) }) }}
          </button>
          <button
            v-else-if="showsAll(ws.id) && sortedConvs(ws.id).length > previewLimit"
            type="button"
            class="show-more"
            @click="emit('toggle-show-all', ws.id)"
          >
            {{ t('workspace.panel.showLess') }}
          </button>
        </div>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.host-block {
  margin-bottom: 10px;
  padding: 4px 0 6px;
  border: var(--border-width) solid var(--border);
  border-radius: 10px;
  background: color-mix(in srgb, var(--text-h) 3%, var(--sidebar-bg));
  overflow: hidden;
}
.host-block.nested {
  margin: 0 6px 8px;
  background: color-mix(in srgb, var(--text-h) 2%, var(--sidebar-bg));
}
.host-row.draggable {
  cursor: grab;
}
.host-row.draggable:active {
  cursor: grabbing;
}
.host-main,
.host-tool {
  -webkit-user-drag: none;
  user-select: none;
}
.host-row {
  display: flex;
  align-items: center;
  gap: 4px;
  min-height: 30px;
  margin: 0 4px;
  padding-right: 4px;
  border-radius: 8px;
  color: var(--text-secondary);
}
.host-row:hover {
  background: color-mix(in srgb, var(--text-h) 5%, transparent);
  color: var(--text-h);
}
.host-main {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 30px;
  padding: 4px 6px 4px 8px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font: inherit;
  text-align: left;
}
.host-tools {
  position: absolute;
  right: 100%;
  top: 50%;
  display: flex;
  align-items: center;
  gap: 0;
  margin-right: 2px;
  padding: 1px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--panel-bg) 88%, transparent);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--border) 80%, transparent);
  opacity: 0;
  pointer-events: none;
  transform: translate(4px, -50%);
  transition: opacity 0.12s ease, transform 0.12s ease;
}
.host-end {
  position: relative;
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  min-height: 22px;
  min-width: 22px;
  justify-content: flex-end;
}
.host-row:hover .host-tools,
.host-row:focus-within .host-tools {
  opacity: 1;
  pointer-events: auto;
  transform: translate(0, -50%);
}
.host-row:hover .host-count,
.host-row:focus-within .host-count {
  opacity: 1;
}
@media (hover: none) {
  .host-tools {
    position: static;
    opacity: 1;
    pointer-events: auto;
    transform: none;
    margin-right: 0;
    background: transparent;
    box-shadow: none;
    padding: 0;
  }
}
.host-tool {
  box-sizing: border-box;
  width: 22px;
  height: 22px;
  min-width: 22px;
  padding: 0;
  margin: 0;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--text-muted);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  line-height: 0;
  flex-shrink: 0;
  cursor: pointer;
}
.host-tool :deep(.app-icon) {
  display: block;
}
.host-tool:hover {
  background: var(--code-bg);
  color: var(--text-h);
}
.host-chev,
.host-icon {
  flex-shrink: 0;
  opacity: 0.95;
  color: var(--text-h);
}
.host-icon.is-ssh {
  color: #0284c7;
}
.host-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  font-weight: 650;
  letter-spacing: 0.01em;
  color: var(--text-h);
}
.host-ssh-mark {
  flex-shrink: 0;
  height: 15px;
  padding: 0 4px;
  border-radius: 4px;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.04em;
  line-height: 15px;
  color: #0284c7;
  background: color-mix(in srgb, #0284c7 14%, transparent);
}
.ws-badge {
  flex-shrink: 0;
  height: 16px;
  padding: 0 5px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 600;
  line-height: 16px;
  letter-spacing: 0.02em;
}
.host-count {
  flex-shrink: 0;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 600;
  color: var(--text-secondary);
  background: color-mix(in srgb, var(--text-h) 8%, transparent);
  font-variant-numeric: tabular-nums;
  opacity: 0.55;
  transition: opacity 0.12s ease;
}
.host-dot {
  width: 6px;
  height: 6px;
  margin: 0 8px 0 4px;
  border-radius: 50%;
  background: #22c55e;
  box-shadow: 0 0 0 2px color-mix(in srgb, #22c55e 25%, transparent);
  flex-shrink: 0;
}
.host-block .ws-list {
  padding: 2px 4px 2px 6px;
}
.empty,
.hint {
  margin: 8px 6px;
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.45;
}
.hint.err {
  color: var(--error-text);
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.hint-retry {
  border: 0;
  border-radius: 5px;
  padding: 2px 8px;
  background: color-mix(in srgb, var(--primary) 12%, transparent);
  color: var(--primary);
  font: inherit;
  font-size: 11px;
  cursor: pointer;
}
.hint-retry:hover {
  background: color-mix(in srgb, var(--primary) 18%, transparent);
}
.ws-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.ws-group {
  border-radius: 10px;
}
.ws-row {
  display: flex;
  align-items: center;
  min-height: 30px;
  padding-right: 6px;
  border-radius: 10px;
}
.ws-row:hover {
  background: color-mix(in srgb, var(--text-h) 4.5%, transparent);
}
.ws-main {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 30px;
  padding: 4px 4px 4px 8px;
  border: 0;
  border-radius: 10px;
  background: transparent;
  color: var(--text-h);
  text-align: left;
  cursor: pointer;
  font: inherit;
}
.ws-chev {
  flex-shrink: 0;
  color: var(--text-muted);
  opacity: 0.85;
}
.ws-icon {
  flex-shrink: 0;
  color: var(--text-secondary);
}
.ws-group.current .ws-icon {
  color: var(--primary);
}
.ws-copy {
  min-width: 0;
  flex: 1;
  display: flex;
  align-items: center;
  gap: 6px;
}
.ws-name {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  font-weight: 600;
  line-height: 17px;
  min-width: 0;
  flex: 1;
}
.ws-missing-badge {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
  padding: 0 5px;
  height: 16px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.02em;
  line-height: 1;
  color: var(--danger, #ef4444);
  background: color-mix(in srgb, var(--danger, #ef4444) 14%, transparent);
}
.ws-dot {
  width: 6px;
  height: 6px;
  margin: 0 4px;
  border-radius: 50%;
  background: var(--primary);
  flex-shrink: 0;
}
.ws-end {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  min-height: 22px;
}
.ws-tools {
  display: flex;
  align-items: center;
  gap: 2px;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.12s ease;
}
.ws-row:hover .ws-tools,
.ws-row:focus-within .ws-tools {
  opacity: 1;
  pointer-events: auto;
}
.ws-tool {
  height: 22px;
  min-width: 22px;
  padding: 0;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--text-muted);
  display: grid;
  place-items: center;
  cursor: pointer;
}
.ws-tool.text {
  padding: 0 8px;
  font-size: 11px;
  font-weight: 500;
  color: var(--text-secondary);
}
.ws-tool:hover {
  background: var(--code-bg);
  color: var(--text-h);
}
.ws-tool.danger:hover {
  color: var(--danger);
  background: color-mix(in srgb, var(--danger) 8%, transparent);
}
.ws-tool:disabled {
  opacity: 0.45;
  cursor: default;
}
.ws-sessions {
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: 1px 0 6px 8px;
}
.conv-row {
  position: relative;
  width: 100%;
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 30px;
  padding: 4px 8px;
  border-radius: 10px;
  color: var(--text);
  cursor: pointer;
}
.conv-row:hover {
  background: color-mix(in srgb, var(--text-h) 4.5%, transparent);
  color: var(--text-h);
}
.conv-row.active {
  background: color-mix(in srgb, var(--primary) 10%, transparent);
  color: var(--text-h);
}
.conv-row.opening {
  opacity: 0.78;
  pointer-events: none;
}
.conv-row.active .conv-title {
  color: var(--text-h);
  font-weight: 600;
}
.conv-status-slot {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  display: grid;
  place-items: center;
}
.conv-status {
  width: 14px;
  height: 14px;
  display: grid;
  place-items: center;
  color: var(--text-muted);
}
.conv-status.running,
.conv-status.opening {
  color: var(--primary);
}
.conv-status.running :deep(svg),
.conv-status.opening :deep(svg),
.spin {
  animation: conv-spin 0.9s linear infinite;
}
.conv-status.confirm {
  color: var(--danger);
}
.conv-status.queued {
  color: var(--text-muted);
}
@keyframes conv-spin {
  to {
    transform: rotate(360deg);
  }
}
.conv-copy {
  min-width: 0;
  flex: 1;
}
.conv-title {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  font-weight: 500;
  line-height: 17px;
}
.conv-rename-input {
  width: 100%;
  min-width: 0;
  height: 22px;
  padding: 0 6px;
  border: var(--border-width) solid color-mix(in srgb, var(--primary) 40%, var(--border));
  border-radius: 6px;
  background: var(--panel-bg);
  color: var(--text-h);
  font: inherit;
  font-size: 12px;
  outline: none;
}
.conv-meta {
  display: flex;
  align-items: center;
  align-self: center;
  gap: 8px;
  flex-shrink: 0;
  font-size: 11px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
  line-height: 22px;
  height: 22px;
}
.conv-turns {
  flex-shrink: 0;
  align-self: center;
  min-width: 2.5rem;
  height: 22px;
  line-height: 22px;
  text-align: right;
  font-size: 11px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}
.conv-row:hover .conv-time,
.conv-row:focus-within .conv-time {
  visibility: hidden;
}
.conv-actions {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  align-self: center;
  gap: 1px;
  flex-shrink: 0;
  height: 22px;
  opacity: 0;
  pointer-events: none;
  width: 0;
  overflow: hidden;
}
.conv-row:hover .conv-actions,
.conv-row:focus-within .conv-actions,
.conv-row.pinned .conv-actions {
  opacity: 1;
  pointer-events: auto;
  width: auto;
  overflow: visible;
}
.conv-action {
  box-sizing: border-box;
  width: 22px;
  height: 22px;
  min-width: 22px;
  padding: 0;
  margin: 0;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--text-muted);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  line-height: 0;
  flex-shrink: 0;
  cursor: pointer;
}
.conv-action :deep(.app-icon) {
  display: block;
}
.conv-action:hover,
.conv-action.on {
  color: var(--primary);
  background: var(--code-bg);
}
.conv-action.danger:hover {
  color: var(--danger);
}
.conv-action.on {
  opacity: 1;
}
.show-more {
  width: 100%;
  height: 26px;
  margin-top: 2px;
  padding: 0 10px 0 8px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--text-muted);
  font-size: 11px;
  text-align: left;
  cursor: pointer;
}
.show-more:hover {
  background: color-mix(in srgb, var(--text-h) 4%, transparent);
  color: var(--text-secondary);
}
.host-block.dragging {
  opacity: 0.45;
}
.host-row.is-dragging {
  opacity: 0.45;
}
</style>
