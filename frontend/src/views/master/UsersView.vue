<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '../../api/http'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const form = reactive({ username: '', password: '', role: 'bookkeeper', status: 'enabled', tenant_id: null, platform_ids: [] })
const users = ref([])
const platforms = ref([])
const tenants = ref([])
const modules = ref([])
const roleModules = reactive({ super_admin: [], admin: [], bookkeeper: [], viewer: [] })
const canEditRoleModules = ref(false)

function isProtectedAdminRow(row) {
  return auth.role === 'admin' && row.role === 'admin'
}

async function load() {
  const tasks = [http.get('/master/users'), http.get('/master/platforms')]
  const loadTenants = auth.role === 'super_admin'
  const loadRolePerms = auth.role === 'super_admin' || auth.role === 'admin'
  if (loadTenants) tasks.push(http.get('/master/tenants'))
  if (loadRolePerms) tasks.push(http.get('/master/role-permissions'))
  const responses = await Promise.all(tasks)
  const u = responses[0]
  const p = responses[1]
  const t = loadTenants ? responses[2] : null
  const rp = loadRolePerms ? responses[responses.length - 1] : null
  users.value = (u.data || []).map((row) => ({
    ...row,
    platform_ids: row.platform_ids || (row.platform_id ? [row.platform_id] : []),
  }))
  platforms.value = p.data
  tenants.value = t?.data || []
  if (rp?.data) {
    canEditRoleModules.value = true
    modules.value = rp.data.modules || []
    roleModules.super_admin = [...(rp.data.role_modules?.super_admin || [])]
    roleModules.admin = [...(rp.data.role_modules?.admin || [])]
    roleModules.bookkeeper = [...(rp.data.role_modules?.bookkeeper || [])]
    roleModules.viewer = [...(rp.data.role_modules?.viewer || [])]
  }
}

async function saveRoleModules(role) {
  if (!canEditRoleModules.value) return
  await http.put(`/master/role-permissions/${role}`, { module_keys: roleModules[role] || [] })
  ElMessage.success('角色模块权限已保存')
}

async function createUser() {
  await http.post('/master/users', null, {
    params: {
      username: form.username,
      password: form.password,
      role: form.role,
      status: form.status,
      tenant_id: form.tenant_id,
      platform_ids: (form.platform_ids || []).join(','),
    },
  })
  ElMessage.success('创建成功')
  form.username = ''
  form.password = ''
  form.tenant_id = null
  form.platform_ids = []
  await load()
}

async function updateUser(row) {
  await http.put(`/master/users/${row.id}`, null, {
    params: {
      role: row.role,
      status: row.status,
      tenant_id: row.tenant_id,
      platform_ids: (row.platform_ids || []).join(','),
    },
  })
  if (auth.role === 'super_admin' && row.role !== 'super_admin') {
    await http.put(`/master/users/${row.id}/tenant-access`, {
      status: row.tenant_status || 'enabled',
      expire_at: row.tenant_expire_at || null,
    })
  }
  ElMessage.success('更新成功')
  await load()
}

async function removeUser(id) {
  await http.delete(`/master/users/${id}`)
  ElMessage.success('删除成功')
  await load()
}

async function resetPassword(row) {
  const ret = await ElMessageBox.prompt(`请输入 ${row.username} 的新密码`, '重置密码', {
    confirmButtonText: '确认',
    cancelButtonText: '取消',
    inputType: 'password',
    inputPattern: /^.{6,}$/,
    inputErrorMessage: '密码至少6位',
  }).catch(() => null)
  if (!ret) return
  await http.put(`/master/users/${row.id}/password`, null, { params: { new_password: ret.value } })
  ElMessage.success(`已重置 ${row.username} 密码`)
}

onMounted(load)
</script>

