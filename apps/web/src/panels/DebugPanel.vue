<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppIcon from '@/components/AppIcon.vue'
import DebugActionIcon from '@/components/DebugActionIcon.vue'
import DebugVarTree from '@/components/DebugVarTree.vue'
import { useAppStore } from '@/stores/app'
import { useDebugStore } from '@/stores/debug'

const { t } = useI18n()
const app = useAppStore()
const debug = useDebugStore()

type SideView = 'callStack' | 'breakpoints' | 'watch' | 'exceptions' | null

const sideView = ref<SideView>(null)
const watchInput = ref('')
const consoleInput = ref('')
const consoleEl = ref<HTMLElement | null>(null)
const consoleInputEl = ref<HTMLInputElement | null>(null)
const conditionPath = ref<string | null>(null)
const conditionLine = ref<number | null>(null)
const conditionText = ref('')

onMounted(() => {
  void debug.loadConfigs()
  void debug.hydrateBreakpoints(true)
})

watch(
  () => app.workspaceId,
  () => {
    void debug.loadConfigs()
    void debug.hydrateBreakpoints(true)
    debug.reset()
    sideView.value = null
  },
)

watch(
  () => debug.activeSessionId,
  () => {
    sideView.value = null
  },
)

watch(
  () => debug.consoleLines.length,
  async () => {
    await nextTick()
    if (consoleEl.value) consoleEl.value.scrollTop = consoleEl.value.scrollHeight
  },
)

function toggleSideView(view: Exclude<SideView, null>) {
  sideView.value = sideView.value === view ? null : view
}

function openCondition(path: string, line: number) {
  conditionPath.value = path
  conditionLine.value = line
  const bp = debug.breakpointsFor(path).find((b) => b.line === line)
  conditionText.value = bp?.condition || ''
}

function saveCondition() {
  if (!conditionPath.value || conditionLine.value == null) return
  debug.setBreakpointCondition(conditionPath.value, conditionLine.value, conditionText.value)
  conditionPath.value = null
  conditionLine.value = null
}

function addWatch() {
  debug.addWatch(watchInput.value)
  watchInput.value = ''
}

function focusConsoleInput() {
  consoleInputEl.value?.focus()
}

function submitConsole() {
  const expr = consoleInput.value.trim()
  if (!expr || !debug.paused) return
  consoleInput.value = ''
  void debug.evaluate(expr).then(async () => {
    await nextTick()
    if (consoleEl.value) consoleEl.value.scrollTop = consoleEl.value.scrollHeight
  })
}

const bpEntries = computed(() =>
  Object.entries(debug.breakpoints).flatMap(([path, list]) =>
    list.map((bp) => ({ path, ...bp })),
  ),
)

const sideViewTitle = computed(() => {
  switch (sideView.value) {
    case 'callStack':
      return t('debug.callStack')
    case 'breakpoints':
      return t('debug.breakpoints')
    case 'watch':
      return t('debug.watch')
    case 'exceptions':
      return t('debug.exceptions')
    default:
      return ''
  }
})
</script>

