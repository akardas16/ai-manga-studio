<template>
  <div class="storyboard-tab">
    <div class="comic-actions mb-4">
        <el-tooltip :disabled="hasCharacters" content="Please generate character images in Character Studio first" placement="top">
          <div style="display: inline-block;">
            <el-popconfirm 
                title="This will regenerate ALL panel images, overwriting existing ones. Continue?" 
                confirm-button-text="Yes, Overwrite" 
                cancel-button-text="Cancel"
                @confirm="generateAllImages"
            >
              <template #reference>
                <el-button type="primary" size="large" :disabled="!hasCharacters || isTaskRunning">
                  Generate All Panels (Overwrite)
                </el-button>
              </template>
            </el-popconfirm>
          </div>
        </el-tooltip>
        <el-tooltip :disabled="hasCharacters" content="Please generate character images in Character Studio first" placement="top">
          <div style="display: inline-block; margin-left: 12px;">
            <el-popconfirm
                title="Render each panel separately and compose them into your selected page layout (with text overlaid). Continue?"
                confirm-button-text="Yes, Render"
                cancel-button-text="Cancel"
                @confirm="generateLayoutPage"
            >
              <template #reference>
                <el-button type="success" size="large" plain :disabled="!hasCharacters || isTaskRunning">
                  Render Page (Layout)
                </el-button>
              </template>
            </el-popconfirm>
          </div>
        </el-tooltip>
      <div class="info-group">
        <span class="tip-text ml-2">Generation will proceed in storyboard order, subsequent panels will reference previous image content.</span>
        <span v-if="!hasCharacters" class="warning-text ml-2"><el-icon><Warning /></el-icon> Please generate characters first!</span>
      </div>
    </div>
    
    <div class="pages-scroll">
      <el-card v-for="item in sortedStoryboard" :key="item.id" class="page-card" shadow="hover">
        <template #header>
          <div class="card-header">
            <span class="panel-title">Page {{ item.sequence }}</span>
            <el-select :model-value="item.data.layout_template_id || ''" size="small"
              placeholder="Layout" style="width: 140px"
              @change="(v) => setPageLayout(item, v)">
              <el-option label="Auto / Random" value="" />
              <el-option v-for="t in layoutsForPage(item)" :key="t.id" :label="t.name" :value="t.id" />
            </el-select>
          </div>
        </template>

        <div class="page-image-wrap">
          <el-image
            v-if="item.image_url"
            :src="`${item.image_url}?v=${imageVersion}`"
            fit="contain"
            class="page-preview"
            :preview-src-list="[`${item.image_url}?v=${imageVersion}`]"
          >
            <template #error><div class="image-slot"><el-icon><icon-picture /></el-icon></div></template>
          </el-image>
          <div v-else class="no-image"><span>No Image</span></div>
        </div>

        <div class="page-actions">
          <el-tooltip :disabled="hasCharacters" content="Generate character images first" placement="top">
            <el-button size="small" type="primary" plain @click="generatePanel(item.id)" :disabled="!hasCharacters">Regenerate</el-button>
          </el-tooltip>
          <el-button size="small" link @click="openJsonEditor(item)">Edit JSON</el-button>
          <a v-if="item.image_url" :href="item.image_url" :download="`page_${item.sequence}.png`" target="_blank">
            <el-button size="small" link>Download</el-button>
          </a>
        </div>
      </el-card>
    </div>

    <JsonEditorDialog
      v-model:visible="showJsonEditor"
      :content="currentEditorContent"
      :title="`Edit Panel ${currentEditingItem?.sequence || ''}`"
      @save="handleJsonSave"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import axios from 'axios'
import { ElMessage } from 'element-plus'
import { Warning, Picture as IconPicture } from '@element-plus/icons-vue'
import JsonEditorDialog from './JsonEditorDialog.vue'

const props = defineProps({
  project: Object,
  projectId: [String, Number],
  isTaskRunning: Boolean,
  imageVersion: Number
})

const emit = defineEmits(['task-started', 'refresh-project', 'open-history'])

// --- per-page layout selection ---
const layoutLib = ref([])
onMounted(async () => {
  try { layoutLib.value = (await axios.get('/api/v1/layouts/')).data.templates } catch (e) { /* ignore */ }
})
const pagePanelCount = (item) => (item.data?.plot_breakdown?.length) || 4
const layoutsForPage = (item) => layoutLib.value.filter(t => t.panels === pagePanelCount(item))
const setPageLayout = async (item, templateId) => {
  try {
    await axios.put(`/api/v1/projects/${props.projectId}/storyboard/${item.id}/layout`, {
      template_id: templateId || null,
    })
    item.data = { ...item.data, layout_template_id: templateId || undefined }
    ElMessage.success(templateId ? 'Page layout set' : 'Page layout set to Auto/Random')
  } catch (e) {
    ElMessage.error('Failed to set layout')
  }
}

const showJsonEditor = ref(false)
const currentEditingItem = ref(null)
const currentEditorContent = ref('')

const sortedStoryboard = computed(() => {
  if (!props.project.storyboard_items) return []
  return [...props.project.storyboard_items].sort((a, b) => a.sequence - b.sequence)
})

