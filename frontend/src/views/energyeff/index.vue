<template>
  <section class="page" data-module="energyeff">
    <header class="page-head">
      <div>
        <h2>节能改造管理</h2>
        <p class="page-desc">按改造前后实测用电计算节电率，验收后按实际投资与节省的电费重算投资回收期，估算与实测偏差过大的项目会被标出。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记节能项目</button>
        <button class="btn" type="button" @click="exportRows">导出节能改造清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)" :class="{ 'row-abnormal': row.abnormal }">
          <td v-for="column in columns" :key="column">
            {{ row[column] ?? '—' }}
            <span v-if="column === '实测节电率' && row.abnormal" class="flag">偏差超限</span>
          </td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
            <button class="link" type="button" @click="openDetail(row)">详情</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无节能改造数据，可先登记节能项目</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条节能改造记录</span>
      <span v-if="infoMessage" class="info-text">{{ infoMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="acceptRow" class="modal-mask" @click.self="acceptRow = null">
      <div class="modal">
        <h3>验收评估 · {{ acceptRow.项目编号 }}</h3>
        <p class="modal-desc">录入验收实测数据，提交后按改造前后实测用电计算节电率并重算投资回收期。</p>
        <label v-for="field in acceptFields" :key="field.name" class="modal-item">
          <span>{{ field.label }}</span>
          <input v-model="acceptForm[field.name]" :placeholder="field.placeholder" />
        </label>
        <footer class="modal-foot">
          <button class="btn primary" type="button" @click="submitAccept">提交验收</button>
          <button class="btn ghost" type="button" @click="acceptRow = null">取消</button>
        </footer>
      </div>
    </div>

    <div v-if="detail" class="modal-mask" @click.self="detail = null">
      <div class="modal">
        <h3>验收结论 · {{ detail.项目编号 }}</h3>
        <dl class="detail-grid">
          <template v-for="field in detailFields" :key="field">
            <dt>{{ field }}</dt>
            <dd>{{ detail[field] ?? '—' }}</dd>
          </template>
        </dl>
        <p v-if="detail.偏差说明" class="deviation">{{ detail.偏差说明 }}</p>
        <h4>历史结论（留档）</h4>
        <table v-if="(detail.历史结论 ?? []).length" class="data-table">
          <thead>
            <tr><th>口径</th><th>节电率</th><th>投资回收期</th><th>归档时间</th></tr>
          </thead>
          <tbody>
            <tr v-for="(item, index) in detail.历史结论" :key="index">
              <td>{{ item.口径 }}</td>
              <td>{{ item.节电率 ?? '—' }}</td>
              <td>{{ item.投资回收期 ?? '—' }}</td>
              <td>{{ item.归档时间 }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="modal-desc">暂无历史结论。</p>
        <footer class="modal-foot">
          <button class="btn ghost" type="button" @click="detail = null">关闭</button>
        </footer>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, any>

const ENDPOINT = '/api/energyeff'
const columns = ["项目编号", "所属站点", "改造内容", "预估节电率", "实测节电率", "实际投资", "投资回收期", "项目状态"]
const actions = ["申请立项", "开始改造", "验收评估"]
const detailFields = ["项目编号", "所属站点", "改造内容", "承包单位", "项目状态", "预估节电率", "实测节电率", "基准期月均用电", "观察期月均用电", "电价", "投资金额", "实际投资", "年节省电费", "投资回收期", "验收时间"]
const acceptFields = [
  { name: '基准期月均用电', label: '基准期月均用电（kWh/月）', placeholder: '改造前基准期月均用电量' },
  { name: '观察期月均用电', label: '观察期月均用电（kWh/月）', placeholder: '验收连续观察期月均用电量' },
  { name: '实际投资', label: '实际投资（万元）', placeholder: '验收确认的实际投资' },
  { name: '电价', label: '电价（元/kWh）', placeholder: '用于折算节省电费' },
]

const rows = ref<Row[]>([])
const total = ref(0)
const stats = ref([{ label: '待立项项目', value: 0 }, { label: '改造中项目', value: 0 }, { label: '已验收项目', value: 0 }])
const errorMessage = ref('')
const infoMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const acceptRow = ref<Row | null>(null)
const acceptForm = ref<Record<string, string>>({})
const detail = ref<Row | null>(null)

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '节能项目登记入口尚未接入审批流'
}

function runAction(action: string, row: Row) {
  if (action === '验收评估') {
    acceptRow.value = row
    acceptForm.value = {
      基准期月均用电: row.基准期月均用电 ?? '',
      观察期月均用电: row.观察期月均用电 ?? '',
      实际投资: row.实际投资 ?? row.投资金额 ?? '',
      电价: row.电价 ?? '',
    }
    return
  }
  void submitAction(row, { action })
}

async function submitAccept() {
  const row = acceptRow.value
  if (!row) return
  const ok = await submitAction(row, { action: '验收评估', ...acceptForm.value })
  if (ok) acceptRow.value = null
}

async function submitAction(row: Row, values: Record<string, unknown>): Promise<boolean> {
  errorMessage.value = ''
  infoMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || payload.detail || '节能改造动作未生效，请稍后重试')
    }
    infoMessage.value = payload.message
    await Promise.all([reload(), loadStats(), refreshDetail(row.id)])
    return true
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '节能改造操作失败'
    return false
  }
}

async function openDetail(row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error('节能项目详情读取失败')
    }
    detail.value = await response.json()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '节能项目详情读取失败'
  }
}

async function refreshDetail(entryId: number) {
  if (detail.value && detail.value.id === entryId) {
    const response = await request(`${ENDPOINT}/${entryId}`)
    if (response.ok) {
      detail.value = await response.json()
    }
  }
}

async function loadStats() {
  try {
    const response = await request(`${ENDPOINT}?size=200`)
    if (!response.ok) return
    const payload = await response.json()
    const items: Row[] = payload.items ?? []
    const count = (status: string) => items.filter((item) => item.status === status).length
    stats.value = [
      { label: '待立项项目', value: count('待立项') },
      { label: '改造中项目', value: count('改造中') },
      { label: '已验收项目', value: count('已验收') },
    ]
  } catch {
    // 统计卡片失败不阻断列表
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('节能项目列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '节能改造列表读取失败'
  }
}

onMounted(() => {
  void reload()
  void loadStats()
})
</script>

<style scoped>
.row-abnormal td { background: #fef3f2; }
.flag { margin-left: 6px; font-size: 12px; color: #b42318; }
.info-text { color: #067647; }
.modal-mask { position: fixed; inset: 0; background: rgba(16, 24, 40, 0.4); display: flex; align-items: center; justify-content: center; z-index: 10; }
.modal { background: #fff; border-radius: 8px; padding: 16px 20px; width: 520px; max-height: 80vh; overflow: auto; }
.modal h3 { margin: 0 0 8px; font-size: 15px; }
.modal h4 { margin: 12px 0 6px; font-size: 13px; }
.modal-desc { color: var(--muted); font-size: 12px; margin: 0 0 10px; }
.modal-item { display: block; margin-bottom: 10px; }
.modal-item span { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; }
.modal-item input { width: 100%; padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px; }
.modal-foot { display: flex; gap: 8px; justify-content: flex-end; margin-top: 12px; }
.detail-grid { display: grid; grid-template-columns: 110px 1fr 110px 1fr; gap: 6px 10px; margin: 0; font-size: 13px; }
.detail-grid dt { color: var(--muted); }
.detail-grid dd { margin: 0; }
.deviation { color: #b42318; font-size: 13px; background: #fef3f2; border-radius: 6px; padding: 8px 10px; }
</style>
