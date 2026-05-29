<script setup>
import { reactive, ref } from 'vue'
import http from '../api/http'

const query = reactive({ bill_date: '', shift_id: null, platform_id: null })
const rows = ref([])

async function load() {
  const { data } = await http.get('/reports/daily', { params: query })
  rows.value = data
}

function exportDaily() {
  if (!query.bill_date) return
  const params = new URLSearchParams({ bill_date: query.bill_date })
  if (query.shift_id) params.append('shift_id', query.shift_id)
  if (query.platform_id) params.append('platform_id', query.platform_id)
  window.open(`/api/exports/daily-excel?${params.toString()}`, '_blank')
}
</script>

<template>
  <el-card>
    <template #header>每日结账</template>
    <el-form inline>
      <el-form-item label="日期"><el-date-picker v-model="query.bill_date" value-format="YYYY-MM-DD" /></el-form-item>
      <el-button type="primary" @click="load">查询</el-button>
      <el-button @click="exportDaily">导出Excel</el-button>
    </el-form>
    <el-table :data="rows" border>
      <el-table-column prop="bill_date" label="日期" />
      <el-table-column prop="shift_id" label="班次" />
      <el-table-column prop="platform_id" label="平台" />
      <el-table-column prop="total_income" label="充值" />
      <el-table-column prop="total_expense" label="支出" />
      <el-table-column prop="net_profit" label="净营业" />
    </el-table>
  </el-card>
</template>
