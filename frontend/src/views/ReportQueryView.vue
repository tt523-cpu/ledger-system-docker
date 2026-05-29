<script setup>
import { computed, reactive, ref } from 'vue'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import http from '../api/http'

const mode = ref('day')
const form = reactive({
  day: dayjs().format('YYYY-MM-DD'),
  week: dayjs().format('YYYY-MM-DD'),
  month: dayjs().format('YYYY-MM'),
  range: [dayjs().subtract(6, 'day').format('YYYY-MM-DD'), dayjs().format('YYYY-MM-DD')],
})

const rows = ref([])
const summary = ref({ income: 0, expense: 0, net: 0 })
const platformSummaries = ref([])
const lastQuery = ref({ start_date: '', end_date: '' })
const paymentBalances = ref([])
const handover = ref({ shifts: [] })
const confirmedInfo = ref({ confirmed: false })
const loading = ref(false)
const shifts = ref([])
const platforms = ref([])
const selectedShiftId = ref('')

const shiftNameMap = computed(() => {
  const m = new Map()
  for (const s of shifts.value) m.set(s.id, s.name)
  return m
})

const platformNameMap = computed(() => {
  const m = new Map()
  for (const p of platforms.value) m.set(p.id, p.name)
  return m
})

const channelSubtotals = computed(() => {
  const map = new Map()
  for (const row of paymentBalances.value) {
    const key = row.channel_kind || 'other'
    if (!map.has(key)) {
      map.set(key, { channel_kind: key, opening_balance: 0, recharge: 0, payout: 0, closing_balance: 0, payout_items: [] })
    }
    const item = map.get(key)
    item.opening_balance += Number(row.opening_balance || 0)
    item.recharge += Number(row.recharge || 0)
    item.payout += Number(row.payout || 0)
    item.closing_balance += Number(row.closing_balance || 0)
    for (const x of row.payout_items || []) {
      const found = item.payout_items.find((p) => p.name === x.name)
      if (found) {
        found.amount += Number(x.amount || 0)
      } else {
        item.payout_items.push({ name: x.name, amount: Number(x.amount || 0) })
      }
    }
  }
  for (const v of map.values()) {
    v.payout_display = v.payout_items.length
      ? v.payout_items.map((x) => `${x.name}:${Number(x.amount || 0).toFixed(2)}`).join('，')
      : '-'
  }
  return Array.from(map.values())
})

function paymentSummaryMethod({ columns, data }) {
  const sums = []
  columns.forEach((col, index) => {
    if (index === 0) {
      sums[index] = '总计'
      return
    }
    if (col.property === 'channel_kind') {
      sums[index] = '-'
      return
    }
    const val = data.reduce((acc, row) => acc + Number(row[col.property] || 0), 0)
    sums[index] = val.toFixed(2)
  })
  return sums
}

function getRange() {
  if (mode.value === 'day') {
    return { start_date: form.day, end_date: form.day }
  }
  if (mode.value === 'week') {
    const d = dayjs(form.week)
    return { start_date: d.startOf('week').format('YYYY-MM-DD'), end_date: d.endOf('week').format('YYYY-MM-DD') }
  }
  if (mode.value === 'month') {
    const d = dayjs(`${form.month}-01`)
    return { start_date: d.startOf('month').format('YYYY-MM-DD'), end_date: d.endOf('month').format('YYYY-MM-DD') }
  }
  return { start_date: form.range[0], end_date: form.range[1] }
}

async function search() {
  loading.value = true
  try {
    const params = getRange()
    if (selectedShiftId.value) params.shift_id = Number(selectedShiftId.value)
    const { data } = await http.get('/reports/query', { params })
    rows.value = data.items
    summary.value = data.summary
    platformSummaries.value = data.platform_summaries || []
    lastQuery.value = params

    if (mode.value === 'day') {
      const billDate = params.start_date
      const [pb, ho] = await Promise.all([
        http.get('/reports/payment-balances', { params: { bill_date: billDate } }),
        http.get('/reports/handover', { params: { bill_date: billDate } }),
      ])
      paymentBalances.value = pb.data
      handover.value = ho.data
      const cf = await http.get('/reports/handover/confirmed', { params: { bill_date: billDate } })
      confirmedInfo.value = cf.data
    } else {
      paymentBalances.value = []
      handover.value = { shifts: [] }
      confirmedInfo.value = { confirmed: false }
    }
  } finally {
    loading.value = false
  }
}

