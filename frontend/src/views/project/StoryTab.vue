<template>
  <div class="story-tab-content">
    <!-- Top Section: Settings -->
    <el-card class="box-card mb-4" shadow="never">
      <template #header>
        <div class="card-header">
          <span>Project Configuration</span>
          <el-button type="primary" link @click="openGlobalConfig">Advanced Config (JSON)</el-button>
        </div>
      </template>
      <el-form :model="project" label-width="120px" class="settings-form" :inline="true">
        <el-form-item label="Theme">
          <el-input v-model="project.theme" placeholder="e.g. Cyberpunk" @change="saveSettings" class="w-200" />
        </el-form-item>
        <el-form-item label="Language">
          <el-select v-model="project.language" placeholder="Select" @change="saveSettings" class="w-200">
            <el-option label="Simplified Chinese" value="zh-CN" />
            <el-option label="English" value="en-US" />
            <el-option label="Japanese" value="ja-JP" />
            <el-option label="Turkish" value="tr-TR" />
          </el-select>
        </el-form-item>
        <el-form-item label="Panels / page">
          <el-input-number v-model="project.panel_count" :min="1" :max="8" @change="saveSettings" class="w-150" />
        </el-form-item>
        <el-form-item label="Pages">
          <el-input-number v-model="project.page_count" :min="1" :max="20" @change="saveSettings" class="w-150" />
        </el-form-item>
        <el-form-item label="Aspect Ratio">
          <el-select v-model="project.aspect_ratio" placeholder="Select" @change="saveSettings" class="w-150">
            <el-option label="1:1" value="1:1" />
            <el-option label="2:3" value="2:3" />
            <el-option label="3:2" value="3:2" />
            <el-option label="3:4" value="3:4" />
            <el-option label="4:3" value="4:3" />
            <el-option label="4:5" value="4:5" />
            <el-option label="5:4" value="5:4" />
            <el-option label="9:16" value="9:16" />
            <el-option label="16:9" value="16:9" />
            <el-option label="21:9" value="21:9" />
          </el-select>
        </el-form-item>
        <el-form-item label="Resolution">
          <el-select v-model="project.resolution" placeholder="Select" @change="saveSettings" class="w-150">
            <el-option label="500px (small file)" value="500" />
            <el-option label="1K" value="1K" />
            <el-option label="2K" value="2K" />
            <el-option label="4K" value="4K" />
          </el-select>
        </el-form-item>
        <el-form-item label="Color">
          <el-select v-model="project.color_mode" placeholder="Select" @change="saveSettings" class="w-150">
            <el-option label="Full Color" value="color" />
            <el-option label="Black &amp; White" value="bw" />
          </el-select>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- Page Layout Picker (optional) -->
    <el-card class="box-card mb-4" shadow="never">
      <template #header>
        <div class="card-header">
          <span>Page Layout <span class="muted">· optional</span></span>
        </div>
      </template>
      <p class="layout-lead">
        Leave it on <b>Auto</b> and we pick a layout that fits your story's beats — or choose one
        yourself. Changing the layout later never re-draws your art.
      </p>

      <div class="auto-row" :class="{ active: layoutMode === 'auto' }" @click="selectAuto">
        <div class="auto-spark">✦</div>
        <div class="auto-txt">
          <b>Auto layout</b>
          <div class="muted">We choose from the {{ project.panel_count || '—' }}-panel templates based on pacing.</div>
        </div>
        <div class="auto-badge" :class="{ on: layoutMode === 'auto' }">Recommended</div>
      </div>

      <div class="tpl-groups">
        <div v-for="g in groups" :key="g.n" class="tpl-group">
          <div class="group-label">{{ g.n }} panels</div>
          <div class="tpl-grid">
            <div
              v-for="t in g.items" :key="t.id"
              class="tpl-card"
              :class="{ active: layoutMode === 'manual' && selectedTemplate === t.id }"
              @click="selectTemplate(t)"
            >
              <div class="tpl-thumb" v-html="tplSvg(t)"></div>
              <div class="tpl-meta"><span>{{ t.name }}</span><span class="pc">{{ t.panels }}p</span></div>
            </div>
          </div>
        </div>
      </div>
    </el-card>

    <!-- Main Section: Story Input -->
    <el-card class="box-card story-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>Story Input</span>
          <div class="upload-area">
            <input type="file" ref="fileInput" @change="handleFileUpload" accept=".txt" style="display: none" />
            <el-button size="small" @click="$refs.fileInput.click()">Import from File (.txt)</el-button>
            <span v-if="fileName" class="file-name ml-2">{{ fileName }}</span>
          </div>
        </div>
      </template>
      
      <el-input 
        type="textarea" 
        :rows="15" 
        v-model="storyInput" 
        placeholder="Enter your story idea, synopsis, or full text here..." 
        @change="saveStoryInput" 
        class="story-textarea"
        resize="none"
      />
      
      <div class="action-footer mt-4">
        <el-button size="large" type="primary" @click="generateStoryboard" :disabled="isTaskRunning || !storyInput">
          Generate Storyboard
        </el-button>
        
        <el-popconfirm 
          title="Regenerate will overwrite existing storyboard and character settings. Continue?" 
          confirm-button-text="Yes"
          cancel-button-text="No"
          @confirm="generateStoryboard"
        >
          <template #reference>
            <el-button size="large" type="warning" plain :disabled="isTaskRunning || !storyInput">
              Regenerate All
            </el-button>
          </template>
        </el-popconfirm>

        <el-button size="large" @click="saveStoryInput">Save Story Only</el-button>
      </div>
    </el-card>

    <!-- Dialogs -->
    <JsonEditorDialog 
      v-model:visible="showGlobalConfig" 
      :content="globalConfigEditor" 
      title="Global Configuration"
      @save="handleGlobalConfigSave"
    />
  </div>
