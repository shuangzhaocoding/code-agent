<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppIcon from '@/components/AppIcon.vue'
import ContextMenu, { type ContextMenuItem } from '@/components/ContextMenu.vue'
import { useDebugStore, type DebugVariable } from '@/stores/debug'

const props = defineProps<{
  variables: DebugVariable[]
  /** Parent DAP variablesReference (needed for setVariable). */
  parentRef?: number
  /** Expression prefix for watch / evaluate (e.g. `obj` → `obj.foo`). */
  expressionPrefix?: string
  depth?: number
}>()

const { t } = useI18n()
const debug = useDebugStore()
const expanded = ref<Record<string, boolean>>({})
const loading = ref<Record<string, boolean>>({})
const selectedKey = ref<string | null>(null)
const ctxMenu = ref<{ x: number; y: number; variable: DebugVariable; index: number } | null>(null)
const editing = ref<{ key: string; variable: DebugVariable; value: string } | null>(null)
const editInput = ref<HTMLInputElement | null>(null)
const setError = ref<string | null>(null)
let committing = false

const depth = computed(() => props.depth ?? 0)
const parentRef = computed(() => props.parentRef ?? 0)
const expressionPrefix = computed(() => props.expressionPrefix ?? '')

function rowKey(v: DebugVariable, index: number) {
  return `${depth.value}:${v.name}:${v.variablesReference || 0}:${index}`
}

function isExpandable(v: DebugVariable) {
  return Boolean(v.variablesReference && v.variablesReference > 0)
}

function isIndexName(name: string) {
  return /^\d+$/.test(name)
}

/** Synthetic debugpy groups — show name only, no trailing " = ". */
function isGroupLabel(name: string) {
  const n = name.trim().toLowerCase()
  return n === 'special variables' || n === 'function variables'
}

function showEquals(v: DebugVariable) {
  if (isGroupLabel(v.name || '')) return false
  const hasType = Boolean(typeBadge(v))
  const hasValue = v.value != null && v.value !== ''
  return hasType || hasValue
}

function typeBadge(v: DebugVariable): string {
  const typ = (v.type || '').trim()
  if (!typ) return ''
  const indexed = typeof v.indexedVariables === 'number' ? v.indexedVariables : null
  const named = typeof v.namedVariables === 'number' ? v.namedVariables : null
  if (indexed != null && indexed > 0) return `{${typ}: ${indexed}}`
  if (named != null && named > 0 && !indexed) return `{${typ}: ${named}}`
  // Fallback: list/dict/tuple size from value preview like "[1, 2, 3]" / "{...}"
  if (/^(list|tuple|dict|set|frozenset)$/i.test(typ) && v.value) {
    const m = v.value.match(/^(?:\[|\{|\().*(?:\]|\}|\))\s*$/)
    if (m) {
      // Prefer DAP length when present later; rough count for display only when small preview
      const lenMatch = v.value.match(/^\[(.*)\]$/)
      if (lenMatch && !v.value.includes('...')) {
        const inner = lenMatch[1].trim()
        const count = inner ? inner.split(',').length : 0
        return `{${typ}: ${count}}`
      }
    }
  }
  return `{${typ}}`
}

function childExpression(parentExpr: string, name: string): string {
  if (!parentExpr) return name
  if (isIndexName(name)) return `${parentExpr}[${name}]`
  if (/^[A-Za-z_][\w]*$/.test(name)) return `${parentExpr}.${name}`
  return `${parentExpr}[${JSON.stringify(name)}]`
}

function expressionFor(v: DebugVariable): string {
  if (isGroupLabel(v.name || '')) return ''
  return childExpression(expressionPrefix.value, v.name)
}

function isReadOnly(v: DebugVariable): boolean {
  const attrs = v.presentationHint?.attributes
  return Boolean(attrs?.includes('readOnly') || attrs?.includes('constant'))
}

function canSetValue(v: DebugVariable): boolean {
  return (
    debug.paused &&
    parentRef.value > 0 &&
    !isGroupLabel(v.name || '') &&
    !isReadOnly(v)
  )
}

async function toggle(v: DebugVariable, index: number) {
  if (!isExpandable(v)) return
  const key = rowKey(v, index)
  const next = !expanded.value[key]
  expanded.value = { ...expanded.value, [key]: next }
  selectedKey.value = key
  if (!next) return
  const ref = v.variablesReference!
  if (debug.variablesByRef[ref]) return
  loading.value = { ...loading.value, [key]: true }
  try {
    await debug.loadVariables(ref)
  } finally {
    loading.value = { ...loading.value, [key]: false }
  }
}

