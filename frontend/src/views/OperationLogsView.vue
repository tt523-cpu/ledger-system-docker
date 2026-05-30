<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '../api/http'

const query = reactive({ page: 1, page_size: 20, username: '', method: '', path_keyword: '' })
const total = ref(0)
const items = ref([])

async function load() {
  const params = {
    page: query.page,
    page_size: query.page_size,
    username: query.username || undefined,
    method: query.method || undefined,
    path_keyword: query.path_keyword || undefined,
  }
  const { data } = await http.get('/system/operation-logs', { params })
  items.value = data.items
  total.value = data.total
}

function search() {
  query.page = 1
  load()
}

async function clearAll() {
  await ElMessageBox.confirm('确认清空操作日志吗？该操作不可恢复。', '提示', { type: 'warning' })
  const { data } = await http.delete('/system/operation-logs')
  ElMessage.success(`已清空 ${data.cleared || 0} 条操作日志`)
  query.page = 1
  await load()
}

onMounted(load)
</script>

<template>
  <el-card>
    <template #header>
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <span>操作日志</span>
        <el-button type="danger" @click="clearAll">清空日志</el-button>
      </div>
    </template>
    <el-form inline>
      <el-form-item label="用户"><el-input v-model="query.username" placeholder="用户名" /></el-form-item>
      <el-form-item label="方法">
        <el-select v-model="query.method" clearable style="width: 120px">
          <el-option value="GET" label="GET" />
          <el-option value="POST" label="POST" />
          <el-option value="PUT" label="PUT" />
          <el-option value="DELETE" label="DELETE" />
          <el-option value="PATCH" label="PATCH" />
        </el-select>
      </el-form-item>
      <el-form-item label="路径"><el-input v-model="query.path_keyword" placeholder="如 /reports" /></el-form-item>
      <el-button type="primary" @click="search">查询</el-button>
    </el-form>
    <el-table :data="items" border style="margin-top: 12px">
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
      :total="total"
      :page-size="query.page_size"
      :page-sizes="[20,50,100]"
      v-model:current-page="query.page"
      @current-change="load"
      @size-change="(v) => { query.page_size = v; query.page = 1; load() }"
    />
  </el-card>
</template>
