<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { TrSender } from '@opentiny/tiny-robot'
import { useAppStore } from '@/stores/app'
import { rendererFor } from '@/renderers'
import type { Block } from '@/protocol/applyEvent'
import AppIcon from '@/components/AppIcon.vue'

const store = useAppStore()
const scroller = ref<HTMLElement | null>(null)
const timelineInner = ref<HTMLElement | null>(null)
const sender = ref<{ clear: () => void; setContent: (content: string) => void } | null>(null)
const draft = ref('')
const stick = ref(true)
let locking = false
let raf = 0
let followGen = 0
let resizeObs: ResizeObserver | null = null
const models = computed(() => store.providers.flatMap((p) => (p.models || []).map((m: any) => ({ ...m, provider: p.name }))))
const streamTick = computed(() =>
  store.messages.map((m) => m.blocks.map((b) => `${b.id}:${b.text?.length || 0}:${b.status}`).join('|')).join('/'),
)

function running() {
  return store.runStatus === 'running' || store.runStatus === 'queued'
}

function distanceToBottom(el: HTMLElement) {
  return el.scrollHeight - el.scrollTop - el.clientHeight
}

function pauseFollow() {
  stick.value = false
  followGen += 1
  if (raf) {
    cancelAnimationFrame(raf)
    raf = 0
  }
}

function jumpToEnd() {
  if (!stick.value) return
  const el = scroller.value
  if (!el) return
  const token = followGen
  const top = Math.max(0, el.scrollHeight - el.clientHeight)
  if (Math.abs(el.scrollTop - top) < 2) return
  locking = true
  el.scrollTop = top
  requestAnimationFrame(() => {
    if (token !== followGen || !stick.value) {
      locking = false
      return
    }
    el.scrollTop = el.scrollHeight
    requestAnimationFrame(() => {
      locking = false
    })
  })
}

function scrollToEnd() {
  if (!stick.value) return
  jumpToEnd()
}

function onScroll() {
  if (locking) return
  const el = scroller.value
  if (!el) return
  if (distanceToBottom(el) > 16) pauseFollow()
  else stick.value = true
}

function onWheel(e: WheelEvent) {
  if (e.deltaY < 0) pauseFollow()
}

function onPointerDown(e: PointerEvent) {
  const el = scroller.value
  if (!el) return
  if (e.offsetX >= el.clientWidth - 18) pauseFollow()
}

function followOutput() {
  if (!stick.value) return
  if (raf) return
  raf = requestAnimationFrame(() => {
    raf = 0
    if (!stick.value) return
    scrollToEnd()
  })
}

onMounted(() => {
  if (timelineInner.value) {
    resizeObs = new ResizeObserver(() => followOutput())
    resizeObs.observe(timelineInner.value)
  }
  followOutput()
})

onBeforeUnmount(() => {
  resizeObs?.disconnect()
  resizeObs = null
  if (raf) cancelAnimationFrame(raf)
})

watch(
  () => store.conversationId,
  async () => {
    stick.value = true
    await nextTick()
    jumpToEnd()
    requestAnimationFrame(jumpToEnd)
  },
)

watch(
  () => [store.conversationId, store.messages.length, store.runStatus, streamTick.value] as const,
  async () => {
    await nextTick()
    followOutput()
  },
)

function clearSender() {
  draft.value = ''
  sender.value?.clear?.()
  sender.value?.setContent?.('')
}

function onSubmit(text: string) {
  const value = text?.trim()
  if (!value) return
  stick.value = true
  const refs = store.openFile ? [{ type: 'file', path: store.openFile.path }] : []
  store.send(value, refs)
  clearSender()
  nextTick(() => {
    clearSender()
    scrollToEnd()
  })
}

function toggleThinking() {
  store.thinking = !store.thinking
}
</script>

