<script setup>
import { onMounted, reactive, ref } from 'vue'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import http from '../api/http'

const tenants = ref([])
const rows = ref([])
const summary = ref({ income: 0, expense: 0, net: 0 })
const loading = ref(false)
const form = reactive({
  date_mode: 'month',
  day: dayjs().format('YYYY-MM-DD'),
  week: dayjs().format('YYYY-MM-DD'),
  month: dayjs().format('YYYY-MM'),
  range: [dayjs().startOf('month').format('YYYY-MM-DD'), dayjs().format('YYYY-MM-DD')],
  tenant_id: null,
})

function buildDateParams() {
  if (form.date_mode === 'day') {
    return { start_date: form.day, end_date: form.day }
  }
  if (form.date_mode === 'week') {
    const d = dayjs(form.week)
    return { start_date: d.startOf('week').format('YYYY-MM-DD'), end_date: d.endOf('week').format('YYYY-MM-DD') }
  }
  if (form.date_mode === 'month') {
    const d = dayjs(`${form.month}-01`)
    return { start_date: d.startOf('month').format('YYYY-MM-DD'), end_date: d.endOf('month').format('YYYY-MM-DD') }
  }
  return { start_date: form.range?.[0] || undefined, end_date: form.range?.[1] || undefined }
}

async function loadTenants() {
  const { data } = await http.get('/master/tenants')
  tenants.value = data || []
}

async function query() {
  loading.value = true
  try {
    const { data } = await http.get('/reports/super/tenant-summary', {
      params: {
        ...buildDateParams(),
        tenant_id: form.tenant_id || undefined,
      },
    })
    rows.value = data.items || []
    summary.value = data.summary || { income: 0, expense: 0, net: 0 }
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '查询失败')
  } finally {
    loading.value = false
  }
}

async function exportExcel() {
  try {
    const dateParams = buildDateParams()
    const res = await http.get('/exports/super-tenant-summary-excel', {
      params: {
        ...dateParams,
        tenant_id: form.tenant_id || undefined,
      },
      responseType: 'blob',
    })
    const url = window.URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url
    a.download = 'super-tenant-summary.xlsx'
    document.body.appendChild(a)
    a.click()
    a.remove()
    window.URL.revokeObjectURL(url)
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '导出失败')
  }
}

onMounted(async () => {
  await loadTenants()
  await query()
})
</script>

<template>
  <el-card>
    <template #header>平台报表（超管）</template>
    <el-form inline @submit.prevent>
      <el-form-item label="日期方式">
        <el-select v-model="form.date_mode" style="width: 110px">
          <el-option value="day" label="按天" />
          <el-option value="week" label="按周" />
          <el-option value="month" label="按月" />
          <el-option value="custom" label="自定义" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="form.date_mode==='day'" label="日期"><el-date-picker v-model="form.day" value-format="YYYY-MM-DD" /></el-form-item>
      <el-form-item v-if="form.date_mode==='week'" label="任意日期"><el-date-picker v-model="form.week" value-format="YYYY-MM-DD" /></el-form-item>
      <el-form-item v-if="form.date_mode==='month'" label="月份"><el-date-picker v-model="form.month" type="month" value-format="YYYY-MM" /></el-form-item>
      <el-form-item v-if="form.date_mode==='custom'" label="日期范围"><el-date-picker v-model="form.range" type="daterange" value-format="YYYY-MM-DD" /></el-form-item>
      <el-form-item label="租户">
        <el-select v-model="form.tenant_id" clearable style="width: 220px" placeholder="全部租户">
          <el-option v-for="t in tenants" :key="t.id" :label="t.name" :value="t.id" />
        </el-select>
      </el-form-item>
      <el-button type="primary" native-type="button" :loading="loading" @click="query">查询</el-button>
      <el-button native-type="button" @click="exportExcel">导出Excel</el-button>
    </el-form>

    <el-alert
      style="margin: 10px 0"
      type="success"
      :closable="false"
      :title="`汇总：总收入 ${summary.income.toFixed(2)}，总支出 ${summary.expense.toFixed(2)}，净利润 ${summary.net.toFixed(2)}`"
    />

    <el-table :data="rows" border v-loading="loading">
      <el-table-column prop="tenant_id" label="租户ID" width="100" />
      <el-table-column prop="tenant_name" label="租户名称" min-width="180" />
      <el-table-column label="总收入" width="160">
        <template #default="{ row }">{{ Number(row.income || 0).toFixed(2) }}</template>
      </el-table-column>
      <el-table-column label="总支出" width="160">
        <template #default="{ row }">{{ Number(row.expense || 0).toFixed(2) }}</template>
      </el-table-column>
      <el-table-column label="净利润" width="160">
        <template #default="{ row }">{{ Number(row.net || 0).toFixed(2) }}</template>
      </el-table-column>
    </el-table>
  </el-card>
</template>