async function exportExcel() {
  if (!lastQuery.value.start_date) {
    ElMessage.warning('请先点查询，再导出')
    return
  }
  const q = new URLSearchParams(lastQuery.value).toString()
  await downloadFile(`/exports/report-query-excel?${q}`, `report-${lastQuery.value.start_date}-to-${lastQuery.value.end_date}.xlsx`)
}

async function loadShifts() {
  const { data } = await http.get('/master/shifts')
  shifts.value = data
}

async function loadPlatforms() {
  const { data } = await http.get('/master/platforms')
  platforms.value = data
}

loadShifts()
loadPlatforms()

async function exportHandover() {
  if (!lastQuery.value.start_date || lastQuery.value.start_date !== lastQuery.value.end_date) {
    ElMessage.warning('交班报表仅支持按天查询后导出')
    return
  }
  await downloadFile(`/exports/handover-excel?bill_date=${lastQuery.value.start_date}`, `handover-${lastQuery.value.start_date}.xlsx`)
}

async function downloadFile(url, filename) {
  const res = await http.get(url, { responseType: 'blob' })
  const ct = res.headers['content-type'] || ''
  if (ct.includes('application/json')) {
    const text = await res.data.text()
    try {
      const obj = JSON.parse(text)
      ElMessage.error(obj.detail || '导出失败')
    } catch {
      ElMessage.error('导出失败')
    }
    return
  }
  const blobUrl = window.URL.createObjectURL(res.data)
  const a = document.createElement('a')
  a.href = blobUrl
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.URL.revokeObjectURL(blobUrl)
}

async function confirmHandover() {
  if (!lastQuery.value.start_date || lastQuery.value.start_date !== lastQuery.value.end_date) {
    ElMessage.warning('请先按天查询后再确认交班')
    return
  }
  await http.post('/reports/handover/confirm', null, { params: { bill_date: lastQuery.value.start_date } })
  ElMessage.success('交班已确认并锁定快照')
  await search()
}
</script>

