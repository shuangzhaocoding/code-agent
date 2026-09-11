<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useAppStore } from '@/stores/app'
import WorkspacePicker from '@/components/WorkspacePicker.vue'
import Workbench from '@/layouts/Workbench.vue'
import ImageLightboxHost from '@/components/ImageLightboxHost.vue'
import { applyWindowTitle, formatWindowTitle } from '@/utils/windowTitle'

const store = useAppStore()

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

onMounted(async () => {
  await store.loadWorkspaces()
  if (store.workspaceId) {
    await store.selectWorkspace(store.workspaceId, { openExplorer: false })
  }
})
</script>

<template>
  <WorkspacePicker v-if="!store.workspaceId" />
  <Workbench v-else />
  <ImageLightboxHost />
</template>
