<template>
  <SimpleMasterTable
    title="平台管理"
    endpoint="platforms"
    :fields="[{ key: 'name', label: '名称' }, { key: 'sort_order', label: '排序', type: 'number' }, { key: 'remark', label: '备注' }]"
    :defaults="{ name: '', sort_order: 0, status: 'enabled', remark: '' }"
  />
</template>

<script setup>
import SimpleMasterTable from '../../components/SimpleMasterTable.vue'
</script>
