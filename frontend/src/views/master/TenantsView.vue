<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '../../api/http'

const tenants = ref([])
const statsMap = ref({})

const createDialog = ref(false)
const createForm = reactive({ name: '', status: 'enabled', admin_username: '', admin_password: '', admin_expire_at: '' })

const editDialog = ref(false)
const editForm = reactive({ id: null, name: '', status: 'enabled', admin_username: '', admin_password: '', admin_expire_at: '' })

async function load() {
  const { data } = await http.get('/master/tenants')
  tenants.value = data || []
}

function openCreate() {
  createForm.name = ''
  createForm.status = 'enabled'
  createForm.admin_username = ''
  createForm.admin_password = ''
  createForm.admin_expire_at = ''
  createDialog.value = true
}

async function saveCreate() {
  if (!createForm.name.trim()) {
    ElMessage.warning('请输入租户名称')
    return
  }
  if (!createForm.admin_username.trim()) {
    ElMessage.warning('请输入主账号用户名')
    return
  }
  if ((createForm.admin_password || '').length < 6) {
    ElMessage.warning('主账号密码至少6位')
    return
  }
  try {
    await http.post('/master/tenants', {
      name: createForm.name.trim(),
      status: createForm.status,
      admin_username: createForm.admin_username.trim(),
      admin_password: createForm.admin_password,
      admin_expire_at: createForm.admin_expire_at || null,
    })
    ElMessage.success('租户创建成功')
    createDialog.value = false
    await load()
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '创建租户失败')
  }
}

function openEdit(row) {
  editForm.id = row.id
  editForm.name = row.name || ''
  editForm.status = row.status || 'enabled'
  editForm.admin_username = row.admin_username || ''
  editForm.admin_password = ''
  editForm.admin_expire_at = row.tenant_expire_at || ''
  editDialog.value = true
}

async function saveEdit() {
  if (!editForm.id) return
  if (!editForm.name.trim()) {
    ElMessage.warning('请输入租户名称')
    return
  }
  if (!editForm.admin_username.trim()) {
    ElMessage.warning('请输入主账号用户名')
    return
  }
  if (editForm.admin_password && editForm.admin_password.length < 6) {
    ElMessage.warning('新密码至少6位')
    return
  }
  try {
    await http.put(`/master/tenants/${editForm.id}`, {
      name: editForm.name.trim(),
      status: editForm.status,
      admin_username: editForm.admin_username.trim(),
      admin_password: editForm.admin_password || null,
      admin_expire_at: editForm.admin_expire_at || null,
    })
    ElMessage.success('租户信息已更新')
    editDialog.value = false
    await load()
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '更新失败')
  }
}

async function resetTenantAdminPassword(row) {
  const ret = await ElMessageBox.prompt(`请输入租户 ${row.name} 主账号的新密码`, '重置主账号密码', {
    confirmButtonText: '确认',
    cancelButtonText: '取消',
    inputType: 'password',
    inputPattern: /^.{6,}$/,
    inputErrorMessage: '密码至少6位',
  }).catch(() => null)
  if (!ret) return
  const admins = (await http.get(`/master/tenants/${row.id}/admins`)).data || []
  if (!admins.length) {
    ElMessage.error('该租户暂无主账号')
    return
  }
  await http.put(`/master/tenants/${row.id}/admins/${admins[0].id}/password`, null, { params: { new_password: ret.value } })
  ElMessage.success('主账号密码已重置')
}

function statusLabel(status) {
  return status === 'enabled' ? '启用' : '停用'
}

function expireLabel(v) {
  return v ? String(v).replace('T', ' ').slice(0, 19) : '无限期'
}

async function downloadTenantBackup(row) {
  const res = await http.get('/system/backup/tenant-export', {
    params: { tenant_id: row.id },
    responseType: 'blob',
  })
  const url = window.URL.createObjectURL(res.data)
  const a = document.createElement('a')
  a.href = url
  a.download = `tenant-${row.id}-backup.json`
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.URL.revokeObjectURL(url)
}