<template>
  <div class="debug-panel">
    <div v-if="debug.sessions.length" class="session-tabs" role="tablist">
      <button
        v-for="s in debug.sessions"
        :key="s.id"
        type="button"
        role="tab"
        class="session-tab"
        :class="{ active: s.id === debug.activeSessionId }"
        :data-state="s.state"
        :title="s.program || s.title"
        @click="debug.selectSession(s.id)"
      >
        <span class="session-tab-title">{{ s.title }}</span>
        <span
          class="session-tab-close"
          :title="t('debug.stop')"
          @click.stop="debug.closeSession(s.id)"
        >
          <AppIcon name="close" :size="11" />
        </span>
      </button>
    </div>

    <header v-if="debug.activeSession" class="toolbar">
      <div class="actions">
        <button
          type="button"
          class="dbg-btn dbg-btn--restart"
          :disabled="!debug.canRestart"
          :title="t('debug.restartHint')"
          @click="debug.restart()"
        >
          <DebugActionIcon kind="restart" :size="16" />
        </button>
        <button
          type="button"
          class="dbg-btn dbg-btn--stop"
          :disabled="!debug.active || debug.busy"
          :title="t('debug.stop')"
          @click="debug.callControl('stop')"
        >
          <AppIcon name="debug-stop" :size="13" />
        </button>
        <span class="dbg-sep" aria-hidden="true" />
        <button
          type="button"
          class="dbg-btn dbg-btn--continue"
          :disabled="!debug.canStep"
          :title="t('debug.continueHint')"
          @click="debug.callControl('continue')"
        >
          <AppIcon name="debug-continue" :size="15" :stroke-width="1.6" />
        </button>
        <button
          type="button"
          class="dbg-btn"
          :disabled="!debug.canPause"
          :title="t('debug.pause')"
          @click="debug.callControl('pause')"
        >
          <AppIcon name="debug-pause" :size="15" :stroke-width="1.6" />
        </button>
        <button
          type="button"
          class="dbg-btn"
          :disabled="!debug.canStep"
          :title="t('debug.stepOverHint')"
          @click="debug.callControl('next')"
        >
          <AppIcon name="debug-step-over" :size="15" :stroke-width="1.6" />
        </button>
        <button
          type="button"
          class="dbg-btn"
          :disabled="!debug.canStep"
          :title="t('debug.stepInHint')"
          @click="debug.callControl('stepIn')"
        >
          <AppIcon name="debug-step-into" :size="15" :stroke-width="1.6" />
        </button>
        <button
          type="button"
          class="dbg-btn"
          :disabled="!debug.canStep"
          :title="t('debug.stepOutHint')"
          @click="debug.callControl('stepOut')"
        >
          <AppIcon name="debug-step-out" :size="15" :stroke-width="1.6" />
        </button>
        <span class="dbg-sep" aria-hidden="true" />
        <button
          type="button"
          class="dbg-btn"
          :class="{ active: sideView === 'callStack' }"
          :title="t('debug.callStack')"
          @click="toggleSideView('callStack')"
        >
          <AppIcon name="list" :size="15" :stroke-width="1.6" />
        </button>
        <button
          type="button"
          class="dbg-btn"
          :class="{ active: sideView === 'breakpoints' }"
          :title="t('debug.breakpoints')"
          @click="toggleSideView('breakpoints')"
        >
          <AppIcon name="circle" :size="15" :stroke-width="1.6" />
        </button>
        <button
          type="button"
          class="dbg-btn"
          :class="{ active: sideView === 'watch' }"
          :title="t('debug.watch')"
          @click="toggleSideView('watch')"
        >
          <AppIcon name="eye" :size="15" :stroke-width="1.6" />
        </button>
        <button
          type="button"
          class="dbg-btn"
          :class="{ active: sideView === 'exceptions' }"
          :title="t('debug.exceptions')"
          @click="toggleSideView('exceptions')"
        >
          <AppIcon name="alert" :size="15" :stroke-width="1.6" />
        </button>
      </div>
      <p v-if="debug.error" class="status-inline">
        <span class="err">{{ debug.error }}</span>
      </p>
    </header>

    <p v-if="!debug.sessions.length" class="empty-sessions">{{ t('debug.noSessions') }}</p>

    <template v-else>
      <section v-if="sideView" class="side-drawer">
        <div class="side-drawer-head">
          <h3>{{ sideViewTitle }}</h3>
          <button type="button" class="dbg-btn dbg-btn--tiny" :title="t('common.close')" @click="sideView = null">
            <AppIcon name="close" :size="12" />
          </button>
        </div>

        <div v-if="sideView === 'callStack'" class="side-drawer-body">
          <ul v-if="debug.frames.length" class="list">
            <li
              v-for="fr in debug.frames"
              :key="fr.id"
              :class="{ active: fr.id === debug.activeFrameId }"
              @click="debug.loadScopes(fr.id)"
            >
              <span class="name">{{ fr.name }}</span>
              <span class="meta">{{ fr.path || '?' }}:{{ fr.line }}</span>
            </li>
          </ul>
          <p v-else class="empty">{{ t('debug.noFrames') }}</p>
        </div>

        <div v-else-if="sideView === 'breakpoints'" class="side-drawer-body">
          <ul v-if="bpEntries.length" class="list">
            <li v-for="bp in bpEntries" :key="bp.path + ':' + bp.line">
              <button type="button" class="link" @click="app.openPathAtLine(bp.path, bp.line)">
                {{ bp.path }}:{{ bp.line }}
              </button>
              <button type="button" class="link dim" @click="openCondition(bp.path, bp.line)">
                {{ bp.condition || t('debug.setCondition') }}
              </button>
              <button type="button" class="dbg-btn dbg-btn--tiny" @click="debug.toggleBreakpoint(bp.path, bp.line)">
                <AppIcon name="close" :size="12" />
              </button>
            </li>
          </ul>
          <p v-else class="empty">{{ t('debug.noBreakpoints') }}</p>
        </div>

        <div v-else-if="sideView === 'watch'" class="side-drawer-body">
          <form class="row" @submit.prevent="addWatch">
            <input v-model="watchInput" :placeholder="t('debug.watchPlaceholder')" />
            <button type="submit" class="btn">{{ t('common.add') }}</button>
          </form>
          <ul class="list">
            <li v-for="w in debug.watches" :key="w.id" class="watch">
              <span class="name">{{ w.expression }}</span>
              <span class="meta">{{ w.error || w.value }}</span>
              <button type="button" class="dbg-btn dbg-btn--tiny" @click="debug.removeWatch(w.id)">
                <AppIcon name="close" :size="12" />
              </button>
            </li>
          </ul>
        </div>

        <div v-else-if="sideView === 'exceptions'" class="side-drawer-body">
          <label class="check">
            <input
              type="checkbox"
              :checked="debug.exceptionFilters.includes('raised')"
              @change="
                debug.setExceptionFilters(
                  ($event.target as HTMLInputElement).checked
                    ? [...new Set([...debug.exceptionFilters, 'raised'])]
                    : debug.exceptionFilters.filter((f) => f !== 'raised'),
                )
              "
            />
            {{ t('debug.exceptionRaised') }}
          </label>
          <label class="check">
            <input
              type="checkbox"
              :checked="debug.exceptionFilters.includes('uncaught')"
              @change="
                debug.setExceptionFilters(
                  ($event.target as HTMLInputElement).checked
                    ? [...new Set([...debug.exceptionFilters, 'uncaught'])]
                    : debug.exceptionFilters.filter((f) => f !== 'uncaught'),
                )
              "
            />
            {{ t('debug.exceptionUncaught') }}
          </label>
        </div>
      </section>

      <div class="debug-split">
        <div class="debug-col debug-col--left">
          <section class="block grow">
            <h3>{{ t('debug.console') }}</h3>
            <div ref="consoleEl" class="console" @click="focusConsoleInput">
              <div v-for="(line, i) in debug.consoleLines" :key="i" :class="['cline', line.kind]">
                {{ line.kind === 'in' ? '› ' : '' }}{{ line.text }}
              </div>
              <div class="console-input-row">
                <span class="console-prompt">›</span>
                <input
                  ref="consoleInputEl"
                  v-model="consoleInput"
                  class="console-input"
                  :disabled="!debug.paused"
                  :placeholder="t('debug.consolePlaceholder')"
                  spellcheck="false"
                  @keydown.enter.prevent="submitConsole"
                />
              </div>
            </div>
          </section>
        </div>

        <div class="debug-col debug-col--right">
          <section class="block grow">
            <h3>{{ t('debug.variables') }}</h3>
            <div class="vars-scroll">
              <div v-for="scope in debug.scopes" :key="scope.variablesReference" class="scope">
                <div class="scope-name">{{ scope.name }}</div>
                <DebugVarTree
                  :variables="debug.variablesByRef[scope.variablesReference] || []"
                  :parent-ref="scope.variablesReference"
                />
              </div>
              <p v-if="!debug.scopes.length" class="empty">{{ t('debug.noVariables') }}</p>
            </div>
          </section>
        </div>
      </div>
    </template>

    <div v-if="conditionPath" class="modal">
      <div class="card">
        <h3>{{ t('debug.conditionTitle') }}</h3>
        <p class="meta">{{ conditionPath }}:{{ conditionLine }}</p>
        <input v-model="conditionText" :placeholder="t('debug.conditionPlaceholder')" />
        <div class="row end">
          <button type="button" class="btn" @click="conditionPath = null">{{ t('common.cancel') }}</button>
          <button type="button" class="btn btn-primary" @click="saveCondition">{{ t('common.save') }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.debug-panel {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--panel-bg);
  color: var(--text);
  font-size: 12.5px;
}
.session-tabs {
  display: flex;
  gap: 0;
  align-items: stretch;
  min-height: 32px;
  overflow-x: auto;
  border-bottom: 1px solid var(--border);
  background: color-mix(in srgb, var(--bg) 70%, var(--panel-bg));
}
.session-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 160px;
  height: 32px;
  padding: 0 8px 0 12px;
  border: 0;
  border-right: 1px solid var(--border);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  flex-shrink: 0;
}
.session-tab:hover {
  background: color-mix(in srgb, var(--text-h) 6%, transparent);
  color: var(--text-h);
}
.session-tab.active {
  background: var(--panel-bg);
  color: var(--text-h);
  box-shadow: inset 0 -2px 0 var(--primary);
}
.session-tab[data-state='paused'] .session-tab-title {
  color: #eab308;
}
.session-tab[data-state='error'] .session-tab-title {
  color: #f14c4c;
}
.session-tab[data-state='terminated'] .session-tab-title,
.session-tab[data-state='stopped'] .session-tab-title {
  color: var(--text-secondary);
  opacity: 0.85;
}
.session-tab-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
}
.session-tab-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 4px;
  opacity: 0.55;
  flex-shrink: 0;
}
.session-tab-close:hover {
  opacity: 1;
  background: color-mix(in srgb, var(--text-h) 12%, transparent);
}
.toolbar {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 6px 10px;
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
}
.actions {
  display: flex;
  gap: 1px;
  align-items: center;
  flex-shrink: 0;
}
.empty-sessions {
  margin: 0;
  padding: 16px 12px;
  color: var(--text-secondary);
}
.dbg-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: color-mix(in srgb, var(--text-h) 88%, transparent);
  cursor: pointer;
  transition: background 0.12s ease, color 0.12s ease;
}
.dbg-btn:hover:not(:disabled) {
  background: color-mix(in srgb, var(--text-h) 12%, transparent);
}
.dbg-btn.active {
  color: var(--primary);
  background: color-mix(in srgb, var(--primary) 14%, transparent);
}
.dbg-btn:disabled {
  opacity: 0.32;
  cursor: not-allowed;
}
.dbg-btn--tiny {
  width: 22px;
  height: 22px;
}
.dbg-btn--continue {
  color: #89d185;
}
.dbg-btn--stop {
  color: #f14c4c;
}
.dbg-btn--restart {
  color: inherit;
}
.dbg-sep {
  width: 1px;
  height: 16px;
  margin: 0 4px;
  background: color-mix(in srgb, var(--text-h) 18%, transparent);
}
.status-inline {
  display: flex;
  gap: 8px;
  align-items: center;
  margin: 0;
  min-width: 0;
  flex: 1;
}
.err {
  color: #dc2626;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.side-drawer {
  display: flex;
  flex-direction: column;
  max-height: 38%;
  min-height: 96px;
  border-bottom: 1px solid var(--border);
  background: color-mix(in srgb, var(--bg) 55%, var(--panel-bg));
}
.side-drawer-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 10px 0;
}
.side-drawer-head h3 {
  margin: 0;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.side-drawer-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 6px 10px 10px;
}
.debug-split {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  overflow: hidden;
}
.debug-col {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}
.debug-col--left {
  border-right: 1px solid var(--border);
}
.block {
  padding: 8px 10px;
  min-height: 0;
}
.block.grow {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
h3 {
  margin: 0 0 6px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.vars-scroll {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 4px 2px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--debug-vars-bg);
}
.scope + .scope {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--border);
}
.list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.list li {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 4px 6px;
  border-radius: 6px;
  cursor: pointer;
}
.list li:hover,
.list li.active {
  background: color-mix(in srgb, var(--primary) 10%, transparent);
}
.name {
  color: var(--text-h);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.meta {
  color: var(--text-secondary);
  font-size: 11px;
}
.empty {
  margin: 0;
  color: var(--text-secondary);
}
.scope-name {
  font-weight: 600;
  margin: 2px 6px 4px;
  padding: 2px 4px;
  font-size: 11px;
  letter-spacing: 0.02em;
  color: var(--text-secondary);
  text-transform: uppercase;
}
.row {
  display: flex;
  gap: 6px;
  margin-top: 6px;
}
.row.end {
  justify-content: flex-end;
}
.row input {
  flex: 1;
  min-width: 0;
  height: 28px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--text-h);
  padding: 0 8px;
}
.check {
  display: flex;
  gap: 6px;
  align-items: center;
  margin: 4px 0;
}
.console {
  flex: 1;
  min-height: 80px;
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
  background: var(--editor-bg);
  font-family: var(--mono);
  font-size: 12px;
  cursor: text;
}
.console-input-row {
  display: flex;
  align-items: center;
  gap: 4px;
  min-height: 18px;
  margin-top: 2px;
}
.console-prompt {
  flex-shrink: 0;
  color: var(--primary);
  line-height: 1;
}
.console-input {
  flex: 1;
  min-width: 0;
  border: 0;
  outline: none;
  background: transparent;
  color: var(--text-h);
  font: inherit;
  padding: 0;
  height: 18px;
}
.console-input:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.console-input::placeholder {
  color: var(--text-secondary);
  opacity: 0.7;
}
.cline.err {
  color: #dc2626;
}
.cline.in {
  color: var(--primary);
}
.cline.stdout {
  color: var(--text-h);
}
.cline.out {
  color: var(--text);
}
.link {
  border: 0;
  background: transparent;
  color: var(--text-h);
  cursor: pointer;
  padding: 0;
  text-align: left;
}
.link.dim {
  color: var(--text-secondary);
  font-size: 11px;
}
.modal {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, #000 35%, transparent);
  z-index: 5;
}
.card {
  width: min(360px, 92%);
  background: var(--panel-bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.card input {
  height: 30px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--text-h);
  padding: 0 8px;
}
</style>
