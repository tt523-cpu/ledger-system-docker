<script setup>
import { onMounted, reactive, ref } from 'vue'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import http from '../api/http'

const tenants = ref([])
const rows = ref([])
const loading = ref(false)
const grandTotal = ref(0)
const form = reactive({ bill_date: dayjs().format('YYYY-MM-DD'), tenant_id: null })

async function loadTenants() {
  const { data } = await http.get('/master/tenants')
  tenants.value = data || []
}

async function query() {
  loading.value = true
  try {
    const { data } = await http.get('/reports/super/tenant-account-balances', {
      params: {
        bill_date: form.bill_date,
        tenant_id: form.tenant_id || undefined,
      },
    })
    rows.value = data.items || []
    grandTotal.value = Number(data.grand_total || 0)
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '查询失败')
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadTenants()
  await query()
})
</script>

<template>
  <el-card>
    <template #header>平台余额（超管）</template>
    <el-form inline @submit.prevent>
      <el-form-item label="截止日期"><el-date-picker v-model="form.bill_date" value-format="YYYY-MM-DD" /></el-form-item>
      <el-form-item label="租户">
        <el-select v-model="form.tenant_id" clearable style="width: 220px" placeholder="全部租户">
          <el-option v-for="t in tenants" :key="t.id" :label="t.name" :value="t.id" />
        </el-select>
      </el-form-item>
      <el-button type="primary" @click="query">查询</el-button>
    </el-form>

    <el-alert style="margin: 10px 0" type="success" :closable="false" :title="`全租户合计余额：${grandTotal.toFixed(2)}`" />

    <el-table :data="rows" border v-loading="loading" row-key="tenant_id">
      <el-table-column prop="tenant_id" label="租户ID" width="100" />
      <el-table-column prop="tenant_name" label="租户名称" width="180" />
      <el-table-column label="账户余额明细" min-width="520">
        <template #default="{ row }">
          <span v-for="(a, idx) in row.accounts" :key="`${row.tenant_id}-${a.payment_method_id}`">
            {{ a.payment_method_name }}: {{ Number(a.balance || 0).toFixed(2) }}<span v-if="idx < row.accounts.length - 1">，</span>
          </span>
        </template>
      </el-table-column>
      <el-table-column label="租户合计余额" width="180">
        <template #default="{ row }">{{ Number(row.tenant_total || 0).toFixed(2) }}</template>
      </el-table-column>
    </el-table>

    <div style="margin-top: 10px; text-align: right; font-size: 16px; color: #16a34a; font-weight: 600">
      所有租户余额合计：{{ grandTotal.toFixed(2) }}
    </div>
  </el-card>
</template>