async function restoreTenantBackup(row, file) {
  const ok = await ElMessageBox.confirm(`确认恢复备份到租户「${row.name}」？将覆盖该租户现有业务数据`, '高风险操作', { type: 'warning' }).catch(() => null)
  if (!ok) return false
  const fd = new FormData()
  fd.append('file', file.raw)
  await http.post('/system/backup/tenant-restore', fd, {
    params: { tenant_id: row.id },
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  ElMessage.success('租户恢复完成')
  return false
}

async function loadStats(row) {
  const { data } = await http.get(`/master/tenants/${row.id}/stats`)
  statsMap.value[row.id] = data
}

async function removeTenant(row) {
  const ok = await ElMessageBox.confirm(`确认删除租户「${row.name}」？仅允许删除无业务数据的租户。`, '高风险操作', { type: 'warning' }).catch(() => null)
  if (!ok) return
  try {
    await http.delete(`/master/tenants/${row.id}`)
    ElMessage.success('租户删除成功')
    await load()
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '删除租户失败')
  }
}

onMounted(load)
</script>

<template>
  <el-card>
    <template #header>租户管理</template>

    <div style="margin-bottom: 12px">
      <el-button type="primary" @click="openCreate">新增租户</el-button>
    </div>

    <el-table :data="tenants" border>
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column prop="name" label="租户名称" width="220" />
      <el-table-column prop="admin_username" label="主账号" width="180" />
      <el-table-column label="到期时间" width="180">
        <template #default="{ row }">{{ expireLabel(row.tenant_expire_at) }}</template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">{{ statusLabel(row.status) }}</template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="190" />
      <el-table-column label="运营" width="220">
        <template #default="{ row }">
          <el-button link type="primary" @click="loadStats(row)">刷新</el-button>
          <span v-if="statsMap[row.id]" style="font-size: 12px; margin-left: 8px">
            用户{{ statsMap[row.id].user_count }} / 平台{{ statsMap[row.id].platform_count }} / 流水{{ statsMap[row.id].transaction_count }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="380">
        <template #default="{ row }">
          <el-space :size="8" wrap="false">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="warning" @click="resetTenantAdminPassword(row)">重置密码</el-button>
            <el-button link type="success" @click="downloadTenantBackup(row)">备份</el-button>
            <el-upload :show-file-list="false" :auto-upload="false" :on-change="(file) => restoreTenantBackup(row, file)">
              <el-button link type="warning">恢复</el-button>
            </el-upload>
            <el-button link type="danger" @click="removeTenant(row)">删除</el-button>
          </el-space>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="createDialog" title="新增租户" width="560px">
      <el-form label-width="100px">
        <el-form-item label="租户名称"><el-input v-model="createForm.name" /></el-form-item>
        <el-form-item label="主账号"><el-input v-model="createForm.admin_username" /></el-form-item>
        <el-form-item label="主密码"><el-input v-model="createForm.admin_password" type="password" /></el-form-item>
        <el-form-item label="到期时间"><el-date-picker v-model="createForm.admin_expire_at" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" clearable placeholder="留空为无限期" /></el-form-item>
        <el-form-item label="状态">
          <el-select v-model="createForm.status" style="width: 140px">
            <el-option value="enabled" label="启用" />
            <el-option value="disabled" label="停用" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialog = false">取消</el-button>
        <el-button type="primary" @click="saveCreate">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="editDialog" title="编辑租户" width="560px">
      <el-form label-width="100px">
        <el-form-item label="租户名称"><el-input v-model="editForm.name" /></el-form-item>
        <el-form-item label="主账号"><el-input v-model="editForm.admin_username" /></el-form-item>
        <el-form-item label="新密码"><el-input v-model="editForm.admin_password" type="password" placeholder="不填则不修改" /></el-form-item>
        <el-form-item label="到期时间"><el-date-picker v-model="editForm.admin_expire_at" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" clearable placeholder="留空为无限期" /></el-form-item>
        <el-form-item label="状态">
          <el-select v-model="editForm.status" style="width: 140px">
            <el-option value="enabled" label="启用" />
            <el-option value="disabled" label="停用" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialog = false">取消</el-button>
        <el-button type="primary" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>
