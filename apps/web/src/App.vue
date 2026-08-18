<script setup lang="ts">
import { onMounted } from 'vue'
import { useAppStore } from '@/stores/app'
import WorkspacePicker from '@/components/WorkspacePicker.vue'
import Workbench from '@/layouts/Workbench.vue'

const store = useAppStore()
onMounted(async () => {
  await store.loadWorkspaces()
  if (store.workspaceId) {
    await store.selectWorkspace(store.workspaceId)
  }
})
</script>

<template>
  <WorkspacePicker v-if="!store.workspaceId" />
  <Workbench v-else />
</template>
