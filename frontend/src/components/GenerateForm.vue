<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api.js'
import ModelPicker from './ModelPicker.vue'

const emit = defineEmits(['error', 'info', 'image-added'])

const styles = ref([])
const imageModels = ref([])
const textModels = ref([])

const prompt = ref('')
const negative = ref('')
const style = ref('realistic')
const imageModel = ref('')
const textModel = ref('')

const SIZE_PRESETS = [
  { label: '1:1 1024', w: 1024, h: 1024 },
  { label: '16:9 1280', w: 1280, h: 720 },
  { label: '9:16 720', w: 720, h: 1280 },
  { label: '4:5 1024', w: 1024, h: 1280 },
  { label: '3:2 1280', w: 1280, h: 854 },
]
const width = ref(1024)
const height = ref(1024)
const batch = ref(1)
const seed = ref('')

const enhancing = ref(false)
const generating = ref(false)
const progress = ref(null)   // { imageIndex, batchTotal, percent, step, total }

const activePreset = computed(() => {
  const m = SIZE_PRESETS.find((p) => p.w === width.value && p.h === height.value)
  return m ? m.label : null
})

function setPreset(p) {
  width.value = p.w
  height.value = p.h
}

async function reloadModels() {
  const m = await api.models()
  imageModels.value = m.image_models || []
  textModels.value = m.text_models || []
  // Default selection: configured default if it's in the list, otherwise the first
  // installed entry of that kind, otherwise the first entry at all.
  if (!imageModel.value) {
    imageModel.value = pickDefault(imageModels.value, m.default_image_model)
  }
  if (!textModel.value) {
    textModel.value = pickDefault(textModels.value, m.default_text_model)
  }
}

function pickDefault(list, configured) {
  if (configured && list.some((x) => x.name === configured)) return configured
  const installed = list.find((x) => x.installed)
  if (installed) return installed.name
  return list[0]?.name || ''
}

onMounted(async () => {
  try {
    const [s] = await Promise.all([api.styles(), reloadModels()])
    styles.value = s
  } catch (e) {
    emit('error', `Failed to load metadata: ${e.message}`)
  }
})

async function onPulled(pulledName) {
  try {
    await reloadModels()
    emit('info', `Pulled ${pulledName}`)
  } catch (e) {
    emit('error', `Reload after pull failed: ${e.message}`)
  }
}

const imageModelInfo = computed(() =>
  imageModels.value.find((m) => m.name === imageModel.value),
)
const textModelInfo = computed(() =>
  textModels.value.find((m) => m.name === textModel.value),
)
const canEnhance = computed(() => !!textModelInfo.value?.installed)
const canGenerate = computed(() => !!imageModelInfo.value?.installed)

async function onEnhance() {
  if (!prompt.value.trim()) {
    emit('error', 'Enter a prompt before enhancing.')
    return
  }
  if (!canEnhance.value) {
    emit('error', 'The selected text model is not installed. Pull it first.')
    return
  }
  enhancing.value = true
  const original = prompt.value
  let live = ''
  prompt.value = ''
  try {
    await api.enhanceStream(
      { prompt: original, style: style.value, model: textModel.value || null },
      (ev) => {
        if (ev.type === 'chunk') {
          live += ev.text
          prompt.value = live
        } else if (ev.type === 'final') {
          prompt.value = ev.text
          emit('info', `Prompt enhanced via ${ev.model}`)
        } else if (ev.type === 'error') {
          throw new Error(ev.detail)
        }
      },
    )
  } catch (e) {
    prompt.value = original    // restore on failure
    emit('error', `Enhance failed: ${e.message}`)
  } finally {
    enhancing.value = false
  }
}

async function onGenerate() {
  if (!prompt.value.trim()) {
    emit('error', 'Enter a prompt before generating.')
    return
  }
  if (!canGenerate.value) {
    emit('error', 'The selected image model is not installed. Pull it first.')
    return
  }
  let seedNum = null
  if (seed.value !== '' && seed.value !== null) {
    const n = Number(seed.value)
    if (!Number.isInteger(n) || n < 0) {
      emit('error', 'Seed must be a non-negative integer or blank.')
      return
    }
    seedNum = n
  }
  generating.value = true
  progress.value = { imageIndex: 0, batchTotal: batch.value, percent: 0, step: 0, total: 0 }
  let producedCount = 0
  try {
    await api.generateStream(
      {
        prompt: prompt.value,
        style: style.value,
        width: width.value,
        height: height.value,
        negative_prompt: negative.value || null,
        seed: seedNum,
        batch_count: batch.value,
        image_model: imageModel.value || null,
      },
      (ev) => {
        if (ev.type === 'start') {
          progress.value = { imageIndex: 0, batchTotal: ev.batch_count, percent: 0, step: 0, total: 0 }
        } else if (ev.type === 'image_start') {
          progress.value = {
            imageIndex: ev.image_index,
            batchTotal: progress.value.batchTotal,
            percent: 0, step: 0, total: 0,
          }
        } else if (ev.type === 'progress') {
          progress.value = {
            imageIndex: ev.image_index,
            batchTotal: progress.value.batchTotal,
            percent: ev.percent,
            step: ev.step,
            total: ev.total,
          }
        } else if (ev.type === 'image') {
          producedCount++
          emit('image-added', ev.image)
        } else if (ev.type === 'error') {
          throw new Error(ev.detail)
        }
      },
    )
    if (producedCount > 0) {
      emit('info', `Generated ${producedCount} image${producedCount > 1 ? 's' : ''}`)
    }
  } catch (e) {
    emit('error', `Generate failed: ${e.message}`)
  } finally {
    generating.value = false
    progress.value = null
  }
}

