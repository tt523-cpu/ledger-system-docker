<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '../api/http'
import { useAuthStore } from '../stores/auth'

const shifts = ref([])
const platforms = ref([])
const categories = ref([])
const accounts = ref([])
const entryTypes = ref([])
const auth = useAuthStore()
const selectablePlatforms = ref([])
const importVisible = ref(false)
const importText = ref('')
const importPreview = ref([])
const importRawResult = ref('')
const aiParsing = ref(false)
const linePlatformMode = ref(false)

const form = reactive({
  bill_date: new Date().toISOString().slice(0, 10),
  shift_id: null,
  platform_id: null,
  lines: [{ type: 'income', type_label: '充值', platform_id: null, requires_category: false, category_id: null, amount: 0, payment_method_id: null, remark: '' }],
})

const showLinePlatform = computed(() => linePlatformMode.value || form.lines.some((line) => line.platform_id))

function createEmptyLine() {
  const firstType = entryTypes.value[0]
  return {
    type: firstType ? firstType.effect : 'income',
    type_label: firstType ? firstType.name : '充值',
    platform_id: null,
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

function normalizeName(v) {
  return String(v || '').trim().toLowerCase().replace(/\s+/g, '')
}

function findEntryType(text) {
  const key = normalizeName(text)
  return entryTypes.value.find((x) => normalizeName(x.name) === key)
    || entryTypes.value.find((x) => key.includes(normalizeName(x.name)) || normalizeName(x.name).includes(key))
}

function findCategory(text) {
  const key = normalizeName(text)
  return categories.value.find((x) => normalizeName(x.name) === key)
    || categories.value.find((x) => key.includes(normalizeName(x.name)) || normalizeName(x.name).includes(key))
}

function findAccount(text) {
  const key = normalizeName(text)
  return accounts.value.find((x) => normalizeName(x.name) === key)
    || accounts.value.find((x) => key.includes(normalizeName(x.name)) || normalizeName(x.name).includes(key))
}

function parseAmount(parts) {
  for (const part of parts) {
    const m = String(part || '').replace(/,/g, '').match(/-?\d+(?:\.\d+)?/)
    if (m && Number(m[0]) > 0) return Number(m[0])
  }
  return 0
}

async function parseImportText() {
  const rows = importText.value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
  const rawItems = []
  for (const raw of rows) {
    const parts = raw.split(/[\t,，|]+/).map((x) => x.trim())
    if (parts.length === 0) continue
    const amount = parseAmount(parts)
    if (!amount) continue
    rawItems.push({
      type_label: parts[0] || '',
      category_name: parts[1] || '',
      amount,
      payment_method_name: parts[3] || '',
      remark: parts[4] || raw,
      raw_type_label: parts[0] || '',
      raw_category_name: parts[1] || '',
      raw_payment_method_name: parts[3] || '',
    })
  }
  if (rawItems.length === 0) {
    ElMessage.warning('没有识别到可导入的金额行')
    return
  }
  try {
    const { data } = await http.post('/transactions/import/normalize', { items: rawItems })
    parseAIItems(data.items || [])
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '识别预览失败')
  }
}

function lineFromAIItem(item) {
  const entryType = item.type_label ? findEntryType(item.type_label) : null
  const category = item.category_name ? findCategory(item.category_name) : null
  const account = item.payment_method_name ? findAccount(item.payment_method_name) : null
  const line = {
    type: entryType ? entryType.effect : 'income',
    type_label: entryType ? entryType.name : '',
    raw_type_label: item.raw_type_label || item.type_label || '',
    platform_id: item.platform_id || null,
    raw_platform_name: item.raw_platform_name || item.platform_name || '',
    requires_category: entryType ? !!entryType.requires_category : false,
    category_id: category ? category.id : null,
    raw_category_name: item.raw_category_name || item.category_name || '',
    amount: Number(item.amount || 0),
    payment_method_id: account ? account.id : null,
    raw_payment_method_name: item.raw_payment_method_name || item.payment_method_name || '',
    remark: item.remark || '',
  }
  if (!line.requires_category) line.category_id = null
  return line
}

function parseAIItems(items, raw = '') {
  importRawResult.value = raw || ''
  importPreview.value = (items || []).map(lineFromAIItem).filter((line) => Number(line.amount || 0) > 0)
  if (importPreview.value.length === 0) {
    ElMessage.warning('AI没有整理出可导入的金额行')
  } else {
    ElMessage.success(`AI已整理 ${importPreview.value.length} 行，请核对预览`)
  }
}

async function aiParseImportText() {
  if (!importText.value.trim()) {
    ElMessage.warning('请先粘贴要整理的文字')
    return
  }
  aiParsing.value = true
  try {
    const { data } = await http.post('/transactions/import/ai-parse', { text: importText.value })
    parseAIItems(data.items || [])
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || 'AI整理失败')
  } finally {
    aiParsing.value = false
  }
}

