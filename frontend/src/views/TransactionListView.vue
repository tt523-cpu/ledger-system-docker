<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import http from '../api/http'
import { useAuthStore } from '../stores/auth'

const typeLabelMap = {
  income: '充值',
  expense: '支出',
  adjust: '回冲',
  transfer: '转账',
}

const dateMode = ref('day')
const query = reactive({
  page: 1,
  page_size: 20,
  tx_type: 'all',
  category_id: 'all',
  keyword: '',
})
const dateForm = reactive({
  day: dayjs().format('YYYY-MM-DD'),
  week: dayjs().format('YYYY-MM-DD'),
  month: dayjs().format('YYYY-MM'),
  range: [dayjs().subtract(6, 'day').format('YYYY-MM-DD'), dayjs().format('YYYY-MM-DD')],
})
const total = ref(0)
const items = ref([])
const platforms = ref([])
const accounts = ref([])
const categories = ref([])
const entryTypes = ref([])
const auth = useAuthStore()
const editing = ref(false)
const saving = ref(false)
const editForm = reactive({ id: null, type: 'income', type_label: '充值', category_id: null, platform_id: null, amount: 0, remark: '' })
const viewportHeight = ref(window.innerHeight)

const tableHeight = computed(() => {
  if (viewportHeight.value < 760) return 360
  return Math.max(420, viewportHeight.value - 330)
})

function onResize() {
  viewportHeight.value = window.innerHeight
}

async function load() {
  const params = buildQueryParams()
  const { data } = await http.get('/transactions', { params })
  items.value = data.items
  total.value = data.total
}

function buildQueryParams() {
  const params = {
    page: query.page,
    page_size: query.page_size,
    tx_type: query.tx_type === 'all' ? undefined : query.tx_type,
    category_id: query.category_id === 'all' ? undefined : query.category_id,
    keyword: query.keyword || undefined,
  }

  if (dateMode.value === 'day') {
    params.bill_date = dateForm.day
    params.start_date = undefined
    params.end_date = undefined
    return params
  }

  if (dateMode.value === 'week') {
    const d = dayjs(dateForm.week)
    params.start_date = d.startOf('week').format('YYYY-MM-DD')
    params.end_date = d.endOf('week').format('YYYY-MM-DD')
    return params
  }

  if (dateMode.value === 'month') {
    const d = dayjs(`${dateForm.month}-01`)
    params.start_date = d.startOf('month').format('YYYY-MM-DD')
    params.end_date = d.endOf('month').format('YYYY-MM-DD')
    return params
  }

  params.start_date = dateForm.range?.[0] || undefined
  params.end_date = dateForm.range?.[1] || undefined
  return params
}

async function loadPlatforms() {
  const [p, a, c, et] = await Promise.all([
    http.get('/master/platforms'),
    http.get('/master/payment-methods'),
    http.get('/master/categories'),
    http.get('/master/entry-types'),
  ])
  platforms.value = p.data
  accounts.value = a.data
  categories.value = c.data
  entryTypes.value = (et.data || []).filter((x) => x.status === 'enabled')
}

function getPlatformName(id) {
  const row = platforms.value.find((p) => p.id === id)
  return row ? row.name : `平台#${id}`
}

function getAccountName(id) {
  if (!id) return '-'
  const row = accounts.value.find((a) => a.id === id)
  return row ? row.name : `账户#${id}`
}

function getCategoryName(id) {
  if (!id) return '-'
  const row = categories.value.find((c) => c.id === id)
  return row ? row.name : `项目#${id}`
}

function formatDateTime(v) {
  if (!v) return '-'
  return String(v).replace('T', ' ').slice(0, 19)
}

function onFilterChange() {
  query.page = 1
  load()
}

function onDateModeChange() {
  query.page = 1
}

function onSizeChange(size) {
  query.page_size = size
  query.page = 1
  load()
}

async function remove(id) {
  await http.delete(`/transactions/${id}`)
  ElMessage.success('删除成功')
  await load()
}

function startEdit(row) {
  editForm.id = row.id
  editForm.type = row.type
  editForm.type_label = row.biz_type_label || (row.type === 'income' ? '充值' : row.type === 'expense' ? '支出' : '回冲')
  editForm.category_id = row.category_id ?? null
  editForm.platform_id = row.platform_id
  editForm.amount = Number(row.amount)
  editForm.remark = row.remark || ''
  editing.value = true
}

function onEditTypeChange(typeId) {
  const t = entryTypes.value.find((x) => x.id === typeId)
  if (!t) return
  editForm.type = t.effect
  editForm.type_label = t.name
  if (editForm.type_label !== '支出') {
    editForm.category_id = null
  }
}

function editTypeRequiresCategory() {
  const t = entryTypes.value.find((x) => x.name === editForm.type_label && x.effect === editForm.type)
  return !!t?.requires_category
}

