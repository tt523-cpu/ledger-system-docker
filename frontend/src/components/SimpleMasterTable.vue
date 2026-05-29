<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '../api/http'

const props = defineProps({
  title: { type: String, required: true },
  endpoint: { type: String, required: true },
  fields: { type: Array, required: true },
  defaults: { type: Object, default: () => ({}) },
})

const items = ref([])
const saving = ref(false)
const editingId = ref(null)
const form = reactive({ ...props.defaults })
const editForm = reactive({})

function statusText(status) {
  return status === 'enabled' ? '启用' : status === 'disabled' ? '停用' : status
}

function resetForm() {
  Object.keys(form).forEach((k) => {
    form[k] = props.defaults[k] ?? ''
  })
}

async function load() {
  const { data } = await http.get(`/master/${props.endpoint}`)
  items.value = data
}

async function submit() {
  saving.value = true
  try {
    await http.post(`/master/${props.endpoint}`, form)
    ElMessage.success('新增成功')
    resetForm()
    await load()
  } finally {
    saving.value = false
  }
}

function startEdit(row) {
  editingId.value = row.id
  Object.keys(row).forEach((k) => {
    editForm[k] = row[k]
  })
}

async function saveEdit(id) {
  await http.put(`/master/${props.endpoint}/${id}`, editForm)
  ElMessage.success('修改成功')
  editingId.value = null
  await load()
}

async function removeRow(id) {
  await ElMessageBox.confirm('确认删除该记录吗？', '提示', { type: 'warning' })
  await http.delete(`/master/${props.endpoint}/${id}`)
  ElMessage.success('删除成功')
  await load()
}

onMounted(() => {
  resetForm()
  load()
})
</script>

<template>
  <el-card>
    <template #header>{{ title }}</template>
    <el-form inline>
      <el-form-item v-for="f in fields" :key="f.key" :label="f.label">
        <el-input v-if="f.type !== 'number'" v-model="form[f.key]" :placeholder="f.label" />
        <el-input-number v-else v-model="form[f.key]" :min="0" />
      </el-form-item>
      <el-form-item label="状态">
        <el-select v-model="form.status" style="width: 120px">
          <el-option value="enabled" label="启用" />
          <el-option value="disabled" label="停用" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="saving" @click="submit">新增</el-button>
      </el-form-item>
    </el-form>

    <el-table :data="items" style="margin-top: 12px" border>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column v-for="f in fields" :key="f.key" :label="f.label">
        <template #default="{ row }">
          <span v-if="editingId !== row.id">{{ row[f.key] }}</span>
          <el-input v-else-if="f.type !== 'number'" v-model="editForm[f.key]" />
          <el-input-number v-else v-model="editForm[f.key]" :min="0" />
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <span v-if="editingId !== row.id">{{ statusText(row.status) }}</span>
          <el-select v-else v-model="editForm.status" style="width: 100px">
            <el-option value="enabled" label="启用" />
            <el-option value="disabled" label="停用" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="190">
        <template #default="{ row }">
          <el-button v-if="editingId !== row.id" link type="primary" @click="startEdit(row)">编辑</el-button>
          <el-button v-if="editingId === row.id" link type="primary" @click="saveEdit(row.id)">保存</el-button>
          <el-button v-if="editingId === row.id" link @click="editingId = null">取消</el-button>
          <el-button link type="danger" @click="removeRow(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>
