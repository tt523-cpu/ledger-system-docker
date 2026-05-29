<script setup>
import { reactive } from 'vue'

const now = new Date()
const query = reactive({ year: now.getFullYear(), month: now.getMonth() + 1 })

function download() {
  const url = `/api/exports/excel?year=${query.year}&month=${query.month}`
  window.open(url, '_blank')
}
</script>

<template>
  <el-card>
    <template #header>Excel 导出</template>
    <el-form inline>
      <el-input-number v-model="query.year" :min="2020" />
      <el-input-number v-model="query.month" :min="1" :max="12" />
      <el-button type="primary" @click="download">导出</el-button>
    </el-form>
  </el-card>
</template>
