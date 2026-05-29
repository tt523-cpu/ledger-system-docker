<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '../api/http'
import { useAuthStore } from '../stores/auth'

const shifts = ref([])
const platforms = ref([])
const categories = ref([])
const accounts = ref([])
const entryTypes = ref([])
const auth = useAuthStore()

const form = reactive({
  bill_date: new Date().toISOString().slice(0, 10),
  shift_id: null,
  platform_id: null,
  lines: [{ type: 'income', type_label: '充值', requires_category: false, category_id: null, amount: 0, payment_method_id: null, remark: '' }],
})

function createEmptyLine() {
  const firstType = entryTypes.value[0]
  return {
    type: firstType ? firstType.effect : 'income',
    type_label: firstType ? firstType.name : '充值',
    requires_category: firstType ? !!firstType.requires_category : false,
    category_id: null,
    amount: 0,
    payment_method_id: null,
    remark: '',
  }
}

function addRow() {
  form.lines.push(createEmptyLine())
}

async function loadMaster() {
  const [s, p, c, pm, et] = await Promise.all([
    http.get('/master/shifts'),
    http.get('/master/platforms'),
    http.get('/master/categories'),
    http.get('/master/payment-methods'),
    http.get('/master/entry-types'),
  ])
  shifts.value = s.data
  platforms.value = p.data
  categories.value = c.data
  accounts.value = pm.data
  entryTypes.value = et.data.filter((x) => x.status === 'enabled')
  if (entryTypes.value.length > 0 && form.lines.length > 0 && !form.lines[0].type_label) {
    form.lines[0].type_label = entryTypes.value[0].name
    form.lines[0].type = entryTypes.value[0].effect
    form.lines[0].requires_category = !!entryTypes.value[0].requires_category
  }

  if (!form.shift_id && shifts.value.length > 0) {
    const now = new Date()
    const nowSec = now.getHours() * 3600 + now.getMinutes() * 60 + now.getSeconds()
    const parseTime = (t) => {
      if (!t || typeof t !== 'string') return null
      const parts = t.split(':').map((n) => Number(n))
      if (parts.length < 2 || Number.isNaN(parts[0]) || Number.isNaN(parts[1])) return null
      const h = parts[0]
      const m = parts[1]
      const s = parts[2] || 0
      return h * 3600 + m * 60 + s
    }
    const inRange = (start, end, sec) => {
      if (start === null || end === null) return false
      if (start <= end) return sec >= start && sec < end
      return sec >= start || sec < end
    }
    const matched = shifts.value.find((x) => inRange(parseTime(x.start_time), parseTime(x.end_time), nowSec))
    form.shift_id = matched ? matched.id : shifts.value[0].id
  }

  if (auth.role === 'bookkeeper' && auth.platformId) {
    form.platform_id = auth.platformId
  } else if (!form.platform_id && platforms.value.length > 0) {
    form.platform_id = platforms.value[0].id
  }
}

async function submit() {
  form.lines.forEach((line) => {
    if (!line.requires_category) line.category_id = null
  })
  await http.post('/transactions/batch', form)
  ElMessage.success('保存成功')
  form.lines = [createEmptyLine(), createEmptyLine()]
}

function onTypeChange(row, selectedId) {
  const t = entryTypes.value.find((x) => x.id === selectedId)
  if (!t) return
  row.type = t.effect
  row.type_label = t.name
  row.requires_category = !!t.requires_category
  if (!row.requires_category) row.category_id = null
}

onMounted(loadMaster)
</script>

<template>
  <el-card>
    <template #header>流水录入（多笔）</template>
    <el-form inline>
      <el-form-item label="日期"><el-date-picker v-model="form.bill_date" value-format="YYYY-MM-DD" /></el-form-item>
      <el-form-item label="班次"><el-select v-model="form.shift_id" style="width: 140px"><el-option v-for="i in shifts" :key="i.id" :value="i.id" :label="i.name" /></el-select></el-form-item>
      <el-form-item v-if="auth.role !== 'bookkeeper'" label="平台"><el-select v-model="form.platform_id" style="width: 180px"><el-option v-for="i in platforms" :key="i.id" :value="i.id" :label="i.name" /></el-select></el-form-item>
    </el-form>

    <div class="table-scroll-wrap" data-hint="左右滑动查看更多列">
    <el-table :data="form.lines" border>
      <el-table-column label="类型" width="160">
        <template #default="{ row }">
          <el-select :model-value="entryTypes.find((x)=>x.name===row.type_label)?.id" @change="(v)=>onTypeChange(row,v)">
            <el-option v-for="t in entryTypes" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="项目" width="210">
        <template #default="{ row }">
          <el-select
            v-model="row.category_id"
            :disabled="!row.requires_category"
            :placeholder="row.requires_category ? '请选择项目' : '-'"
          >
            <el-option v-for="i in categories.filter((x) => x.type === 'expense')" :key="i.id" :value="i.id" :label="i.name" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="金额" width="140">
        <template #default="{ row }"><el-input-number v-model="row.amount" :min="0" :precision="2" inputmode="decimal" /></template>
      </el-table-column>
      <el-table-column label="账户" width="180">
        <template #default="{ row }"><el-select v-model="row.payment_method_id" placeholder="选择账户"><el-option v-for="i in accounts" :key="i.id" :value="i.id" :label="i.name" /></el-select></template>
      </el-table-column>
      <el-table-column label="备注">
        <template #default="{ row }"><el-input v-model="row.remark" /></template>
      </el-table-column>
    </el-table>
    </div>
    <div class="page-actions">
      <el-button @click="addRow">新增一行</el-button>
      <el-button type="primary" @click="submit">保存并继续</el-button>
    </div>
  </el-card>
</template>
