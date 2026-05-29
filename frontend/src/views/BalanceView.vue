<script setup>
import { reactive, ref } from 'vue'
import http from '../api/http'

const query = reactive({ bill_date: '' })
const rows = ref([])
const shifts = ref([])
const selectedShiftId = ref('')
const accounts = ref([])
const selectedAccountId = ref('')

async function load() {
  const params = { bill_date: query.bill_date }
  if (selectedShiftId.value) params.shift_id = Number(selectedShiftId.value)
  if (selectedAccountId.value) params.payment_method_id = Number(selectedAccountId.value)
  const { data } = await http.get('/reports/payment-balances', { params })
  rows.value = data
}

async function loadShifts() {
  const { data } = await http.get('/master/shifts')
  shifts.value = data
}

async function loadAccounts() {
  const { data } = await http.get('/master/payment-methods')
  accounts.value = data
}

loadShifts()
loadAccounts()
</script>

<template>
  <el-card>
    <template #header>账户余额（按账户管理）</template>
    <el-form inline>
      <el-form-item label="日期"><el-date-picker v-model="query.bill_date" value-format="YYYY-MM-DD" /></el-form-item>
      <el-form-item label="班次">
        <el-select v-model="selectedShiftId" style="width: 140px">
          <el-option value="" label="全天" />
          <el-option v-for="s in shifts" :key="s.id" :value="String(s.id)" :label="s.name" />
        </el-select>
      </el-form-item>
      <el-form-item label="账户">
        <el-select v-model="selectedAccountId" clearable style="width: 180px" placeholder="全部账户">
          <el-option v-for="a in accounts" :key="a.id" :value="String(a.id)" :label="a.name" />
        </el-select>
      </el-form-item>
      <el-button @click="load">查询</el-button>
    </el-form>
    <el-table :data="rows" border>
      <el-table-column prop="payment_method_name" label="账户" />
      <el-table-column prop="channel_kind" label="通道类型" />
      <el-table-column prop="opening_balance" label="期初余额" />
      <el-table-column prop="recharge" label="充值" />
      <el-table-column prop="payout" label="支出" />
      <el-table-column prop="closing_balance" label="期末余额" />
    </el-table>
  </el-card>
</template>