async function saveEdit() {
  if (!editForm.id) return
  saving.value = true
  try {
    const finalCategoryId = editTypeRequiresCategory() ? editForm.category_id : null
    await http.put(`/transactions/${editForm.id}`, {
      type: editForm.type,
      biz_type_label: editForm.type_label,
      category_id: finalCategoryId,
      platform_id: editForm.platform_id,
      amount: editForm.amount,
      remark: editForm.remark,
    })
    ElMessage.success('修改成功')
    editing.value = false
    await load()
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  window.addEventListener('resize', onResize)
  await Promise.all([load(), loadPlatforms()])
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
})
</script>

<template>
  <el-card>
    <template #header>流水查询</template>
    <el-form inline>
      <el-form-item label="日期方式">
        <el-select v-model="dateMode" style="width: 120px" @change="onDateModeChange">
          <el-option value="day" label="按天" />
          <el-option value="week" label="按周" />
          <el-option value="month" label="按月" />
          <el-option value="custom" label="自定义" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="dateMode==='day'" label="日期"><el-date-picker v-model="dateForm.day" value-format="YYYY-MM-DD" /></el-form-item>
      <el-form-item v-if="dateMode==='week'" label="任意日期"><el-date-picker v-model="dateForm.week" value-format="YYYY-MM-DD" /></el-form-item>
      <el-form-item v-if="dateMode==='month'" label="月份"><el-date-picker v-model="dateForm.month" type="month" value-format="YYYY-MM" /></el-form-item>
      <el-form-item v-if="dateMode==='custom'" label="日期范围"><el-date-picker v-model="dateForm.range" type="daterange" value-format="YYYY-MM-DD" /></el-form-item>
      <el-form-item label="类别">
        <el-select v-model="query.tx_type" style="width: 130px">
          <el-option value="all" label="全部" />
          <el-option value="income" label="收入" />
          <el-option value="expense" label="支出" />
          <el-option value="adjust" label="回冲" />
        </el-select>
      </el-form-item>
      <el-form-item label="项目">
        <el-select v-model="query.category_id" filterable style="width: 180px">
          <el-option value="all" label="全部" />
          <el-option v-for="c in categories" :key="c.id" :value="c.id" :label="c.name" />
        </el-select>
      </el-form-item>
      <el-form-item label="备注关键词"><el-input v-model="query.keyword" /></el-form-item>
      <el-button type="primary" @click="onFilterChange" class="primary-query-btn">查询</el-button>
    </el-form>

    <div class="table-scroll-wrap" data-hint="左右滑动查看更多列">
    <el-table :data="items" border :max-height="tableHeight">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="bill_date" label="日期" width="120" />
      <el-table-column label="录入时间" width="180">
        <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="平台" width="140">
        <template #default="{ row }">{{ getPlatformName(row.platform_id) }}</template>
      </el-table-column>
      <el-table-column label="账户" width="140">
        <template #default="{ row }">{{ getAccountName(row.payment_method_id) }}</template>
      </el-table-column>
      <el-table-column label="类型" width="120">
        <template #default="{ row }">{{ row.biz_type_label || typeLabelMap[row.type] || row.type }}</template>
      </el-table-column>
      <el-table-column label="项目" width="140">
        <template #default="{ row }">{{ getCategoryName(row.category_id) }}</template>
      </el-table-column>
      <el-table-column prop="amount" label="金额" width="120" />
      <el-table-column prop="remark" label="备注" />
      <el-table-column label="操作" width="170">
        <template #default="{ row }">
          <el-button link type="primary" @click="startEdit(row)">编辑</el-button>
          <el-button link type="danger" @click="remove(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    </div>
    <el-pagination
      style="margin-top:12px"
      background
      layout="sizes, prev, pager, next, total"
      :total="total"
      :page-size="query.page_size"
      :page-sizes="[10,20,30,50,100]"
      v-model:current-page="query.page"
      @current-change="load"
      @size-change="onSizeChange"
    />

    <el-dialog v-model="editing" title="编辑流水" width="420px">
      <el-form label-width="80px">
        <el-form-item label="类型">
          <el-select
            :model-value="entryTypes.find((x) => x.name === editForm.type_label && x.effect === editForm.type)?.id"
            style="width: 220px"
            @change="onEditTypeChange"
          >
            <el-option v-for="t in entryTypes" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="金额">
          <el-input-number v-model="editForm.amount" :min="0" :precision="2" inputmode="decimal" />
        </el-form-item>
        <el-form-item label="平台">
          <el-select v-model="editForm.platform_id" style="width: 220px">
            <el-option v-for="p in platforms" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="项目">
          <el-select v-model="editForm.category_id" :disabled="!editTypeRequiresCategory()" clearable filterable style="width: 220px">
            <el-option v-for="c in categories" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="editForm.remark" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editing = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>
