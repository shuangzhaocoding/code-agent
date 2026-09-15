<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import AccessGate from '@/components/AccessGate.vue'
import WorkspacePicker from '@/components/WorkspacePicker.vue'
import Workbench from '@/layouts/Workbench.vue'
import ImageLightboxHost from '@/components/ImageLightboxHost.vue'
import AppWallpaper from '@/components/AppWallpaper.vue'
import DesktopPet from '@/components/DesktopPet.vue'
import { useAppStore } from '@/stores/app'
import { useDebugStore } from '@/stores/debug'
import { fetchAuthStatus } from '@/api/http'
import { applyWindowTitle, formatWindowTitle } from '@/utils/windowTitle'

const store = useAppStore()
const bootstrapped = ref(false)
const needsUnlock = ref(false)

const sessionTitle = computed(() => {
  const id = store.conversationId
  if (!id) return null
  return store.conversations.find((c) => c.id === id)?.title || null
})

const workspaceName = computed(() => store.workspace?.name || null)

watch(
  [sessionTitle, workspaceName],
  ([session, workspace]) => {
    applyWindowTitle(formatWindowTitle({ session, workspace }))
  },
  { immediate: true },
)

function onVisibility() {
  if (document.visibilityState === 'visible' && store.workspaceId) {
    void store.refreshWorkspaceStatus()
  }
}

function onAuthRequired() {
  needsUnlock.value = true
}

async function bootstrapApp() {
  await Promise.all([store.loadWorkspaces(), store.loadSettings()])
  if (store.workspaceId) {
    await store.selectWorkspace(store.workspaceId, { openExplorer: false })
    void useDebugStore().hydrateBreakpoints(true)
  }
  bootstrapped.value = true
}

async function checkAuthAndBoot() {
  try {
    const status = await fetchAuthStatus()
    needsUnlock.value = Boolean(status.required && !status.unlocked)
    if (!needsUnlock.value) await bootstrapApp()
  } catch {
    needsUnlock.value = false
    await bootstrapApp()
  }
}

async function onUnlocked() {
  needsUnlock.value = false
  if (!bootstrapped.value) await bootstrapApp()
}

onMounted(async () => {
  document.addEventListener('visibilitychange', onVisibility)
  window.addEventListener('ca-auth-required', onAuthRequired)
  await checkAuthAndBoot()
})

onUnmounted(() => {
  document.removeEventListener('visibilitychange', onVisibility)
  window.removeEventListener('ca-auth-required', onAuthRequired)
  store.stopWorkspaceStatusWatch()
})
</script>

<template>
  <AppWallpaper />
  <AccessGate v-if="needsUnlock" @unlocked="onUnlocked" />
  <template v-else-if="bootstrapped">
    <WorkspacePicker v-if="!store.workspaceId" />
    <Workbench v-else />
    <DesktopPet />
    <ImageLightboxHost />
  </template>
</template>
