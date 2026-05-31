<script setup>
import { onMounted, ref } from 'vue'
import http from '../api/http'

const data = ref({ today: {}, month: {}, trend7: [] })
let chart = null

async function getEcharts() {
  const mod = await import('echarts')
  return mod
}

async function load() {
  const res = await http.get('/reports/dashboard')
  data.value = res.data
  const echarts = await getEcharts()
  const el = document.getElementById('trend7')
  if (!el) return
  if (!chart) {
    chart = echarts.init(el)
  }
  chart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['充值', '支出', '净营业'] },
    xAxis: { type: 'category', data: data.value.trend7.map((i) => i.date) },
    yAxis: { type: 'value' },
    series: [
      { name: '充值', type: 'line', data: data.value.trend7.map((i) => i.income) },
      { name: '支出', type: 'line', data: data.value.trend7.map((i) => i.expense) },
      { name: '净营业', type: 'line', data: data.value.trend7.map((i) => i.net) },
    ],
  })
}

onMounted(load)
</script>

<template>
  <div>
    <el-row :gutter="12">
      <el-col :span="6"><el-card>今日充值：{{ data.today.income || 0 }}</el-card></el-col>
      <el-col :span="6"><el-card>今日支出：{{ data.today.expense || 0 }}</el-card></el-col>
      <el-col :span="6"><el-card>今日净营业：{{ data.today.net || 0 }}</el-card></el-col>
      <el-col :span="6"><el-card>本月净盈利：{{ data.month.net || 0 }}</el-card></el-col>
    </el-row>
    <el-card style="margin-top: 12px">
      <template #header>最近7天趋势</template>
      <div id="trend7" style="height: 360px"></div>
    </el-card>
  </div>
</template>
