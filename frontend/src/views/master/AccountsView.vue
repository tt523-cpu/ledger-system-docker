<template>
  <SimpleMasterTable
    title="账户管理"
    endpoint="accounts"
    :fields="[{ key: 'name', label: '名称' }, { key: 'type', label: '类型' }, { key: 'initial_balance', label: '初始余额', type: 'number' }, { key: 'remark', label: '备注' }]"
    :defaults="{ name: '', type: 'cash', initial_balance: 0, status: 'enabled', remark: '' }"
  />
</template>

<script setup>
import SimpleMasterTable from '../../components/SimpleMasterTable.vue'
</script>