function select(v: DebugVariable, index: number) {
  selectedKey.value = rowKey(v, index)
}

async function onRowClick(v: DebugVariable, index: number) {
  if (editing.value) return
  select(v, index)
  if (isExpandable(v)) await toggle(v, index)
}

function onContextMenu(e: MouseEvent, v: DebugVariable, index: number) {
  e.preventDefault()
  e.stopPropagation()
  select(v, index)
  ctxMenu.value = { x: e.clientX, y: e.clientY, variable: v, index }
}

async function copyText(text: string) {
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    /* clipboard denied */
  }
}

const ctxMenuItems = computed((): ContextMenuItem[] => {
  const v = ctxMenu.value?.variable
  if (!v) return []
  const group = isGroupLabel(v.name || '')
  const hasValue = v.value != null && v.value !== ''
  const expr = expressionFor(v)
  return [
    {
      id: 'copy-value',
      label: t('debug.copyValue'),
      icon: 'copy',
      disabled: group || !hasValue,
    },
    {
      id: 'copy-name',
      label: t('debug.copyName'),
      icon: 'path-relative',
      disabled: !v.name,
    },
    {
      id: 'copy-as-expr',
      label: t('debug.copyExpression'),
      icon: 'path-absolute',
      disabled: !expr,
    },
    {
      id: 'copy-assignment',
      label: t('debug.copyAssignment'),
      icon: 'file',
      disabled: group || !hasValue,
    },
    { id: 'sep-1', separator: true },
    {
      id: 'add-watch',
      label: t('debug.addToWatch'),
      icon: 'eye',
      disabled: !expr || !debug.paused,
    },
    {
      id: 'evaluate',
      label: t('debug.evaluateInConsole'),
      icon: 'terminal',
      disabled: !expr || !debug.paused,
    },
    { id: 'sep-2', separator: true },
    {
      id: 'set-value',
      label: t('debug.setValue'),
      icon: 'edit',
      disabled: !canSetValue(v),
    },
  ]
})

async function onCtxSelect(id: string) {
  const ctx = ctxMenu.value
  if (!ctx) return
  const v = ctx.variable
  const expr = expressionFor(v)
  if (id === 'copy-value') {
    await copyText(v.value ?? '')
    return
  }
  if (id === 'copy-name') {
    await copyText(v.name || '')
    return
  }
  if (id === 'copy-as-expr') {
    await copyText(expr)
    return
  }
  if (id === 'copy-assignment') {
    await copyText(`${v.name} = ${v.value ?? ''}`)
    return
  }
  if (id === 'add-watch' && expr) {
    debug.addWatch(expr)
    return
  }
  if (id === 'evaluate' && expr) {
    void debug.evaluate(expr)
    return
  }
  if (id === 'set-value') {
    startEdit(v, ctx.index)
  }
}

async function startEdit(v: DebugVariable, index: number) {
  if (!canSetValue(v)) return
  setError.value = null
  editing.value = {
    key: rowKey(v, index),
    variable: v,
    value: v.value ?? '',
  }
  await nextTick()
  editInput.value?.focus()
  editInput.value?.select()
}

function cancelEdit() {
  editing.value = null
  setError.value = null
}

async function commitEdit() {
  if (committing) return
  const ed = editing.value
  if (!ed) return
  committing = true
  try {
    const result = await debug.setVariable(parentRef.value, ed.variable.name, ed.value)
    if (!result.ok) {
      setError.value = result.error
      await nextTick()
      editInput.value?.focus()
      return
    }
    editing.value = null
    setError.value = null
  } finally {
    committing = false
  }
}

function onEditKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    e.preventDefault()
    cancelEdit()
    return
  }
  if (e.key === 'Enter') {
    e.preventDefault()
    void commitEdit()
  }
}

function bindEditInput(el: unknown) {
  editInput.value = (el as HTMLInputElement | null) || null
}

watch(
  () => props.variables,
  () => {
    expanded.value = {}
    selectedKey.value = null
    editing.value = null
    setError.value = null
    ctxMenu.value = null
  },
)
</script>

