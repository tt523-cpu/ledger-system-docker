<script setup>
import { reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '../api/http'

const form = reactive({
  before_date: '',
  bill_date: '',
})
const restoring = ref(false)

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

async function restoreBackup(file) {
  const ok = await ElMessageBox.confirm('恢复会覆盖当前全部数据，确认继续？', '高风险操作', { type: 'warning' }).catch(() => null)
  if (!ok) return false
  restoring.value = true
  try {
    const fd = new FormData()
    fd.append('file', file.raw)
    await http.post('/system/backup/restore', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
    ElMessage.success('恢复完成')
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
  ElMessage.success('删除完成')
}

async function deleteByDate() {
  if (!form.bill_date) {
    ElMessage.warning('请选择日期')
    return
  }
  const ok = await ElMessageBox.confirm(`确认删除 ${form.bill_date} 当天数据？`, '高风险操作', { type: 'warning' }).catch(() => null)
  if (!ok) return
  await http.post('/system/data/delete-by-date', null, { params: { bill_date: form.bill_date } })
  ElMessage.success('删除完成')
}
</script>

<template>
  <el-card>
    <template #header>系统工具</template>

    <el-alert title="以下操作请仅管理员使用" type="warning" show-icon style="margin-bottom: 12px" />

    <el-space wrap>
      <el-button type="primary" @click="exportBackup">导出备份(JSON)</el-button>
      <el-upload :show-file-list="false" :auto-upload="false" :on-change="restoreBackup">
        <el-button :loading="restoring" type="danger">恢复备份(JSON)</el-button>
      </el-upload>
    </el-space>

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
  </el-card>
</template>
