<script setup>
import { ref } from 'vue'
import { api } from '../api.js'

const props = defineProps({
  image: { type: Object, required: true },
})
const emit = defineEmits(['close', 'deleted', 'reuse', 'error'])

const confirmDelete = ref(false)
const deleting = ref(false)

async function doDelete() {
  deleting.value = true
  try {
    await api.remove(props.image.id)
    emit('deleted', props.image.id)
  } catch (e) {
    emit('error', `Delete failed: ${e.message}`)
    confirmDelete.value = false
  } finally {
    deleting.value = false
  }
}

function onBackdrop(e) {
  if (e.target === e.currentTarget) emit('close')
}
</script>

<template>
  <div class="modal-backdrop" @click="onBackdrop">
    <div class="modal">
      <img :src="api.fileUrl(image.id)" :alt="image.user_prompt" />

      <div class="actions" style="margin-top: 16px">
        <a class="" :href="api.fileUrl(image.id, true)" download>
          <button type="button">Download</button>
        </a>
        <button type="button" class="secondary" @click="emit('reuse', image)">
          Reuse prompt
        </button>
        <button type="button" class="danger" @click="confirmDelete = true">
          Delete
        </button>
        <button type="button" style="margin-left: auto" @click="emit('close')">Close</button>
      </div>

      <dl class="meta">
        <dt>Style</dt><dd>{{ image.style }}</dd>
        <dt>Size</dt><dd>{{ image.width }} × {{ image.height }}</dd>
        <dt>Seed</dt><dd>{{ image.seed != null ? image.seed : '—' }}</dd>
        <dt>Model</dt><dd>{{ image.model }}</dd>
        <dt>Created</dt><dd>{{ image.created_at }}</dd>
        <dt>Your prompt</dt><dd>{{ image.user_prompt }}</dd>
        <dt v-if="image.negative_prompt">Negative</dt>
        <dd v-if="image.negative_prompt">{{ image.negative_prompt }}</dd>
        <dt>Full prompt sent</dt><dd style="font-family: ui-monospace, monospace; font-size: 12px;">{{ image.full_prompt }}</dd>
      </dl>
    </div>

    <!-- Confirm-delete modal -->
    <div v-if="confirmDelete" class="modal-backdrop" @click.self="confirmDelete = false">
      <div class="modal" style="max-width: 380px">
        <h2 style="margin-bottom: 8px; color: var(--text); text-transform: none; letter-spacing: 0; font-size: 16px;">Delete this image?</h2>
        <p style="color: var(--muted); margin: 0 0 16px 0;">This removes the file from disk. Cannot be undone.</p>
        <div class="actions">
          <button type="button" @click="confirmDelete = false" :disabled="deleting">Cancel</button>
          <button type="button" class="danger" @click="doDelete" :disabled="deleting">
            <span v-if="deleting" class="spinner" />
            {{ deleting ? 'Deleting...' : 'Delete' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