<template>
  <div class="panel-shell agent">
    <header class="panel-head">
      <select v-model="store.mode" class="field-control">
        <option value="ask">Ask</option>
        <option value="agent">Agent</option>
        <option value="plan">Plan</option>
      </select>
      <select v-model="store.modelId" class="field-control grow">
        <option :value="null">选择模型</option>
        <option v-for="m in models" :key="m.id" :value="m.id">{{ m.display_name }}</option>
      </select>
      <button
        type="button"
        class="think-btn"
        :class="{ on: store.thinking }"
        :title="store.thinking ? '深度思考：开' : '深度思考：关'"
        @click="toggleThinking"
      >
        <AppIcon name="think" :size="15" />
        思考
      </button>
      <span class="spacer" />
      <button v-if="running()" type="button" class="btn" @click="store.stop()">停止</button>
      <button type="button" class="btn btn-primary" @click="store.newChat()">新会话</button>
    </header>
    <div ref="scroller" class="timeline" @scroll="onScroll" @wheel="onWheel" @pointerdown="onPointerDown">
      <div ref="timelineInner" class="timeline-inner">
        <div v-if="!store.messages.length" class="empty">
          描述你想改的代码。可用 Skill、自备模型，刷新后生成会继续。
        </div>
        <article v-for="msg in store.messages" :key="msg.id" :class="msg.role">
          <section v-for="block in msg.blocks" :key="block.id" class="block">
            <component :is="rendererFor(block.type)" :block="block as Block" />
          </section>
        </article>
        <div v-if="running()" class="typing" aria-hidden="true">
          <span class="dots"><i /><i /><i /></span>
        </div>
      </div>
    </div>
    <footer>
      <TrSender
        ref="sender"
        v-model="draft"
        class="sender"
        placeholder="给 Code Agent 下指令…"
        :loading="running()"
        @submit="onSubmit"
      />
    </footer>
  </div>
</template>

<style scoped>
.agent { background: var(--bg); }
.panel-head { flex-wrap: wrap; }
.field-control {
  height: 28px;
  padding: 0 8px;
  font-size: 12px;
}
.grow { min-width: 0; max-width: 180px; }
.btn { height: 28px; padding: 0 10px; font-size: 12px; }
.think-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 28px;
  padding: 0 8px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-elevated);
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 12px;
  flex-shrink: 0;
}
.think-btn:hover { color: var(--text); }
.think-btn.on {
  color: var(--primary);
  border-color: color-mix(in srgb, var(--primary) 45%, var(--border));
  background: var(--primary-soft);
}
.timeline {
  flex: 1;
  overflow-x: hidden;
  overflow-y: scroll;
  overflow-anchor: none;
  padding: 14px 16px 24px;
}
.timeline-inner {
  display: flex;
  flex-direction: column;
  min-height: min-content;
}
.empty {
  color: var(--text-secondary);
  padding: 32px 8px;
  text-align: center;
  line-height: 1.6;
}
article.user {
  align-self: flex-end;
  max-width: min(82%, 560px);
  width: fit-content;
  margin: 10px 0 10px 40px;
  background: var(--primary-soft);
  color: var(--text);
  padding: 10px 14px;
  border-radius: 12px 12px 4px 12px;
  overflow-anchor: none;
}
article.assistant {
  align-self: stretch;
  margin: 10px 28px 10px 0;
  overflow-anchor: none;
}
.block + .block { margin-top: 4px; }
.typing {
  display: flex;
  align-items: center;
  min-height: 28px;
  padding: 4px 2px 8px;
  color: var(--text-muted);
}
.dots {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.dots i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--primary);
  animation: typing 1.05s ease-in-out infinite;
}
.dots i:nth-child(2) { animation-delay: 0.15s; }
.dots i:nth-child(3) { animation-delay: 0.3s; }
@keyframes typing {
  0%, 80%, 100% { opacity: 0.25; }
  40% { opacity: 1; }
}
footer {
  border-top: 1px solid var(--border);
  padding: 10px;
  background: var(--bg-elevated);
}
</style>
