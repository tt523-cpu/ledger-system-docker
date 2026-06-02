<script setup>
import { onMounted, ref } from 'vue'
import http from '../api/http'

const selectedPlatformId = ref('all')
const platforms = ref([])
let trendChart = null
let platformChart = null

async function getEcharts() {
  const mod = await import('echarts')
  return mod
}

async function loadPlatforms() {
  const { data } = await http.get('/master/platforms')
  platforms.value = data
}

async function load() {
  const params = { platform_id: selectedPlatformId.value === 'all' ? undefined : Number(selectedPlatformId.value) }
  const trend = await http.get('/system/charts/income-expense-trend', { params })
  const plat = await http.get('/system/charts/profit-by-platform', { params })
  const echarts = await getEcharts()

  const trendEl = document.getElementById('trend')
  if (!trendEl) return
  if (!trendChart) {
    trendChart = echarts.init(trendEl)
  }
  trendChart.setOption({
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: trend.data.map((i) => i.date) },
    yAxis: { type: 'value' },
    series: [
      { name: '充值', type: 'line', data: trend.data.map((i) => i.income) },
      { name: '支出', type: 'line', data: trend.data.map((i) => i.expense) },
      { name: '净营业', type: 'line', data: trend.data.map((i) => i.net) },
    ],
  }, { notMerge: true })

  const platformEl = document.getElementById('platform')
  if (!platformEl) return
  if (!platformChart) {
    platformChart = echarts.init(platformEl)
  }
  platformChart.setOption({
    xAxis: { type: 'category', data: plat.data.map((i) => i.platform_name) },
    yAxis: { type: 'value' },
    series: [{ type: 'bar', data: plat.data.map((i) => i.net) }],
  }, { notMerge: true })
}

onMounted(async () => {
  await loadPlatforms()
  await load()
})
</script>

<template>
  <el-card>
    <template #header>图表分析</template>
    <el-form inline style="margin-bottom: 10px">
      <el-form-item label="平台">
        <el-select v-model="selectedPlatformId" style="width: 180px">
          <el-option value="all" label="全部平台" />
          <el-option v-for="p in platforms" :key="p.id" :value="String(p.id)" :label="p.name" />
        </el-select>
      </el-form-item>
      <el-button type="primary" @click="load">查询</el-button>
    </el-form>
    <div id="trend" style="height: 320px"></div>
    <div id="platform" style="height: 320px; margin-top: 12px"></div>
  </el-card>
</template>
