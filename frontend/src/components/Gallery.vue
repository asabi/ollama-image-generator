<script setup>
import { api } from '../api.js'

defineProps({
  images: { type: Array, required: true },
})
const emit = defineEmits(['open'])
</script>

<template>
  <div class="panel">
    <h2>Gallery ({{ images.length }})</h2>
    <div v-if="!images.length" class="empty">No images yet. Generate one above.</div>
    <div v-else class="gallery">
      <div
        v-for="img in images"
        :key="img.id"
        class="thumb"
        :title="img.user_prompt"
        @click="emit('open', img)"
      >
        <img :src="api.thumbUrl(img.id)" :alt="img.user_prompt" loading="lazy" />
      </div>
    </div>
  </div>
</template>
