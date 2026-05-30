<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '../api/http'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const activeTab = ref('audit')

const auditQuery = reactive({ page: 1, page_size: 20 })
const auditTotal = ref(0)
const auditItems = ref([])

const opQuery = reactive({ page: 1, page_size: 20, username: '', method: '', path_keyword: '' })
const opTotal = ref(0)
const opItems = ref([])

const canViewAudit = ref(false)
const canViewOperation = ref(false)

async function loadAudit() {
  const { data } = await http.get('/system/logs', { params: auditQuery })
  auditItems.value = data.items
  auditTotal.value = data.total
}

async function clearAudit() {
  await ElMessageBox.confirm('确认清空修改日志吗？该操作不可恢复。', '提示', { type: 'warning' })
  const { data } = await http.delete('/system/logs')
  ElMessage.success(`已清空 ${data.cleared || 0} 条修改日志`)
  auditQuery.page = 1
  await loadAudit()
}

async function loadOperation() {
  const params = {
    page: opQuery.page,
    page_size: opQuery.page_size,
    username: opQuery.username || undefined,
    method: opQuery.method || undefined,
    path_keyword: opQuery.path_keyword || undefined,
  }
  const { data } = await http.get('/system/operation-logs', { params })
  opItems.value = data.items
  opTotal.value = data.total
}

function searchOperation() {
  opQuery.page = 1
  loadOperation()
}

async function clearOperation() {
  await ElMessageBox.confirm('确认清空操作日志吗？该操作不可恢复。', '提示', { type: 'warning' })
  const { data } = await http.delete('/system/operation-logs')
  ElMessage.success(`已清空 ${data.cleared || 0} 条操作日志`)
  opQuery.page = 1
  await loadOperation()
}

onMounted(async () => {
  canViewAudit.value = auth.moduleKeys.includes('logs')
  canViewOperation.value = auth.moduleKeys.includes('operation.logs')
  if (canViewOperation.value) {
    activeTab.value = 'operation'
    await loadOperation()
  }
  if (canViewAudit.value) {
    activeTab.value = 'audit'
    await loadAudit()
  }
})
</script>

<template>
  <el-card>
    <template #header>日志中心</template>

    <el-tabs v-model="activeTab">
      <el-tab-pane v-if="canViewAudit" label="修改日志" name="audit">
        <div style="margin-bottom: 12px; display:flex; justify-content:flex-end;">
          <el-button type="danger" @click="clearAudit">清空日志</el-button>
        </div>
        <el-table :data="auditItems" border>
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column prop="user_id" label="用户" width="80" />
          <el-table-column prop="module" label="模块" width="120" />
          <el-table-column prop="action" label="操作" width="120" />
          <el-table-column prop="before_data" label="修改前" />
          <el-table-column prop="after_data" label="修改后" />
          <el-table-column prop="created_at" label="时间" width="180" />
        </el-table>
        <el-pagination
          style="margin-top:12px"
          background
          layout="prev, pager, next, total"
          :total="auditTotal"
          v-model:current-page="auditQuery.page"
          @current-change="loadAudit"
        />
      </el-tab-pane>

      <el-tab-pane v-if="canViewOperation" label="操作日志" name="operation">
        <div style="margin-bottom: 12px; display:flex; justify-content:space-between; gap: 12px; align-items:center;">
          <el-form inline>
            <el-form-item label="用户"><el-input v-model="opQuery.username" placeholder="用户名" /></el-form-item>
            <el-form-item label="方法">
              <el-select v-model="opQuery.method" clearable style="width: 120px">
                <el-option value="GET" label="GET" />
                <el-option value="POST" label="POST" />
                <el-option value="PUT" label="PUT" />
                <el-option value="DELETE" label="DELETE" />
                <el-option value="PATCH" label="PATCH" />
              </el-select>
            </el-form-item>
            <el-form-item label="路径"><el-input v-model="opQuery.path_keyword" placeholder="如 /reports" /></el-form-item>
            <el-button type="primary" @click="searchOperation">查询</el-button>
          </el-form>
          <el-button type="danger" @click="clearOperation">清空日志</el-button>
        </div>
        <el-table :data="opItems" border>
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column prop="username" label="用户" width="120" />
          <el-table-column prop="method" label="方法" width="90" />
          <el-table-column prop="path" label="路径" width="260" />
          <el-table-column prop="query_string" label="参数" />
          <el-table-column prop="status_code" label="状态" width="90" />
          <el-table-column prop="duration_ms" label="耗时ms" width="100" />
          <el-table-column prop="ip" label="IP" width="140" />
          <el-table-column prop="error_message" label="错误" />
          <el-table-column prop="created_at" label="时间" width="180" />
        </el-table>
        <el-pagination
          style="margin-top:12px"
          background
          layout="sizes, prev, pager, next, total"
          :total="opTotal"
          :page-size="opQuery.page_size"
          :page-sizes="[20,50,100]"
          v-model:current-page="opQuery.page"
          @current-change="loadOperation"
          @size-change="(v) => { opQuery.page_size = v; opQuery.page = 1; loadOperation() }"
        />
      </el-tab-pane>
    </el-tabs>
  </el-card>
</template>