</template>

<script setup>
import { ref, watch, computed, onMounted } from 'vue'
import axios from 'axios'
import { ElMessage } from 'element-plus'
import JsonEditorDialog from './JsonEditorDialog.vue'

const props = defineProps({
  project: Object,
  projectId: [String, Number],
  isTaskRunning: Boolean
})

const emit = defineEmits(['refresh-project', 'task-started'])

const storyInput = ref('')
const fileName = ref('')
const fileInput = ref(null)
const globalConfigEditor = ref('')
const showGlobalConfig = ref(false)

// --- Page layout picker ---
const layoutLib = ref({ canvas: { w: 1200, h: 1800 }, templates: [] })
const layoutMode = ref('auto')        // 'auto' | 'manual'
const selectedTemplate = ref(null)

const groups = computed(() => {
  const by = {}
  for (const t of layoutLib.value.templates) (by[t.panels] ||= []).push(t)
  return Object.keys(by).sort((a, b) => a - b).map(n => ({ n: Number(n), items: by[n] }))
})

const tplSvg = (t) => {
  const c = layoutLib.value.canvas
  const shapes = t.slots.map(s => {
    if (s.shape === 'rect')
      return `<rect x="${s.x}" y="${s.y}" width="${s.w}" height="${s.h}" rx="10" fill="var(--tpl-fill,#212a3e)" stroke="var(--tpl-line,#9aa6bd)" stroke-width="14"/>`
    return `<polygon points="${s.points.map(p => p.join(',')).join(' ')}" fill="var(--tpl-fill,#212a3e)" stroke="var(--tpl-line,#9aa6bd)" stroke-width="14" stroke-linejoin="round"/>`
  }).join('')
  return `<svg viewBox="0 0 ${c.w} ${c.h}" preserveAspectRatio="xMidYMid meet" style="width:100%;height:100%;display:block">${shapes}</svg>`
}

const selectAuto = () => {
  layoutMode.value = 'auto'
  selectedTemplate.value = null
  saveLayout()
}
const selectTemplate = (t) => {
  layoutMode.value = 'manual'
  selectedTemplate.value = t.id
  // picking a template locks the panel count to its slot count
  if (props.project.panel_count !== t.panels) {
    props.project.panel_count = t.panels
    saveSettings()
  }
  saveLayout()
}
const saveLayout = async () => {
  const page_layout = layoutMode.value === 'manual' && selectedTemplate.value
    ? { mode: 'manual', template_id: selectedTemplate.value }
    : { mode: 'auto' }
  // keep the local prop in sync so the deep project watcher doesn't reset our choice
  props.project.page_layout = page_layout
  try {
    await axios.put(`/api/v1/projects/${props.projectId}`, { page_layout })
    ElMessage.success('Layout saved')
  } catch (e) {
    ElMessage.error('Failed to save layout')
  }
}

onMounted(async () => {
  try {
    const { data } = await axios.get('/api/v1/layouts/')
    layoutLib.value = data
  } catch (e) {
    console.error('Failed to load layouts', e)
  }
})

// Initialize local state when project changes
watch(() => props.project, (newVal) => {
  if (newVal) {
    if (newVal.story_input && !storyInput.value) storyInput.value = newVal.story_input
    if (newVal.global_config) {
      globalConfigEditor.value = JSON.stringify(newVal.global_config.data, null, 2)
    }
    const pl = newVal.page_layout
    if (pl && pl.mode === 'manual' && pl.template_id) {
      layoutMode.value = 'manual'
      selectedTemplate.value = pl.template_id
    } else {
      layoutMode.value = 'auto'
      selectedTemplate.value = null
    }
  }
}, { immediate: true, deep: true })

const saveSettings = async () => {
  try {
    await axios.put(`/api/v1/projects/${props.projectId}`, { 
      theme: props.project.theme,
      language: props.project.language,
      panel_count: props.project.panel_count,
      page_count: props.project.page_count,
      aspect_ratio: props.project.aspect_ratio,
      resolution: props.project.resolution,
      color_mode: props.project.color_mode
    })
    ElMessage.success('Settings saved')
  } catch (e) {
    ElMessage.error('Failed to save settings')
  }
}

const saveStoryInput = async () => {
  try {
    await axios.put(`/api/v1/projects/${props.projectId}`, { story_input: storyInput.value })
    ElMessage.success('Story saved')
  } catch (e) {
    console.error("Failed to save story input", e)
  }
}

