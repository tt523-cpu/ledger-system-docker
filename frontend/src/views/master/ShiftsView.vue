<template>
  <SimpleMasterTable
    title="班次管理"
    endpoint="shifts"
    :fields="[{ key: 'name', label: '名称' }, { key: 'start_time', label: '开始时间(HH:MM:SS)' }, { key: 'end_time', label: '结束时间(HH:MM:SS)' }, { key: 'sort_order', label: '排序', type: 'number' }]"
    :defaults="{ name: '', start_time: '08:00:00', end_time: '20:00:00', sort_order: 0, status: 'enabled' }"
  />
</template>

<script setup>
import SimpleMasterTable from '../../components/SimpleMasterTable.vue'
</script>