async function beforeImportImage(file) {
  if (!file.type?.startsWith('image/')) {
    ElMessage.warning('请上传图片文件')
    return false
  }
  if (file.size > 8 * 1024 * 1024) {
    ElMessage.warning('图片不能超过8MB')
    return false
  }
  aiParsing.value = true
  try {
    const fd = new FormData()
    fd.append('image', file)
    const { data } = await http.post('/transactions/import/ai-parse-image', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 90000,
    })
    parseAIItems(data.items || [], data.raw || '')
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '图片AI识别失败')
  } finally {
    aiParsing.value = false
  }
  return false
}

function applyImport() {
  if (importPreview.value.length === 0) {
    ElMessage.warning('请先识别预览')
    return
  }
  if (importPreview.value.some((line) => !line.type_label)) {
    ElMessage.warning('还有未匹配的类型，请先选择类型')
    return
  }
  form.lines = importPreview.value.map((line) => ({ ...line }))
  linePlatformMode.value = true
  importVisible.value = false
  ElMessage.success(`已导入 ${form.lines.length} 行，请核对后保存`)
}

function onPreviewTypeChange(row, selectedId) {
  onTypeChange(row, selectedId)
}

function targetName(aliasType, targetId) {
  if (aliasType === 'platform') return selectablePlatforms.value.find((x) => x.id === targetId)?.name || ''
  if (aliasType === 'entry_type') return entryTypes.value.find((x) => x.id === targetId)?.name || ''
  if (aliasType === 'category') return categories.value.find((x) => x.id === targetId)?.name || ''
  if (aliasType === 'payment_method') return accounts.value.find((x) => x.id === targetId)?.name || ''
  return ''
}

async function rememberAlias(row, aliasType) {
  const config = {
    platform: { rawKey: 'raw_platform_name', targetKey: 'platform_id' },
    entry_type: { rawKey: 'raw_type_label', targetKey: 'type_label' },
    category: { rawKey: 'raw_category_name', targetKey: 'category_id' },
    payment_method: { rawKey: 'raw_payment_method_name', targetKey: 'payment_method_id' },
  }[aliasType]
  if (!config) return
  const aliasName = String(row[config.rawKey] || '').trim()
  if (!aliasName) {
    ElMessage.warning('没有可记住的原始值')
    return
  }
  let targetId = row[config.targetKey]
  if (aliasType === 'entry_type') {
    targetId = entryTypes.value.find((x) => x.name === row.type_label)?.id
  }
  if (!targetId) {
    ElMessage.warning('请先选择要匹配到的主数据')
    return
  }
  await http.post('/transactions/import-aliases', {
    alias_type: aliasType,
    alias_name: aliasName,
    target_id: targetId,
  })
  ElMessage.success(`已记住：${aliasName} -> ${targetName(aliasType, targetId)}`)
  for (const item of importPreview.value) {
    if (String(item[config.rawKey] || '').trim() !== aliasName) continue
    if (aliasType === 'entry_type') {
      onPreviewTypeChange(item, targetId)
    } else {
      item[config.targetKey] = targetId
    }
  }
}

