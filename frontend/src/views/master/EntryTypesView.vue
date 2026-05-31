<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '../../api/http'

const items = ref([])
const saving = ref(false)
const editingId = ref(null)
const form = reactive({ name: '', effect: 'expense', requires_category: false, sort_order: 0, status: 'enabled' })
const editForm = reactive({})

const effectOptions = [
  { value: 'income', label: '收入（加）' },
  { value: 'expense', label: '开支（减）' },
  { value: 'adjust', label: '回冲（冲正）' },
]

function effectLabel(v) {
  const row = effectOptions.find((x) => x.value === v)
  return row ? row.label : v
}

async function load() {
  const { data } = await http.get('/master/entry-types')
  items.value = data
}

async function submit() {
  saving.value = true
  try {
    await http.post('/master/entry-types', form)
    ElMessage.success('新增成功')
    form.name = ''
    form.effect = 'expense'
    form.requires_category = false
    form.sort_order = 0
    form.status = 'enabled'
    await load()
  } finally {
    saving.value = false
  }
}

function startEdit(row) {
  editingId.value = row.id
  editForm.id = row.id
  editForm.name = row.name
  editForm.effect = row.effect
  editForm.requires_category = !!row.requires_category
  editForm.sort_order = row.sort_order
  editForm.status = row.status
}

async function saveEdit(id) {
  await http.put(`/master/entry-types/${id}`, editForm)
  ElMessage.success('修改成功')
  editingId.value = null
  await load()
}

async function removeRow(id) {
  try {
    await ElMessageBox.confirm('确认删除该录入类型吗？', '提示', { type: 'warning' })
    await http.delete(`/master/entry-types/${id}`)
    ElMessage.success('删除成功')
    await load()
  } catch (err) {
    if (err === 'cancel') return
    ElMessage.error(err?.response?.data?.detail || '删除失败')
  }
}

onMounted(load)
</script>

<template>
  <el-card>
    <template #header>类型管理</template>
    <el-form inline>
      <el-form-item label="名称">
        <el-input v-model="form.name" placeholder="例如：充值、兑奖、误上" style="width: 220px" />
      </el-form-item>
      <el-form-item label="记账方向">
        <el-select v-model="form.effect" style="width: 180px">
          <el-option v-for="e in effectOptions" :key="e.value" :value="e.value" :label="e.label" />
        </el-select>
      </el-form-item>
      <el-form-item label="需要项目">
        <el-switch v-model="form.requires_category" active-text="是" inactive-text="否" />
      </el-form-item>
      <el-form-item label="排序">
        <el-input-number v-model="form.sort_order" :min="0" />
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

    <el-table :data="items" border>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column label="名称">
        <template #default="{ row }">
          <span v-if="editingId !== row.id">{{ row.name }}</span>
          <el-input v-else v-model="editForm.name" />
        </template>
      </el-table-column>
      <el-table-column label="记账方向" width="200">
        <template #default="{ row }">
          <span v-if="editingId !== row.id">{{ effectLabel(row.effect) }}</span>
          <el-select v-else v-model="editForm.effect" style="width: 180px">
            <el-option v-for="e in effectOptions" :key="e.value" :value="e.value" :label="e.label" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="排序" width="120">
        <template #default="{ row }">
          <span v-if="editingId !== row.id">{{ row.sort_order }}</span>
          <el-input-number v-else v-model="editForm.sort_order" :min="0" />
        </template>
      </el-table-column>
      <el-table-column label="需要项目" width="140">
        <template #default="{ row }">
          <span v-if="editingId !== row.id">{{ row.requires_category ? '是' : '否' }}</span>
          <el-switch v-else v-model="editForm.requires_category" active-text="是" inactive-text="否" />
        </template>
      </el-table-column>
      <el-table-column label="状态" width="120">
        <template #default="{ row }">
          <span v-if="editingId !== row.id">{{ row.status }}</span>
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
