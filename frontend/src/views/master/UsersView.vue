<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '../../api/http'

const form = reactive({ username: '', password: '', role: 'bookkeeper', status: 'enabled', platform_id: null })
const users = ref([])
const platforms = ref([])
const modules = ref([])
const roleModules = reactive({ admin: [], bookkeeper: [], viewer: [] })

async function load() {
  const [u, p, rp] = await Promise.all([http.get('/master/users'), http.get('/master/platforms'), http.get('/master/role-permissions')])
  users.value = u.data
  platforms.value = p.data
  modules.value = rp.data.modules || []
  roleModules.admin = [...(rp.data.role_modules?.admin || [])]
  roleModules.bookkeeper = [...(rp.data.role_modules?.bookkeeper || [])]
  roleModules.viewer = [...(rp.data.role_modules?.viewer || [])]
}

async function saveRoleModules(role) {
  await http.put(`/master/role-permissions/${role}`, { module_keys: roleModules[role] || [] })
  ElMessage.success('角色模块权限已保存')
}

async function createUser() {
  await http.post('/master/users', null, { params: form })
  ElMessage.success('创建成功')
  form.username = ''
  form.password = ''
  form.platform_id = null
  await load()
}

async function updateUser(row) {
  await http.put(`/master/users/${row.id}`, null, { params: { role: row.role, status: row.status, platform_id: row.platform_id } })
  ElMessage.success('更新成功')
  await load()
}

async function removeUser(id) {
  await http.delete(`/master/users/${id}`)
  ElMessage.success('删除成功')
  await load()
}

onMounted(load)
</script>

<template>
  <el-card>
    <template #header>用户管理</template>
    <el-form inline>
      <el-form-item label="用户名"><el-input v-model="form.username" /></el-form-item>
      <el-form-item label="密码"><el-input v-model="form.password" type="password" /></el-form-item>
      <el-form-item label="角色"><el-select v-model="form.role"><el-option value="admin" label="管理员" /><el-option value="bookkeeper" label="记账员" /><el-option value="viewer" label="查看人员" /></el-select></el-form-item>
      <el-form-item label="所属平台">
        <el-select v-model="form.platform_id" clearable style="width: 180px">
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
          <el-select v-model="row.role" style="width: 120px">
            <el-option value="admin" label="管理员" />
            <el-option value="bookkeeper" label="记账员" />
            <el-option value="viewer" label="查看人员" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="状态">
        <template #default="{ row }">
          <el-select v-model="row.status" style="width: 120px">
            <el-option value="enabled" label="启用" />
            <el-option value="disabled" label="停用" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="所属平台">
        <template #default="{ row }">
          <el-select v-model="row.platform_id" clearable style="width: 180px">
            <el-option v-for="p in platforms" :key="p.id" :value="p.id" :label="p.name" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160">
        <template #default="{ row }">
          <el-button link type="primary" @click="updateUser(row)">保存</el-button>
          <el-button link type="danger" @click="removeUser(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-divider />
    <el-card>
      <template #header>角色模块权限（管理员可编辑）</template>
      <el-form label-width="120px">
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