<template>
  <el-card>
    <template #header>用户管理</template>
    <el-alert
      v-if="auth.role === 'admin'"
      title="用户不能创建或设置管理员账号；如需管理员账号请联系客服。"
      type="info"
      show-icon
      style="margin-bottom: 10px"
    />
    <el-form inline>
      <el-form-item label="用户名"><el-input v-model="form.username" /></el-form-item>
      <el-form-item label="密码"><el-input v-model="form.password" type="password" /></el-form-item>
      <el-form-item label="角色">
        <el-select v-model="form.role" style="width: 140px">
          <el-option v-if="auth.role === 'super_admin'" value="super_admin" label="超级管理员" />
          <el-option v-if="auth.role === 'super_admin'" value="admin" label="管理员" />
          <el-option value="bookkeeper" label="记账员" />
          <el-option value="viewer" label="查看人员" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="auth.role === 'super_admin' && form.role !== 'super_admin'" label="所属租户">
        <el-select v-model="form.tenant_id" style="width: 180px">
          <el-option v-for="t in tenants" :key="t.id" :value="t.id" :label="t.name" />
        </el-select>
      </el-form-item>
      <el-form-item label="所属平台">
        <el-select v-model="form.platform_ids" multiple collapse-tags collapse-tags-tooltip style="width: 260px">
          <el-option v-for="p in platforms" :key="p.id" :value="p.id" :label="p.name" />
        </el-select>
      </el-form-item>
      <el-button type="primary" @click="createUser">新增用户</el-button>
    </el-form>
    <el-table :data="users" border>
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column prop="username" label="用户名" />
      <el-table-column label="角色">
        <template #default="{ row }">
          <el-select v-model="row.role" :disabled="isProtectedAdminRow(row)" style="width: 120px">
            <el-option v-if="auth.role === 'super_admin'" value="super_admin" label="超级管理员" />
            <el-option v-if="auth.role === 'super_admin'" value="admin" label="管理员" />
            <el-option value="bookkeeper" label="记账员" />
            <el-option value="viewer" label="查看人员" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column v-if="auth.role === 'super_admin'" label="所属租户">
        <template #default="{ row }">
          <el-select v-model="row.tenant_id" :disabled="row.role === 'super_admin'" style="width: 180px">
            <el-option v-for="t in tenants" :key="t.id" :value="t.id" :label="t.name" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column v-if="auth.role === 'super_admin'" label="租户到期">
        <template #default="{ row }">
          <el-date-picker
            v-model="row.tenant_expire_at"
            :disabled="row.role === 'super_admin'"
            type="datetime"
            value-format="YYYY-MM-DDTHH:mm:ss"
            placeholder="不过期"
            clearable
          />
        </template>
      </el-table-column>
      <el-table-column v-if="auth.role === 'super_admin'" label="租户状态">
        <template #default="{ row }">
          <el-select v-model="row.tenant_status" :disabled="row.role === 'super_admin'" style="width: 120px">
            <el-option value="enabled" label="启用" />
            <el-option value="disabled" label="停用" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="状态">
        <template #default="{ row }">
          <el-select v-model="row.status" :disabled="isProtectedAdminRow(row)" style="width: 120px">
            <el-option value="enabled" label="启用" />
            <el-option value="disabled" label="停用" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="所属平台">
        <template #default="{ row }">
          <el-select v-model="row.platform_ids" multiple collapse-tags collapse-tags-tooltip :disabled="isProtectedAdminRow(row)" style="width: 260px">
            <el-option v-for="p in platforms" :key="p.id" :value="p.id" :label="p.name" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="230">
        <template #default="{ row }">
          <el-button link type="primary" :disabled="isProtectedAdminRow(row)" @click="updateUser(row)">保存</el-button>
          <el-button link type="warning" @click="resetPassword(row)">重置密码</el-button>
          <el-button link type="danger" :disabled="isProtectedAdminRow(row)" @click="removeUser(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-divider v-if="canEditRoleModules" />
    <el-card v-if="canEditRoleModules">
      <template #header>角色模块权限（管理员可编辑）</template>
      <el-form label-width="120px">
        <el-form-item v-if="auth.role === 'super_admin'" label="超级管理员">
          <el-checkbox-group v-model="roleModules.super_admin">
            <el-checkbox v-for="m in modules" :key="`super-${m.key}`" :label="m.key">{{ m.label }}</el-checkbox>
          </el-checkbox-group>
          <el-button type="primary" style="margin-left: 8px" @click="saveRoleModules('super_admin')">保存超管权限</el-button>
        </el-form-item>
        <el-form-item label="管理员">
          <el-checkbox-group v-model="roleModules.admin">
            <el-checkbox v-for="m in modules" :key="`admin-${m.key}`" :label="m.key">{{ m.label }}</el-checkbox>
          </el-checkbox-group>
          <el-button type="primary" style="margin-left: 8px" @click="saveRoleModules('admin')">保存管理员权限</el-button>
        </el-form-item>
        <el-form-item label="记账员">
          <el-checkbox-group v-model="roleModules.bookkeeper">
            <el-checkbox v-for="m in modules" :key="`bookkeeper-${m.key}`" :label="m.key">{{ m.label }}</el-checkbox>
          </el-checkbox-group>
          <el-button type="primary" style="margin-left: 8px" @click="saveRoleModules('bookkeeper')">保存记账员权限</el-button>
        </el-form-item>
        <el-form-item label="查看人员">
          <el-checkbox-group v-model="roleModules.viewer">
            <el-checkbox v-for="m in modules" :key="`viewer-${m.key}`" :label="m.key">{{ m.label }}</el-checkbox>
          </el-checkbox-group>
          <el-button type="primary" style="margin-left: 8px" @click="saveRoleModules('viewer')">保存查看人员权限</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </el-card>
</template>
