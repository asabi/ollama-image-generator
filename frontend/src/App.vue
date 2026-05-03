<script setup>
import { ref, onMounted } from 'vue'
import { api } from './api.js'
import GenerateForm from './components/GenerateForm.vue'
import Gallery from './components/Gallery.vue'
import ImageModal from './components/ImageModal.vue'

const images = ref([])
const open = ref(null)
const toast = ref(null)
const formRef = ref(null)

function showToast(message, kind = 'info') {
  toast.value = { message, kind }
  setTimeout(() => { if (toast.value && toast.value.message === message) toast.value = null }, 4000)
}

async function refresh() {
  try {
    images.value = await api.list()
  } catch (e) {
    showToast(`Failed to load gallery: ${e.message}`, 'error')
  }
}
onMounted(refresh)

// One image at a time as the form streams them in.
function onImageAdded(img) {
  images.value = [img, ...images.value]
}

function onOpen(img) { open.value = img }
function onClose() { open.value = null }
function onDeleted(id) {
  images.value = images.value.filter((i) => i.id !== id)
  open.value = null
  showToast('Image deleted')
}
function onReuse(img) {
  formRef.value?.loadFrom(img)
  open.value = null
  showToast('Loaded prompt into the form')
  window.scrollTo({ top: 0, behavior: 'smooth' })
}
</script>

<template>
  <h1>Local Image Studio</h1>
  <GenerateForm
    ref="formRef"
    @image-added="onImageAdded"
    @error="(m) => showToast(m, 'error')"
    @info="(m) => showToast(m)"
  />
  <Gallery :images="images" @open="onOpen" />
  <ImageModal
    v-if="open"
    :image="open"
    @close="onClose"
    @deleted="onDeleted"
    @reuse="onReuse"
    @error="(m) => showToast(m, 'error')"
  />

  <div v-if="toast" :class="['toast', toast.kind === 'error' ? 'error' : '']">
    {{ toast.message }}
  </div>
</template>
