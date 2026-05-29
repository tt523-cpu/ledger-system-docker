<template>
  <SimpleMasterTable
    title="项目管理"
    endpoint="categories"
    :fields="[{ key: 'name', label: '名称' }, { key: 'type', label: '类型' }, { key: 'sort_order', label: '排序', type: 'number' }]"
    :defaults="{ name: '', type: 'expense', affect_profit: true, affect_balance: true, sort_order: 0, status: 'enabled' }"
  />
</template>

<script setup>
import SimpleMasterTable from '../../components/SimpleMasterTable.vue'
</script>
