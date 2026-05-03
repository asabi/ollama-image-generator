<script setup>
import { ref, computed } from 'vue'
import { api } from '../api.js'

const props = defineProps({
  label: { type: String, required: true },
  models: { type: Array, required: true },     // [{name, installed, parameter_size, quantization_level}, ...]
  modelValue: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue', 'pulled', 'error'])

const pulling = ref(false)
const pullStatus = ref('')          // current status string from ollama
const pullPercent = ref(0)          // 0-100 for the active layer
const pullLayerIndex = ref(0)       // how many layer/manifest events we've seen

const selected = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const selectedInfo = computed(() =>
  props.models.find((m) => m.name === selected.value),
)

function fmtMeta(m) {
  const bits = []
  if (m.parameter_size) bits.push(m.parameter_size)
  if (m.quantization_level) bits.push(m.quantization_level)
  return bits.length ? ` (${bits.join(', ')})` : ''
}

function optionLabel(m) {
  return m.installed
    ? `${m.name}${fmtMeta(m)}`
    : `${m.name} — not installed`
}

async function onPull() {
  if (!selected.value) return
  pulling.value = true
  pullStatus.value = 'starting…'
  pullPercent.value = 0
  pullLayerIndex.value = 0
  try {
    await api.pullStream(selected.value, (ev) => {
      if (ev.error) throw new Error(ev.error)
      const status = ev.status || ''
      pullStatus.value = status
      if (status.startsWith('pulling ') && status !== 'pulling manifest') {
        // new layer started
        pullLayerIndex.value++
      }
      if (typeof ev.total === 'number' && typeof ev.completed === 'number' && ev.total > 0) {
        pullPercent.value = Math.round((ev.completed / ev.total) * 100)
      } else if (status === 'success') {
        pullPercent.value = 100
      }
    })
    emit('pulled', selected.value)
  } catch (e) {
    emit('error', `Pull failed: ${e.message}`)
  } finally {
    pulling.value = false
  }
}
</script>

<template>
  <div>
    <label>{{ label }}</label>
    <select v-model="selected" :disabled="pulling">
      <option v-for="m in models" :key="m.name" :value="m.name">{{ optionLabel(m) }}</option>
    </select>

    <div v-if="selectedInfo && !selectedInfo.installed && !pulling" class="not-installed">
      <span>This model isn't installed on the Ollama server.</span>
      <button type="button" class="secondary" @click="onPull">⤓ Pull it now</button>
    </div>

    <div v-if="pulling" class="pull-progress">
      <div class="pull-status">
        Pulling <strong>{{ selected }}</strong> — {{ pullStatus || '…' }}
        <span v-if="pullLayerIndex > 0" style="color: var(--muted)"> (layer {{ pullLayerIndex }})</span>
      </div>
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: pullPercent + '%' }" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.not-installed {
  margin-top: 8px;
  padding: 10px 12px;
  background: rgba(139, 111, 255, 0.08);
  border: 1px solid rgba(139, 111, 255, 0.4);
  border-radius: 8px;
  color: var(--text);
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.not-installed button { padding: 6px 12px; }

.pull-progress {
  margin-top: 8px;
  padding: 10px 12px;
  background: var(--panel-2);
  border: 1px solid var(--border);
  border-radius: 8px;
}
.pull-status {
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 6px;
  letter-spacing: 0.02em;
}
.pull-status strong { color: var(--text); }
.progress-bar {
  height: 8px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 4px;
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--accent-2), var(--accent));
  transition: width 0.25s ease;
}
</style>
