<script setup>
import { reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '../api/http'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const isSuper = auth.role === 'super_admin'

const form = reactive({
  before_date: '',
  bill_date: '',
  lock_year: new Date().getFullYear(),
  lock_month: new Date().getMonth() + 1,
})
const restoring = ref(false)
const monthLocks = ref([])
const backupFiles = ref([])
const tenantHealth = ref(null)

async function loadMonthLocks() {
  const { data } = await http.get('/system/month-locks')
  monthLocks.value = data
}

async function exportBackup() {
  const res = await http.get('/system/backup/export', { responseType: 'blob' })
  const url = window.URL.createObjectURL(res.data)
  const a = document.createElement('a')
  a.href = url
  a.download = 'accounting-backup.json'
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.URL.revokeObjectURL(url)
}

async function createServerBackup() {
  try {
    const { data } = await http.post('/system/backup/create')
      ElMessage.success(`备份完成：${data.backup_file}`)
      if (isSuper) await loadBackupFiles()
  } catch (err) {
    const detail = err?.response?.data?.detail
    const status = err?.response?.status
    ElMessage.error(detail ? `手动备份失败：${detail}` : `手动备份失败（HTTP ${status || '-'})`)
  }
}

async function loadBackupFiles() {
  if (!isSuper) return
  const { data } = await http.get('/system/backup/files')
  backupFiles.value = data
}

async function restoreBackup(file) {
  if (!isSuper) {
    ElMessage.warning('租户端不支持全库恢复')
    return false
  }
  const ok = await ElMessageBox.confirm('恢复会覆盖当前全部数据，确认继续？', '高风险操作', { type: 'warning' }).catch(() => null)
  if (!ok) return false
  restoring.value = true
  try {
    const fd = new FormData()
    fd.append('file', file.raw)
    await http.post('/system/backup/restore', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
    ElMessage.success('恢复完成')
    await loadBackupFiles()
  } finally {
    restoring.value = false
  }
  return false
}

async function restoreTenantBackup(file) {
  if (!auth.tenantId) {
    ElMessage.error('当前用户未绑定数据范围')
    return false
  }
  const ok = await ElMessageBox.confirm('恢复会覆盖当前用户的数据范围，确认继续？', '高风险操作', { type: 'warning' }).catch(() => null)
  if (!ok) return false
  restoring.value = true
  try {
    const fd = new FormData()
    fd.append('file', file.raw)
    await http.post('/system/backup/tenant-restore', fd, {
      params: { tenant_id: auth.tenantId },
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    ElMessage.success('当前用户数据恢复完成')
  } finally {
    restoring.value = false
  }
  return false
}

async function deleteBefore() {
  if (!form.before_date) {
    ElMessage.warning('请选择日期')
    return
  }
  const ok = await ElMessageBox.confirm(`确认删除 ${form.before_date} 之前的数据？`, '高风险操作', { type: 'warning' }).catch(() => null)
  if (!ok) return
  await http.post('/system/data/delete-before', null, { params: { before_date: form.before_date } })
  ElMessage.success('删除完成，已自动生成服务器备份')
  await loadBackupFiles()
}

async function deleteByDate() {
  if (!form.bill_date) {
    ElMessage.warning('请选择日期')
    return
  }
  const ok = await ElMessageBox.confirm(`确认删除 ${form.bill_date} 当天数据？`, '高风险操作', { type: 'warning' }).catch(() => null)
  if (!ok) return
  await http.post('/system/data/delete-by-date', null, { params: { bill_date: form.bill_date } })
  ElMessage.success('删除完成，已自动生成服务器备份')
  await loadBackupFiles()
}

async function lockMonth() {
  await http.post('/system/month-lock', null, { params: { year: form.lock_year, month: form.lock_month } })
  ElMessage.success('月账已锁定')
  await loadMonthLocks()
}

async function unlockMonth() {
  await http.delete('/system/month-lock', { params: { year: form.lock_year, month: form.lock_month } })
  ElMessage.success('月账已解锁')
  await loadMonthLocks()
}

async function downloadBackupFile(filename) {
  const res = await http.get(`/system/backup/files/${filename}`, { responseType: 'blob' })
  const url = window.URL.createObjectURL(res.data)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.URL.revokeObjectURL(url)
}

async function deleteBackupFile(filename) {
  if (!isSuper) return
  const ok = await ElMessageBox.confirm(`确认删除备份文件 ${filename} ?`, '提示', { type: 'warning' }).catch(() => null)
  if (!ok) return
  await http.delete(`/system/backup/files/${filename}`)
  ElMessage.success('备份文件已删除')
  await loadBackupFiles()
}

async function loadTenantHealth() {
  if (!isSuper) return
  const { data } = await http.get('/system/health/tenant-consistency')
  tenantHealth.value = data
}

loadMonthLocks()
loadBackupFiles()
if (isSuper) loadTenantHealth()
</script>

<template>
  <el-card>
    <template #header>系统工具</template>

    <el-alert :title="isSuper ? '以下操作请仅管理员使用' : '当前页面操作仅作用于当前用户的数据范围'" type="warning" show-icon style="margin-bottom: 12px" />

    <el-space wrap>
      <el-button type="success" @click="createServerBackup">手动备份到服务器</el-button>
      <el-button type="primary" @click="exportBackup">导出备份(JSON)</el-button>
      <el-upload v-if="isSuper" :show-file-list="false" :auto-upload="false" :on-change="restoreBackup">
        <el-button :loading="restoring" type="danger">恢复备份(JSON)</el-button>
      </el-upload>
      <el-upload v-else :show-file-list="false" :auto-upload="false" :on-change="restoreTenantBackup">
        <el-button :loading="restoring" type="danger">恢复当前用户(JSON)</el-button>
      </el-upload>
    </el-space>

    <el-table v-if="isSuper" :data="backupFiles" border style="margin-top: 12px">
      <el-table-column prop="filename" label="备份文件" />
      <el-table-column prop="size" label="大小(字节)" width="140" />
      <el-table-column prop="modified_at" label="修改时间" width="220" />
      <el-table-column label="操作" width="180">
        <template #default="{ row }">
          <el-button link type="primary" @click="downloadBackupFile(row.filename)">下载</el-button>
          <el-button link type="danger" @click="deleteBackupFile(row.filename)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-divider v-if="isSuper" />

    <el-card v-if="isSuper" shadow="never">
      <template #header>租户一致性检查</template>
      <el-space>
        <el-button type="primary" @click="loadTenantHealth">刷新检查</el-button>
        <span v-if="tenantHealth">租户{{ tenantHealth.tenant_count }}，异常用户绑定{{ tenantHealth.invalid_user_access }}，异常平台绑定{{ tenantHealth.invalid_platform_access }}，未绑定租户用户{{ tenantHealth.users_without_tenant }}</span>
      </el-space>
      <el-alert title="默认租户下线迁移脚本：backend/scripts/migrate_remove_default_tenant_template.py" :type="tenantHealth?.ok ? 'success' : 'warning'" show-icon style="margin-top: 10px" />
    </el-card>

    <el-divider />

    <el-form inline>
      <el-form-item label="删除某日前数据">
        <el-date-picker v-model="form.before_date" value-format="YYYY-MM-DD" />
      </el-form-item>
      <el-form-item>
        <el-button type="danger" @click="deleteBefore">执行删除</el-button>
      </el-form-item>
    </el-form>

    <el-form inline>
      <el-form-item label="删除某日数据">
        <el-date-picker v-model="form.bill_date" value-format="YYYY-MM-DD" />
      </el-form-item>
      <el-form-item>
        <el-button type="danger" @click="deleteByDate">执行删除</el-button>
      </el-form-item>
    </el-form>

    <el-divider />

    <el-form inline>
      <el-form-item label="锁账年份"><el-input-number v-model="form.lock_year" :min="2020" /></el-form-item>
      <el-form-item label="锁账月份"><el-input-number v-model="form.lock_month" :min="1" :max="12" /></el-form-item>
      <el-form-item>
        <el-button type="warning" @click="lockMonth">锁定该月</el-button>
        <el-button @click="unlockMonth">解锁该月</el-button>
      </el-form-item>
    </el-form>

    <el-table :data="monthLocks" border style="margin-top: 12px">
      <el-table-column prop="lock_month" label="月份" width="120" />
      <el-table-column label="状态" width="120">
        <template #default="{ row }">{{ row.is_locked ? '已锁定' : '未锁定' }}</template>
      </el-table-column>
      <el-table-column prop="locked_by" label="操作人ID" width="120" />
      <el-table-column prop="locked_at" label="操作时间" />
    </el-table>
  </el-card>
</template>