function loadFrom(image) {
  prompt.value = image.user_prompt
  negative.value = image.negative_prompt || ''
  if (styles.value.some((s) => s.id === image.style)) style.value = image.style
  width.value = image.width
  height.value = image.height
  seed.value = image.seed != null ? String(image.seed) : ''
}
function randomizeSeed() { seed.value = '' }
defineExpose({ loadFrom })
</script>

<template>
  <div class="panel">
    <h2>Create</h2>

    <div class="row">
      <ModelPicker
        label="Image model"
        v-model="imageModel"
        :models="imageModels"
        @pulled="onPulled"
        @error="(m) => $emit('error', m)"
      />
      <ModelPicker
        label="Text model (for enhance)"
        v-model="textModel"
        :models="textModels"
        @pulled="onPulled"
        @error="(m) => $emit('error', m)"
      />
    </div>

    <div class="row" style="margin-top: 12px">
      <div>
        <label for="style">Style</label>
        <select id="style" v-model="style">
          <option v-for="s in styles" :key="s.id" :value="s.id">{{ s.label }}</option>
        </select>
      </div>
    </div>

    <div style="margin-top: 12px">
      <label for="prompt">
        Prompt
        <span v-if="enhancing" style="text-transform: none; color: var(--accent-2); margin-left: 8px;">
          <span class="spinner" /> streaming from AI…
        </span>
      </label>
      <textarea id="prompt" v-model="prompt" placeholder="A cat astronaut floating above a glowing nebula..." rows="3" />
    </div>

    <div style="margin-top: 12px">
      <label for="negative">Negative prompt (optional)</label>
      <input id="negative" type="text" v-model="negative" placeholder="blurry, low quality, extra limbs..." />
    </div>

    <div class="row" style="margin-top: 12px">
      <div>
        <label>Size</label>
        <div class="preset-row">
          <button
            v-for="p in SIZE_PRESETS"
            :key="p.label"
            type="button"
            :class="{ active: activePreset === p.label }"
            @click="setPreset(p)"
          >{{ p.label }}</button>
        </div>
      </div>
    </div>

    <div class="row" style="margin-top: 8px">
      <div>
        <label for="w">Width</label>
        <input id="w" type="number" v-model.number="width" min="128" max="2048" step="64" />
      </div>
      <div>
        <label for="h">Height</label>
        <input id="h" type="number" v-model.number="height" min="128" max="2048" step="64" />
      </div>
      <div>
        <label for="batch">Batch (N images)</label>
        <input id="batch" type="number" v-model.number="batch" min="1" max="4" step="1" />
      </div>
    </div>

    <div class="row" style="margin-top: 8px">
      <div style="flex: 2 1 320px">
        <label for="seed">Seed (blank = random)</label>
        <input id="seed" type="text" v-model="seed" placeholder="leave blank for random per-image" inputmode="numeric" />
      </div>
      <div style="flex: 0 0 auto; align-self: end">
        <button type="button" @click="randomizeSeed" :disabled="!seed">Clear seed</button>
      </div>
    </div>

    <div class="actions">
      <button type="button" class="secondary" :disabled="enhancing || generating" @click="onEnhance">
        <span v-if="enhancing" class="spinner" />
        {{ enhancing ? 'Enhancing...' : 'Enhance with AI' }}
      </button>
      <button type="button" class="primary" :disabled="generating || enhancing" @click="onGenerate">
        <span v-if="generating" class="spinner" />
        {{ generating ? 'Generating...' : 'Generate' }}
      </button>
    </div>

    <div v-if="progress" class="progress" style="margin-top: 14px">
      <div class="progress-label">
        Image {{ progress.imageIndex + 1 }} of {{ progress.batchTotal }} —
        {{ progress.percent }}%
        <span v-if="progress.total" style="color: var(--muted)">
          ({{ progress.step }}/{{ progress.total }} steps)
        </span>
      </div>
      <div class="progress-bar"><div class="progress-fill" :style="{ width: progress.percent + '%' }" /></div>
    </div>
  </div>
</template>

<style scoped>
.progress-label {
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.progress-bar {
  height: 8px;
  background: var(--panel-2);
  border: 1px solid var(--border);
  border-radius: 4px;
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--accent), var(--accent-2));
  transition: width 0.25s ease;
}
</style>