<template>
  <ul class="var-tree" :style="{ '--var-depth': depth }">
    <li v-for="(v, index) in variables" :key="rowKey(v, index)" class="var-node">
      <div
        class="var-row"
        role="button"
        tabindex="0"
        :class="{
          selected: selectedKey === rowKey(v, index),
          expandable: isExpandable(v),
          editing: editing?.key === rowKey(v, index),
        }"
        :style="{ paddingLeft: `${8 + depth * 14}px` }"
        @click="onRowClick(v, index)"
        @contextmenu="onContextMenu($event, v, index)"
        @dblclick.stop="startEdit(v, index)"
      >
        <span
          class="twist"
          :class="{ open: expanded[rowKey(v, index)], hidden: !isExpandable(v) }"
          @click.stop="toggle(v, index)"
        >
          <AppIcon
            :name="expanded[rowKey(v, index)] ? 'chevron-down' : 'chevron-right'"
            :size="12"
            :stroke-width="2"
          />
        </span>
        <template v-if="editing?.key === rowKey(v, index)">
          <span class="vname" :class="{ index: isIndexName(v.name), group: isGroupLabel(v.name) }">{{
            v.name
          }}</span>
          <span class="veq"> = </span>
          <input
            :ref="bindEditInput"
            v-model="editing.value"
            class="var-edit"
            spellcheck="false"
            :aria-label="t('debug.setValue')"
            @click.stop
            @keydown="onEditKeydown"
            @blur="commitEdit"
          />
        </template>
        <span
          v-else
          class="var-line"
          :title="showEquals(v) ? `${v.name} = ${v.value ?? ''}` : v.name"
        >
          <span class="vname" :class="{ index: isIndexName(v.name), group: isGroupLabel(v.name) }">{{
            v.name
          }}</span>
          <template v-if="showEquals(v)">
            <span class="veq"> = </span>
            <span v-if="typeBadge(v)" class="vtype">{{ typeBadge(v) }}</span>
            <span v-if="v.value != null && v.value !== ''" class="vval"> {{ v.value }}</span>
          </template>
        </span>
      </div>
      <p v-if="editing?.key === rowKey(v, index) && setError" class="var-error">{{ setError }}</p>
      <p v-if="expanded[rowKey(v, index)] && loading[rowKey(v, index)]" class="var-loading">…</p>
      <DebugVarTree
        v-else-if="expanded[rowKey(v, index)] && v.variablesReference"
        :variables="debug.variablesByRef[v.variablesReference] || []"
        :parent-ref="v.variablesReference"
        :expression-prefix="
          isGroupLabel(v.name) ? expressionPrefix : childExpression(expressionPrefix, v.name)
        "
        :depth="depth + 1"
      />
    </li>
  </ul>

  <ContextMenu
    v-if="ctxMenu"
    :x="ctxMenu.x"
    :y="ctxMenu.y"
    :items="ctxMenuItems"
    @select="onCtxSelect"
    @close="ctxMenu = null"
  />
</template>

<script lang="ts">
export default {
  name: 'DebugVarTree',
}
</script>

<style scoped>
.var-tree {
  list-style: none;
  margin: 0;
  padding: 0;
  font-family: var(--mono);
  font-size: 12px;
  line-height: 1.45;
  color: var(--text);
}
.var-node {
  min-width: 0;
}
.var-row {
  display: flex;
  align-items: center;
  gap: 2px;
  width: 100%;
  min-height: 22px;
  margin: 0;
  padding: 1px 8px 1px 8px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: var(--text);
  text-align: left;
  cursor: default;
  box-sizing: border-box;
  outline: none;
  transition: background 0.12s ease;
}
.var-row:hover {
  background: var(--debug-var-row-hover);
}
.var-row.selected {
  background: var(--debug-var-row-selected);
}
.var-row.editing {
  background: var(--debug-var-row-selected);
}
.twist {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  color: var(--text-muted);
  cursor: pointer;
  border-radius: 3px;
}
.twist.hidden {
  visibility: hidden;
  pointer-events: none;
}
.twist:hover:not(.hidden) {
  color: var(--text-h);
  background: color-mix(in srgb, var(--text-h) 8%, transparent);
}
.var-line {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.vname {
  color: var(--debug-var-name);
  font-weight: 500;
  flex-shrink: 0;
}
.vname.index {
  color: var(--debug-var-index);
}
.vname.group {
  color: var(--text-secondary);
  font-weight: 600;
}
.veq {
  color: var(--debug-var-eq);
  flex-shrink: 0;
}
.vtype {
  color: var(--debug-var-type);
}
.vval {
  color: var(--debug-var-value);
}
.var-edit {
  flex: 1;
  min-width: 0;
  height: 20px;
  margin: 0;
  padding: 0 6px;
  border: 1px solid var(--accent, #3b82f6);
  border-radius: 3px;
  background: var(--bg);
  color: var(--debug-var-value);
  font: inherit;
  outline: none;
}
.var-error {
  margin: 0;
  padding: 0 8px 4px 36px;
  color: var(--danger);
  font-size: 11px;
}
.var-loading {
  margin: 0;
  padding: 2px 8px 2px 36px;
  color: var(--text-secondary);
  font-size: 11px;
}
</style>