function openImport() {
  importText.value = ''
  importPreview.value = []
  importRawResult.value = ''
  importVisible.value = true
}

function beforeImportFile(file) {
  const reader = new FileReader()
  reader.onload = () => {
    importText.value = String(reader.result || '')
    parseImportText()
  }
  reader.readAsText(file, 'utf-8')
  return false
}

async function loadMaster() {
  const [s, p, c, pm, et] = await Promise.allSettled([
    http.get('/master/shifts'),
    http.get('/master/platforms'),
    http.get('/master/categories'),
    http.get('/master/payment-methods'),
    http.get('/master/entry-types'),
  ])
  shifts.value = s.status === 'fulfilled' ? (s.value.data || []) : []
  platforms.value = p.status === 'fulfilled' ? (p.value.data || []) : []
  categories.value = c.status === 'fulfilled' ? (c.value.data || []) : []
  accounts.value = pm.status === 'fulfilled' ? (pm.value.data || []) : []
  entryTypes.value = et.status === 'fulfilled' ? ((et.value.data || []).filter((x) => x.status === 'enabled')) : []
  const allowedIds = new Set((auth.platformIds || []).map((x) => Number(x)))
  selectablePlatforms.value = auth.role === 'bookkeeper' && allowedIds.size > 0
    ? platforms.value.filter((x) => allowedIds.has(Number(x.id)))
    : platforms.value
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

  if (!form.platform_id && selectablePlatforms.value.length > 0) {
    form.platform_id = selectablePlatforms.value[0].id
  }
}

