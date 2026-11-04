<template>
  <div class="characters-view">
    <div class="header">
      <h2>My Characters</h2>
      <el-button type="primary" @click="openCreate">New Character</el-button>
    </div>
    <p class="lead">Create reusable characters from a text description (FLUX.1 Kontext). These live
      independently of any project.</p>

    <el-empty v-if="!loading && characters.length === 0" description="No characters yet. Create one!" />

    <el-row :gutter="20">
      <el-col :span="6" v-for="c in characters" :key="c.id">
        <el-card shadow="hover" class="char-card">
          <div class="thumb">
            <el-image v-if="c.image_url" :src="`${c.image_url}?v=${version}`" fit="cover"
              :preview-src-list="[`${c.image_url}?v=${version}`]" class="char-img" />
            <div v-else class="no-img">No image</div>
          </div>
          <div class="meta">
            <span class="char-name" :title="c.name">{{ c.name }}</span>
            <el-button type="danger" text size="small" @click="removeCharacter(c.id)">Delete</el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-dialog v-model="dialogVisible" title="New Character" width="520px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="Name">
          <el-input v-model="form.name" placeholder="e.g. Aria the Explorer" />
        </el-form-item>
        <el-form-item label="Style">
          <el-select v-model="form.style" placeholder="Choose or type a style"
            filterable allow-create default-first-option class="full-w">
            <el-option v-for="s in STYLES" :key="s" :label="s" :value="s" />
          </el-select>
        </el-form-item>
        <el-form-item label="Description">
          <el-input type="textarea" :rows="4" v-model="form.description"
            placeholder="Describe the character: appearance, hair, outfit, personality..." />
        </el-form-item>
        <el-form-item label="Photo">
          <input ref="photoInput" type="file" accept="image/png,image/jpeg,image/webp"
            style="display:none" @change="onPhotoChange" />
          <el-button @click="photoInput?.click()">{{ photoFile ? 'Change photo' : 'Attach photo (optional)' }}</el-button>
          <span v-if="photoFile" class="photo-name">{{ photoFile.name }}
            <el-button text size="small" @click="photoFile = null">clear</el-button>
          </span>
        </el-form-item>
        <el-form-item v-if="photoFile" label="Engine">
          <el-select v-model="form.engine" class="full-w">
            <el-option label="FLUX.1 Kontext (best likeness)" value="flux" />
            <el-option label="Nano Banana" value="nano" />
          </el-select>
        </el-form-item>
        <p class="hint">Attach a photo to transform it into the character (image-to-image), or leave it empty to create from the text description.</p>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">Cancel</el-button>
        <el-button type="primary" :loading="creating" @click="createCharacter">Create</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'
import { ElMessage } from 'element-plus'

const characters = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const creating = ref(false)
const version = ref(Date.now())
const STYLES = [
  'Modern anime/manga style',
  'Chibi / cute',
  'Shonen manga (bold, dynamic)',
  'Shoujo manga (soft, romantic)',
  'Black & white manga (ink + screentone)',
  'American comic book',
  'Gritty noir comic',
  'Ghibli-esque soft painterly',
  'Watercolor illustration',
  'Cyberpunk',
  'Semi-realistic',
  'Pixel art',
]
const form = ref({ name: '', style: 'Modern anime/manga style', description: '', engine: 'flux' })
const photoInput = ref(null)
const photoFile = ref(null)
const onPhotoChange = (e) => { photoFile.value = (e.target.files && e.target.files[0]) || null }

const fetchCharacters = async () => {
  loading.value = true
  try {
    const res = await axios.get('/api/v1/library/characters')
    characters.value = res.data
    version.value = Date.now()
  } catch (e) {
    ElMessage.error('Failed to load characters')
  } finally {
    loading.value = false
  }
}

const openCreate = () => {
  form.value = { name: '', style: 'Modern anime/manga style', description: '', engine: 'flux' }
  photoFile.value = null
  dialogVisible.value = true
}

const pollTask = async (taskId) => {
  for (let i = 0; i < 90; i++) {
    try {
      const { data } = await axios.get(`/api/v1/tasks/${taskId}`)
      if (data.status === 'completed') { await fetchCharacters(); return }
      if (data.status === 'failed') { ElMessage.error('Generation failed: ' + (data.message || '')); return }
    } catch (e) { /* keep polling */ }
    await new Promise(r => setTimeout(r, 3000))
  }
}

const createCharacter = async () => {
  if (!form.value.name && !form.value.description) {
    return ElMessage.warning('Add a name and description')
  }
  creating.value = true
  try {
    let data
    if (photoFile.value) {
      const fd = new FormData()
      fd.append('file', photoFile.value)
      fd.append('name', form.value.name || 'Character')
      fd.append('style', form.value.style)
      fd.append('description', form.value.description)
      fd.append('engine', form.value.engine)
      data = (await axios.post('/api/v1/library/characters/from-photo', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })).data
      ElMessage.info(`Creating character from photo (${form.value.engine})...`)
    } else {
      data = (await axios.post('/api/v1/library/characters', form.value)).data
      ElMessage.info('Generating character from text with FLUX...')
    }
    dialogVisible.value = false
    await fetchCharacters()          // show the placeholder card immediately
    pollTask(data.task_id)           // refresh when the image is ready
  } catch (e) {
    ElMessage.error('Failed: ' + (e.response?.data?.detail || e.message))
  } finally {
    creating.value = false
  }
}

const removeCharacter = async (id) => {
  try {
    await axios.delete(`/api/v1/library/characters/${id}`)
    ElMessage.success('Deleted')
    fetchCharacters()
  } catch (e) {
    ElMessage.error('Delete failed')
  }
}

onMounted(fetchCharacters)
</script>

<style scoped>
.characters-view { padding: 20px; }
.header { display: flex; justify-content: space-between; align-items: center; }
.lead { color: #8a94a9; font-size: 0.9rem; margin: 4px 0 20px; }
.char-card { margin-bottom: 20px; }
.thumb {
  width: 100%; aspect-ratio: 2 / 3; background: var(--el-fill-color-darker, #1a1a1a);
  border-radius: 6px; overflow: hidden; display: flex; align-items: center; justify-content: center;
}
.char-img { width: 100%; height: 100%; }
.no-img { color: #666; font-size: 0.9em; }
.meta { display: flex; align-items: center; justify-content: space-between; margin-top: 10px; }
.char-name {
  font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 70%;
}
.full-w { width: 100%; }
.photo-name { margin-left: 10px; color: #8a94a9; font-size: 0.85em; }
.hint { color: #8a94a9; font-size: 0.82rem; margin: 4px 0 0; }
</style>