const handleFileUpload = (event) => {
  const file = event.target.files[0]
  if (!file) return
  fileName.value = file.name
  const reader = new FileReader()
  reader.onload = (e) => {
    storyInput.value = e.target.result
    saveStoryInput() 
    ElMessage.success('File read successfully')
  }
  reader.onerror = () => ElMessage.error('Failed to read file')
  reader.readAsText(file)
}

const generateStoryboard = async () => {
  if (!storyInput.value) return ElMessage.warning('Please enter story content')
  try {
    await saveStoryInput()
    await axios.post(`/api/v1/generate/storyboard/${props.projectId}`, {
      user_input: storyInput.value
    })
    emit('task-started')
    ElMessage.info('Storyboard generation task started in background...')
  } catch (error) {
    ElMessage.error('Failed to start task: ' + (error.response?.data?.detail || error.message))
  }
}

const openGlobalConfig = () => {
  // Ensure editor has latest
  if (props.project.global_config) {
    globalConfigEditor.value = JSON.stringify(props.project.global_config.data, null, 2)
  } else {
    globalConfigEditor.value = '{}'
  }
  showGlobalConfig.value = true
}

const handleGlobalConfigSave = async (newContent) => {
  try {
    const data = JSON.parse(newContent)
    await axios.put(`/api/v1/projects/${props.projectId}/global_config`, data)
    ElMessage.success('Global config synced')
    emit('refresh-project')
  } catch (e) {
    ElMessage.error('Save failed: ' + e.message)
  }
}
</script>

<style scoped>
.story-tab-content {
  max-width: 1200px;
  margin: 0 auto;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.settings-form {
  /* padding: 10px 0; */
}
.w-200 { width: 200px; }
.w-150 { width: 150px; }

.story-textarea :deep(.el-textarea__inner) {
  font-family: inherit;
  font-size: 1.05rem;
  line-height: 1.6;
  padding: 16px;
}
.upload-area { display: flex; align-items: center; }
.file-name { color: #888; font-size: 0.9em; }
.action-footer {
  display: flex;
  gap: 16px;
  justify-content: flex-start;
  border-top: 1px solid #333;
  padding-top: 20px;
}

.mb-4 { margin-bottom: 24px; }
.mt-4 { margin-top: 24px; }
.ml-2 { margin-left: 10px; }

/* --- Page Layout picker --- */
.muted { color: #8a94a9; font-weight: 400; font-size: 0.9em; }
.layout-lead { color: #8a94a9; font-size: 0.9rem; margin: 0 0 16px; max-width: 70ch; }

.auto-row {
  display: flex; align-items: center; gap: 14px; padding: 14px 16px; cursor: pointer;
  border: 1.5px solid var(--el-border-color, #3a3a3a); border-radius: 10px;
  background: var(--el-fill-color-light, #1d2436); margin-bottom: 18px; transition: all .15s;
}
.auto-row.active { border-color: #e0a23c; background: rgba(224, 162, 60, .12); }
.auto-spark {
  flex: none; width: 40px; height: 40px; border-radius: 9px; display: grid; place-items: center;
  background: rgba(224, 162, 60, .16); color: #e0a23c; font-size: 18px;
}
.auto-txt b { font-size: 0.95rem; }
.auto-badge {
  margin-left: auto; font-size: 11px; font-weight: 700; letter-spacing: .04em; text-transform: uppercase;
  color: #8a94a9; border: 1px solid #4a4a4a; border-radius: 999px; padding: 4px 10px;
}
.auto-badge.on { color: #e0a23c; border-color: #e0a23c; }

.tpl-group { margin-bottom: 18px; }
.group-label {
  font-size: 11px; text-transform: uppercase; letter-spacing: .09em; color: #8a94a9;
  font-weight: 700; margin-bottom: 10px;
}
.tpl-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(96px, 1fr)); gap: 10px; }

.tpl-card {
  cursor: pointer; border: 1.5px solid var(--el-border-color, #3a3a3a); border-radius: 8px;
  padding: 6px; background: var(--el-fill-color-light, #1d2436); transition: all .15s;
  display: flex; flex-direction: column; gap: 5px;
}
.tpl-card:hover { transform: translateY(-2px); border-color: #606266; }
.tpl-card.active { border-color: #409eff; background: rgba(64, 158, 255, .12); }
.tpl-thumb {
  background: var(--el-bg-color, #141922); border: 1px solid var(--el-border-color, #3a3a3a);
  border-radius: 5px; aspect-ratio: 2 / 3; overflow: hidden;
  --tpl-fill: #212a3e; --tpl-line: #aeb8cc;
}
.tpl-meta { display: flex; align-items: center; justify-content: space-between; gap: 4px; font-size: 10.5px; }
.tpl-meta span:first-child { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tpl-meta .pc {
  flex: none; color: #8a94a9; border: 1px solid var(--el-border-color, #3a3a3a); border-radius: 4px; padding: 0 4px; font-size: 9px;
}
.tpl-card.active .tpl-meta .pc { color: #409eff; border-color: #409eff; }
</style>