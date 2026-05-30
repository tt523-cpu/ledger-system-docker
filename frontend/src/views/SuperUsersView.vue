<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '../api/http'

const form = reactive({ username: '', password: '', role: 'platform_viewer', status: 'enabled' })
const users = ref([])
const moduleOptions = [
  { key: 'master.tenants', label: '租户管理', module_keys: ['master.tenants'] },
  { key: 'super.users', label: '后台用户', module_keys: ['super.users'] },
  { key: 'super.reports', label: '平台报表', module_keys: ['reports.query', 'reports.monthly', 'reports.charts'] },
  { key: 'reports.balances', label: '平台余额', module_keys: ['reports.balances'] },
  { key: 'logs', label: '平台日志', module_keys: ['logs', 'operation.logs'] },
  { key: 'system.tools', label: '平台工具', module_keys: ['system.tools'] },
]
const roleModuleFlags = reactive({ super_admin: [], platform_viewer: [] })

function toFlags(moduleKeys) {
  const s = new Set(moduleKeys || [])
  return moduleOptions.filter((m) => m.module_keys.every((k) => s.has(k))).map((m) => m.key)
}

function toModuleKeys(flags) {
  const enabled = new Set(flags || [])
  const keys = []
  for (const m of moduleOptions) {
    if (!enabled.has(m.key)) continue
    keys.push(...m.module_keys)
  }
  return [...new Set(keys)]
}

async function load() {
  const [u, rp] = await Promise.all([http.get('/master/super-users'), http.get('/master/role-permissions')])
  users.value = u.data || []
  roleModuleFlags.super_admin = toFlags(rp.data?.role_modules?.super_admin || [])
  roleModuleFlags.platform_viewer = toFlags(rp.data?.role_modules?.platform_viewer || [])
}

async function saveRoleModules(role) {
  const moduleKeys = toModuleKeys(roleModuleFlags[role] || [])
  await http.put(`/master/role-permissions/${role}`, { module_keys: moduleKeys })
  ElMessage.success('模块权限已保存')
}

async function createUser() {
  await http.post('/master/super-users', null, { params: { ...form } })
  ElMessage.success('新增成功')
  form.username = ''
  form.password = ''
  form.role = 'platform_viewer'
  form.status = 'enabled'
  await load()
}

async function saveUser(row) {
  await http.put(`/master/super-users/${row.id}`, null, { params: { role: row.role, status: row.status } })
  ElMessage.success('保存成功')
  await load()
}

async function resetPassword(row) {
  const ret = await ElMessageBox.prompt(`请输入 ${row.username} 新密码`, '重置密码', {
    inputType: 'password',
    inputPattern: /^.{6,}$/,
    inputErrorMessage: '至少6位',
  }).catch(() => null)
  if (!ret) return
  await http.put(`/master/users/${row.id}/password`, null, { params: { new_password: ret.value } })
  ElMessage.success('已重置')
}

async function removeUser(row) {
  const ok = await ElMessageBox.confirm(`确认删除用户 ${row.username} ?`, '提示', { type: 'warning' }).catch(() => null)
  if (!ok) return
  try {
    await http.delete(`/master/super-users/${row.id}`)
    ElMessage.success('删除成功')
    await load()
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '删除失败')
  }
}

onMounted(load)
</script>

<template>
  <el-card>
    <template #header>后台用户管理</template>
    <el-form inline>
      <el-form-item label="用户名"><el-input v-model="form.username" /></el-form-item>
      <el-form-item label="密码"><el-input v-model="form.password" type="password" /></el-form-item>
      <el-form-item label="角色">
        <el-select v-model="form.role" style="width: 160px">
          <el-option value="platform_viewer" label="平台查看员" />
          <el-option value="super_admin" label="超级管理员" />
        </el-select>
      </el-form-item>
      <el-button type="primary" @click="createUser">新增用户</el-button>
    </el-form>

    <el-table :data="users" border>
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column prop="username" label="用户名" />
      <el-table-column label="角色" width="180">
        <template #default="{ row }">
          <el-select v-model="row.role" style="width: 160px">
            <el-option value="platform_viewer" label="平台查看员" />
            <el-option value="super_admin" label="超级管理员" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="120">
        <template #default="{ row }">
          <el-select v-model="row.status" style="width: 100px">
            <el-option value="enabled" label="启用" />
            <el-option value="disabled" label="停用" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="260">
        <template #default="{ row }">
          <el-button link type="primary" @click="saveUser(row)">保存</el-button>
          <el-button link type="warning" @click="resetPassword(row)">重置密码</el-button>
          <el-button link type="danger" @click="removeUser(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-divider />
    <el-card>
      <template #header>模块权限配置</template>
      <el-form label-width="120px">
        <el-form-item label="超级管理员">
          <el-checkbox-group v-model="roleModuleFlags.super_admin">
            <el-checkbox v-for="m in moduleOptions" :key="`super-${m.key}`" :label="m.key">{{ m.label }}</el-checkbox>
          </el-checkbox-group>
          <el-button type="primary" style="margin-left: 8px" @click="saveRoleModules('super_admin')">保存超管权限</el-button>
        </el-form-item>
        <el-form-item label="平台查看员">
          <el-checkbox-group v-model="roleModuleFlags.platform_viewer">
            <el-checkbox v-for="m in moduleOptions" :key="`viewer-${m.key}`" :label="m.key">{{ m.label }}</el-checkbox>
          </el-checkbox-group>
          <el-button type="primary" style="margin-left: 8px" @click="saveRoleModules('platform_viewer')">保存查看员权限</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </el-card>
</template>
