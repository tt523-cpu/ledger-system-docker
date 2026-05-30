<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '../api/http'

const query = reactive({ page: 1, page_size: 20 })
const total = ref(0)
const items = ref([])

async function load() {
  const { data } = await http.get('/system/logs', { params: query })
  items.value = data.items
  total.value = data.total
}

async function clearAll() {
  await ElMessageBox.confirm('确认清空修改日志吗？该操作不可恢复。', '提示', { type: 'warning' })
  const { data } = await http.delete('/system/logs')
  ElMessage.success(`已清空 ${data.cleared || 0} 条修改日志`)
  query.page = 1
  await load()
}

onMounted(load)
</script>

<template>
  <el-card>
    <template #header>
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <span>修改日志</span>
        <el-button type="danger" @click="clearAll">清空日志</el-button>
      </div>
    </template>
    <el-table :data="items" border>
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column prop="user_id" label="用户" width="80" />
      <el-table-column prop="module" label="模块" width="120" />
      <el-table-column prop="action" label="操作" width="120" />
      <el-table-column prop="before_data" label="修改前" />
      <el-table-column prop="after_data" label="修改后" />
      <el-table-column prop="created_at" label="时间" width="180" />
    </el-table>
    <el-pagination style="margin-top:12px" background layout="prev, pager, next, total" :total="total" v-model:current-page="query.page" @current-change="load" />
  </el-card>
</template>
