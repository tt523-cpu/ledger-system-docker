<script setup>
import { reactive, ref } from 'vue'
import http from '../api/http'

const now = new Date()
const query = reactive({ year: now.getFullYear(), month: now.getMonth() + 1 })
const data = ref(null)
const detail = ref({ summary: { income: 0, expense: 0, net: 0 }, expense_items: [], account_balances: [] })

async function load() {
  const res = await http.get('/reports/monthly', { params: query })
  data.value = res.data
  const d = await http.get('/reports/monthly/detail', { params: query })
  detail.value = d.data
}

async function rebuild() {
  await http.post('/reports/monthly/rebuild', null, { params: query })
  await load()
}
</script>

<template>
  <el-card>
    <template #header>月度汇总</template>
    <el-form inline>
      <el-input-number v-model="query.year" :min="2020" />
      <el-input-number v-model="query.month" :min="1" :max="12" />
      <el-button @click="load">查询</el-button>
      <el-button type="primary" @click="rebuild">重算</el-button>
    </el-form>
    <el-descriptions v-if="data" :column="2" border style="margin-top:12px">
      <el-descriptions-item label="月份">{{ data.month }}</el-descriptions-item>
      <el-descriptions-item label="总充值">{{ data.total_income }}</el-descriptions-item>
      <el-descriptions-item label="总支出">{{ data.total_expense }}</el-descriptions-item>
      <el-descriptions-item label="净盈利">{{ data.net_profit }}</el-descriptions-item>
    </el-descriptions>

    <el-card style="margin-top:12px">
      <template #header>支出项目汇总</template>
      <el-table :data="detail.expense_items" border>
        <el-table-column prop="category_name" label="项目" />
        <el-table-column prop="amount" label="金额" />
      </el-table>
    </el-card>

    <el-card style="margin-top:12px">
      <template #header>各账户余额（本月）</template>
      <el-table :data="detail.account_balances" border>
        <el-table-column prop="payment_method_name" label="账户" />
        <el-table-column prop="channel_kind" label="通道类型" />
        <el-table-column prop="opening_balance" label="期初余额" />
        <el-table-column prop="income" label="本月收入" />
        <el-table-column prop="expense" label="本月支出" />
        <el-table-column prop="closing_balance" label="期末余额" />
      </el-table>
    </el-card>
  </el-card>
</template>