const hasCharacters = computed(() => {
  if (!props.project.characters) return false
  return props.project.characters.some(c => c.image_url)
})

const getPanelCharacters = (itemId) => {
  const item = props.project.storyboard_items.find(i => i.id === itemId)
  if (!item || !item.data.characters) return []
  
  let chars = item.data.characters
  if (typeof chars === 'string') return [chars]
  if (Array.isArray(chars)) {
    return chars.map(c => typeof c === 'string' ? c : c.name)
  }
  return []
}

const openJsonEditor = (item) => {
  currentEditingItem.value = item
  currentEditorContent.value = JSON.stringify(item.data, null, 2)
  showJsonEditor.value = true
}

const handleJsonSave = async (newContent) => {
  if (!currentEditingItem.value) return
  try {
    const data = JSON.parse(newContent)
    await axios.put(`/api/v1/projects/${props.projectId}/storyboard/${currentEditingItem.value.id}`, data)
    ElMessage.success('Storyboard content saved')
    emit('refresh-project')
  } catch (e) {
    ElMessage.error('JSON format error or save failed: ' + e.message)
  }
}

const generateAllImages = async () => {
  try {
    await axios.post(`/api/v1/generate/all-images/${props.projectId}`)
    emit('task-started')
    ElMessage.info('Full image generation task started in background...')
  } catch (error) {
    ElMessage.error('Failed to start task: ' + (error.response?.data?.detail || error.message))
  }
}

const generateLayoutPage = async () => {
  try {
    await axios.post(`/api/v1/generate/layout-page/${props.projectId}`)
    emit('task-started')
    ElMessage.info('Rendering panels and composing your layout in the background...')
  } catch (error) {
    ElMessage.error('Failed to start task: ' + (error.response?.data?.detail || error.message))
  }
}

const generatePanel = async (itemId) => {
  try {
    await axios.post(`/api/v1/generate/panel/${itemId}`)
    emit('task-started')
    ElMessage.info('Panel drawing task started in background...')
  } catch (error) {
    console.error(error)
    ElMessage.error('Failed to start task: ' + (error.response?.data?.detail || error.message))
  }
}
</script>

<style scoped>
.storyboard-tab {
  padding-bottom: 40px;
}
.comic-actions {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 16px;
}
.info-group {
    display: flex;
    flex-direction: column;
    gap: 4px;
}
.comic-row {
    margin-bottom: 24px;
}
/* Horizontal scroll of page cards */
.pages-scroll {
    display: flex;
    gap: 18px;
    overflow-x: auto;
    padding: 4px 4px 18px;
    scroll-snap-type: x proximity;
}
.page-card {
    flex: 0 0 auto;
    width: 320px;
    border: 1px solid #333;
    background-color: #1e1e1e;
    scroll-snap-align: start;
}
.page-image-wrap {
    width: 100%;
    aspect-ratio: 2 / 3;
    background: #141414;
    border-radius: 6px;
    overflow: hidden;
    display: flex; align-items: center; justify-content: center;
}
.page-preview { width: 100%; height: 100%; cursor: zoom-in; }
.page-actions {
    display: flex; align-items: center; gap: 8px; margin-top: 10px; flex-wrap: wrap;
}
.panel-card {
    border: 1px solid #333;
    background-color: #1e1e1e;
}
.card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.panel-title {
    font-size: 1.1rem;
    font-weight: 600;
    color: #409EFF;
}
.header-actions {
    display: flex;
    gap: 10px;
}
.panel-details {
    padding-right: 16px;
}
.detail-group {
    margin-bottom: 12px;
}
.detail-group label {
    display: block;
    color: #909399;
    font-size: 0.9rem;
    margin-bottom: 4px;
    font-weight: 500;
}
.detail-content {
    color: #E5EAF3;
    line-height: 1.5;
}
.prompt-text {
    background: #252525;
    padding: 10px;
    border-radius: 4px;
    font-size: 0.95rem;
    max-height: 200px;
    overflow-y: auto;
}
.tags-wrapper {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
}
.image-area {
    display: flex;
    flex-direction: column;
    align-items: center;
}
.image-wrapper {
    width: 100%;
    min-height: 180px;
    display: flex;
    justify-content: center;
    background: #1a1a1a;
    border-radius: 4px;
    padding: 10px;
}
.comic-preview {
    width: 100%;
    max-width: 340px;
    max-height: 480px;
    height: auto;
    object-fit: contain;
    display: block;
    cursor: zoom-in;
}
.no-image {
    width: 100%;
    max-width: 340px;
    height: 200px;
    display: flex;
    justify-content: center;
    align-items: center;
    background: #2a2a2a;
    color: #666;
    border-radius: 4px;
}
.image-actions {
    display: flex;
    justify-content: center;
    width: 100%;
}
.tip-text { color: #888; font-size: 0.9em; }
.warning-text { color: #E6A23C; font-size: 0.9em; display: inline-flex; align-items: center; gap: 4px; }
.text-gray { color: #888; }
.sm-text { font-size: 0.85em; }
.mt-2 { margin-top: 10px; }
.mt-3 { margin-top: 16px; }
.mb-4 { margin-bottom: 24px; }
.ml-2 { margin-left: 10px; }
.mr-2 { margin-right: 10px; }
</style>