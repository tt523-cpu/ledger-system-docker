<script setup>
import { onMounted } from 'vue'
import * as echarts from 'echarts'
import http from '../api/http'

async function load() {
  const trend = await http.get('/system/charts/income-expense-trend')
  const plat = await http.get('/system/charts/profit-by-platform')

  const t = echarts.init(document.getElementById('trend'))
  t.setOption({
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: trend.data.map((i) => i.date) },
    yAxis: { type: 'value' },
    series: [
      { name: '充值', type: 'line', data: trend.data.map((i) => i.income) },
      { name: '支出', type: 'line', data: trend.data.map((i) => i.expense) },
      { name: '净营业', type: 'line', data: trend.data.map((i) => i.net) },
    ],
  })

  const p = echarts.init(document.getElementById('platform'))
  p.setOption({
    xAxis: { type: 'category', data: plat.data.map((i) => `平台${i.platform_id}`) },
    yAxis: { type: 'value' },
    series: [{ type: 'bar', data: plat.data.map((i) => i.net) }],
  })
}

onMounted(load)
</script>

<template>
  <el-card>
    <template #header>图表分析</template>
    <div id="trend" style="height: 320px"></div>
    <div id="platform" style="height: 320px; margin-top: 12px"></div>
  </el-card>
</template>