<template>
  <el-card>
    <template #header>报表查询</template>
    <el-form inline>
      <el-form-item label="查询方式">
        <el-select v-model="mode" style="width: 130px">
          <el-option value="day" label="按天" />
          <el-option value="week" label="按周" />
          <el-option value="month" label="按月" />
          <el-option value="custom" label="自定义" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="mode==='day'" label="日期"><el-date-picker v-model="form.day" value-format="YYYY-MM-DD" /></el-form-item>
      <el-form-item v-if="mode==='week'" label="任意日期"><el-date-picker v-model="form.week" value-format="YYYY-MM-DD" /></el-form-item>
      <el-form-item v-if="mode==='month'" label="月份"><el-date-picker v-model="form.month" type="month" value-format="YYYY-MM" /></el-form-item>
      <el-form-item v-if="mode==='custom'" label="日期范围"><el-date-picker v-model="form.range" type="daterange" value-format="YYYY-MM-DD" /></el-form-item>
      <el-form-item label="班次">
        <el-select v-model="selectedShiftId" style="width: 140px">
          <el-option value="" label="全天" />
          <el-option v-for="s in shifts" :key="s.id" :value="String(s.id)" :label="s.name" />
        </el-select>
      </el-form-item>
      <el-button type="primary" :loading="loading" @click="search">查询</el-button>
      <el-button @click="exportExcel">导出Excel</el-button>
      <el-button v-if="mode==='day'" type="success" @click="confirmHandover">确认交班</el-button>
      <el-button v-if="mode==='day'" @click="exportHandover">导出交班报表</el-button>
    </el-form>

    <el-alert
      v-if="mode==='day'"
      :title="confirmedInfo.confirmed ? `已交班：${confirmedInfo.confirmed_at || ''}` : '未交班：当前为实时数据'"
      :type="confirmedInfo.confirmed ? 'success' : 'warning'"
      show-icon
      style="margin-bottom: 10px"
    />

    <el-row :gutter="10" style="margin: 8px 0 12px">
      <el-col :span="8"><el-card>充值合计：{{ summary.income }}</el-card></el-col>
      <el-col :span="8"><el-card>支出合计：{{ summary.expense }}</el-card></el-col>
      <el-col :span="8"><el-card>净营业：{{ summary.net }}</el-card></el-col>
    </el-row>

    <el-card style="margin-bottom: 12px">
      <template #header>按平台汇总</template>
      <el-table :data="platformSummaries" border>
        <el-table-column prop="platform_name" label="平台" width="180" />
        <el-table-column prop="income" label="充值" />
        <el-table-column prop="expense" label="支出" />
        <el-table-column prop="net" label="净营业" />
      </el-table>
    </el-card>

    <el-table :data="rows" border>
      <el-table-column prop="bill_date" label="日期" width="130" />
      <el-table-column label="班次" width="120">
        <template #default="{ row }">{{ shiftNameMap.get(row.shift_id) || row.shift_id }}</template>
      </el-table-column>
      <el-table-column label="平台" width="160">
        <template #default="{ row }">{{ platformNameMap.get(row.platform_id) || `平台#${row.platform_id}` }}</template>
      </el-table-column>
      <el-table-column prop="total_income" label="充值" />
      <el-table-column label="支出" min-width="320">
        <template #default="{ row }">
          <span>{{ row.total_expense }}</span>
          <span v-if="Number(row.total_expense || 0) > 0">（{{ row.expense_display || '未关联项目' }}）</span>
        </template>
      </el-table-column>
      <el-table-column prop="net_profit" label="净营业" />
    </el-table>

    <el-card v-if="mode==='day'" style="margin-top: 12px">
      <template #header>账户余额（当日）</template>
      <el-table :data="paymentBalances" border show-summary :summary-method="paymentSummaryMethod">
        <el-table-column prop="payment_method_name" label="账户" />
        <el-table-column prop="channel_kind" label="通道类型" width="120" />
        <el-table-column prop="opening_balance" label="期初余额" />
        <el-table-column prop="recharge" label="充值" />
        <el-table-column label="支出" min-width="320">
          <template #default="{ row }">
            <span>{{ row.payout }}</span>
            <span v-if="Number(row.payout || 0) > 0">（{{ row.payout_display || '未关联项目' }}）</span>
          </template>
        </el-table-column>
        <el-table-column prop="closing_balance" label="期末余额" />
      </el-table>

      <el-table :data="channelSubtotals" border style="margin-top: 10px">
        <el-table-column prop="channel_kind" label="通道类型小计" width="180" />
        <el-table-column prop="opening_balance" label="期初小计" />
        <el-table-column prop="recharge" label="充值小计" />
        <el-table-column label="支出小计" min-width="320">
          <template #default="{ row }">
            <span>{{ row.payout }}</span>
            <span v-if="Number(row.payout || 0) > 0">（{{ row.payout_display || '未关联项目' }}）</span>
          </template>
        </el-table-column>
        <el-table-column prop="closing_balance" label="期末小计" />
      </el-table>
    </el-card>

    <el-card v-if="mode==='day'" style="margin-top: 12px">
      <template #header>交班营业报表（当日）</template>
      <el-table :data="handover.shifts || []" border>
        <el-table-column label="班次">
          <template #default="{ row }">{{ shiftNameMap.get(row.shift_id) || row.shift_id }}</template>
        </el-table-column>
        <el-table-column prop="recharge" label="充值" />
        <el-table-column label="支出" min-width="320">
          <template #default="{ row }">
            <span>{{ row.expense }}</span>
            <span v-if="Number(row.expense || 0) > 0">（{{ row.expense_display || '未关联项目' }}）</span>
          </template>
        </el-table-column>
        <el-table-column prop="turnover" label="营业额" />
      </el-table>
    </el-card>
  </el-card>
</template>