async function submit() {
  const validLines = form.lines
    .map((line) => ({ ...line }))
    .filter((line) => Number(line.amount || 0) > 0)

  if (validLines.length === 0) {
    ElMessage.warning('请至少填写一行金额大于0的流水')
    return
  }

  validLines.forEach((line) => {
    if (!line.requires_category) line.category_id = null
  })

  await http.post('/transactions/batch', {
    bill_date: form.bill_date,
    shift_id: form.shift_id,
    platform_id: form.platform_id,
    lines: validLines,
  })
  ElMessage.success('保存成功')
  form.lines = [createEmptyLine(), createEmptyLine()]
  linePlatformMode.value = false
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
      <el-form-item label="平台"><el-select v-model="form.platform_id" style="width: 180px"><el-option v-for="i in selectablePlatforms" :key="i.id" :value="i.id" :label="i.name" /></el-select></el-form-item>
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
      <el-table-column v-if="showLinePlatform" label="平台" width="180">
        <template #default="{ row }">
          <el-select v-model="row.platform_id" clearable placeholder="默认顶部平台">
            <el-option v-for="i in selectablePlatforms" :key="i.id" :value="i.id" :label="i.name" />
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
      <el-button @click="openImport">AI导入中心</el-button>
      <el-button type="primary" @click="submit">保存并继续</el-button>
    </div>

    <el-dialog v-model="importVisible" title="AI导入中心" width="1120px">
      <el-alert
        title="可上传图片让千问AI识别，也可以粘贴文字后AI整理。导入后请核对，再点击保存。"
        type="info"
        show-icon
        style="margin-bottom: 12px"
      />
      <div class="page-actions" style="margin-top: 0">
        <el-upload :before-upload="beforeImportImage" accept="image/*" :show-file-list="false">
          <el-button type="success" :loading="aiParsing">上传图片AI识别</el-button>
        </el-upload>
        <el-upload :before-upload="beforeImportFile" accept=".txt,.csv" :show-file-list="false">
          <el-button>上传TXT/CSV</el-button>
        </el-upload>
      </div>
      <el-input
        v-model="importText"
        type="textarea"
        :rows="8"
        placeholder="例如：充值,,3000,小羊,截图识别导入&#10;兑奖,回款,19800,小羊,回款19800"
      />
      <div class="page-actions">
        <el-button type="primary" @click="parseImportText">识别预览</el-button>
        <el-button type="success" :loading="aiParsing" @click="aiParseImportText">AI整理</el-button>
        <el-button :disabled="importPreview.length === 0" @click="applyImport">导入到表格</el-button>
      </div>
      <el-table v-if="importPreview.length" :data="importPreview" border style="margin-top: 10px">
        <el-table-column label="平台" width="210">
          <template #default="{ row }">
            <div class="import-match-cell">
              <el-select v-model="row.platform_id" clearable placeholder="未匹配" :class="{ 'is-unmatched': row.raw_platform_name && !row.platform_id }">
                <el-option v-for="i in selectablePlatforms" :key="i.id" :value="i.id" :label="i.name" />
              </el-select>
              <el-button v-if="row.raw_platform_name && row.platform_id" size="small" link type="primary" @click="rememberAlias(row, 'platform')">记住</el-button>
              <div v-if="row.raw_platform_name" class="raw-hint">原：{{ row.raw_platform_name }}</div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="180">
          <template #default="{ row }">
            <div class="import-match-cell">
              <el-select :model-value="entryTypes.find((x)=>x.name===row.type_label)?.id" placeholder="未匹配" :class="{ 'is-unmatched': row.raw_type_label && !row.type_label }" @change="(v)=>onPreviewTypeChange(row,v)">
                <el-option v-for="t in entryTypes" :key="t.id" :label="t.name" :value="t.id" />
              </el-select>
              <el-button v-if="row.raw_type_label && row.type_label" size="small" link type="primary" @click="rememberAlias(row, 'entry_type')">记住</el-button>
              <div v-if="row.raw_type_label" class="raw-hint">原：{{ row.raw_type_label }}</div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="项目" width="190">
          <template #default="{ row }">
            <div class="import-match-cell">
              <el-select v-model="row.category_id" clearable :disabled="!row.requires_category" :placeholder="row.requires_category ? '未匹配' : '-'" :class="{ 'is-unmatched': row.requires_category && row.raw_category_name && !row.category_id }">
                <el-option v-for="i in categories.filter((x) => x.type === 'expense')" :key="i.id" :value="i.id" :label="i.name" />
              </el-select>
              <el-button v-if="row.raw_category_name && row.category_id" size="small" link type="primary" @click="rememberAlias(row, 'category')">记住</el-button>
              <div v-if="row.raw_category_name" class="raw-hint">原：{{ row.raw_category_name }}</div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="amount" label="金额" width="120" />
        <el-table-column label="账户" width="210">
          <template #default="{ row }">
            <div class="import-match-cell">
              <el-select v-model="row.payment_method_id" clearable placeholder="未匹配" :class="{ 'is-unmatched': row.raw_payment_method_name && !row.payment_method_id }">
                <el-option v-for="i in accounts" :key="i.id" :value="i.id" :label="i.name" />
              </el-select>
              <el-button v-if="row.raw_payment_method_name && row.payment_method_id" size="small" link type="primary" @click="rememberAlias(row, 'payment_method')">记住</el-button>
              <div v-if="row.raw_payment_method_name" class="raw-hint">原：{{ row.raw_payment_method_name }}</div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="原始行" />
      </el-table>
      <el-alert
        v-if="!importPreview.length && importRawResult"
        title="AI已返回内容，但没有匹配成可导入流水，请查看原始结果"
        type="warning"
        show-icon
        style="margin-top: 10px"
      />
      <pre v-if="!importPreview.length && importRawResult" style="white-space: pre-wrap; max-height: 220px; overflow: auto; background: #f6f8fa; padding: 10px; border-radius: 4px">{{ importRawResult }}</pre>
    </el-dialog>
  </el-card>
</template>

<style scoped>
.import-match-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.raw-hint {
  color: #909399;
  font-size: 12px;
  line-height: 1.2;
}

:deep(.is-unmatched .el-select__wrapper) {
  box-shadow: 0 0 0 1px #f56c6c inset;
}
</style>
