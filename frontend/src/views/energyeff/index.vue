<template>
  <section class="page" data-module="energyeff">
    <header class="page-head">
      <div>
        <h2>节能改造管理</h2>
        <p class="page-desc">
          节电率一律按改造前后实测用电计算：改造前取基准期、验收取连续观察期；
          投资回收期按实际投资与节省电费重算，立项预估与实测偏差超 10 个百分点自动标红说明。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记节能项目</button>
        <button class="btn" type="button" @click="exportRows">导出节能改造清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value" :class="{ 'warn-value': item.label === '偏差超限项目' && item.value > 0 }">
          {{ item.value }}
        </strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>项目编号</span>
        <input v-model="keyword" placeholder="按项目编号检索" />
      </label>
      <label class="filter-item">
        <span>项目状态</span>
        <select v-model="status">
          <option value="">全部状态</option>
          <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
        </select>
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
        <tr v-for="row in rows" :key="String(row.id)" :class="{ 'abnormal-row': row['偏差超限'] }">
          <td v-for="column in columns" :key="column">
            <RouterLink v-if="column === '项目编号'" class="link" :to="`/energyeff/${row.id}`">
              {{ row[column] ?? '—' }}
            </RouterLink>
            <span v-else :class="{ 'cell-warn': column === '实测节电率' && row['偏差超限'] }">
              {{ column === '实测节电率' ? (row['实测节电率'] ?? '待验收') : (row[column] ?? '—') }}
            </span>
          </td>
          <td class="row-actions">
            <template v-for="action in availableActions(row.status)" :key="action">
              <button v-if="action !== '验收评估'" class="link" type="button" @click="runAction(action, row)">
                {{ action }}
              </button>
              <RouterLink v-else class="link" :to="`/energyeff/${row.id}/accept`">验收评估</RouterLink>
            </template>
            <span v-if="row.status === '已验收'" class="muted-text">验收已锁定</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无节能改造数据，可先登记节能项目</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条节能改造记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="creating" class="modal-mask" @click.self="creating = false">
      <form class="modal-card" @submit.prevent="submitCreate">
        <h3>登记节能项目</h3>
        <p class="modal-hint">立项阶段只登记预估数；节电率与回收期以验收时的实测数据为准。</p>
        <label v-for="field in createFields" :key="field.name" class="modal-field">
          <span>{{ field.label }}<i v-if="field.required">*</i></span>
          <input
            v-model="createForm[field.name]"
            :type="field.type ?? 'text'"
            :placeholder="field.placeholder ?? ''"
            :step="field.type === 'number' ? '0.01' : undefined"
          />
        </label>
        <div class="modal-actions">
          <button class="btn" type="button" @click="creating = false">取消</button>
          <button class="btn primary" type="submit">登记</button>
        </div>
        <p v-if="createError" class="error-text">{{ createError }}</p>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>

const ENDPOINT = '/api/energyeff'
const columns = [
  '项目编号', '所属站点', '改造内容', '预估节电率', '实测节电率',
  '投资金额', '实际投资', '承包单位', '投资回收期', '项目状态',
]
const statuses = ['待立项', '改造中', '评估中', '已验收']

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const keyword = ref('')
const status = ref('')
const stats = ref([
  { label: '待立项项目', value: 0 },
  { label: '改造/评估中项目', value: 0 },
  { label: '已验收项目', value: 0 },
  { label: '偏差超限项目', value: 0 },
])

const creating = ref(false)
const createError = ref('')
interface CreateField {
  name: string
  label: string
  required?: boolean
  type?: string
  placeholder?: string
}

const createFields: CreateField[] = [
  { name: '项目编号', label: '项目编号', required: true },
  { name: '所属站点', label: '所属站点', required: true },
  { name: '改造内容', label: '改造内容', required: true },
  { name: '预估节电率', label: '预估节电率（%）', placeholder: '如 25 或 25%' },
  { name: '投资金额', label: '立项投资金额（元）', type: 'number' },
  { name: '承包单位', label: '承包单位' },
]
const createForm = reactive<Record<string, string>>({})

function availableActions(rowStatus: unknown): string[] {
  switch (rowStatus) {
    case '待立项':
      return ['申请立项']
    case '改造中':
      return ['开始改造']
    case '评估中':
      return ['验收评估']
    default:
      return []
  }
}

function resetFilters() {
  keyword.value = ''
  status.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  createError.value = ''
  for (const field of createFields) createForm[field.name] = ''
  creating.value = true
}

async function submitCreate() {
  createError.value = ''
  const payload: Record<string, string | number> = { ...createForm }
  const investment = createForm['投资金额']
  if (investment !== '') payload['投资金额'] = Number(investment)
  try {
    const response = await request(ENDPOINT, { method: 'POST', body: JSON.stringify({ values: payload }) })
    const result = await response.json()
    if (!result.ok) {
      createError.value = result.message ?? '节能项目登记失败'
      return
    }
    creating.value = false
    await reload()
  } catch (error) {
    createError.value = error instanceof Error ? error.message : '节能项目登记失败'
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  // 开始改造时留基准期用电：没有基准期数据就先问出来，保证验收一定有改造前口径；
  // 已经留过基准期的（如改造中的老数据）直接推进，不再允许改数。
  let body: Record<string, unknown> = { action }
  if (action === '开始改造' && row['基准期用电'] == null) {
    const answer = window.prompt('请输入改造前基准期用电（度）与基准期天数，用逗号分隔，如：9600,30')
    if (answer === null) return
    const [baseline, days] = answer.split(',').map((part) => part.trim())
    if (!baseline || !days || Number(baseline) <= 0 || Number(days) <= 0) {
      errorMessage.value = '基准期用电与天数都必须是大于 0 的数字'
      return
    }
    body = { action, 基准期用电: Number(baseline), 基准期天数: Number(days) }
  }
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: body }),
    })
    const result = await response.json()
    if (!result.ok) {
      errorMessage.value = result.message ?? '节能改造动作未生效'
      return
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '节能改造操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (keyword.value) query.set('keyword', keyword.value)
  if (status.value) query.set('status', status.value)
  try {
    const [listResponse, statsResponse] = await Promise.all([
      request(`${ENDPOINT}?${query.toString()}`),
      request(`${ENDPOINT}/stats`),
    ])
    if (!listResponse.ok) throw new Error('节能项目列表读取失败')
    const payload = await listResponse.json()
    rows.value = (payload.items ?? []) as Row[]
    total.value = payload.total ?? rows.value.length
    if (statsResponse.ok) {
      const statsPayload = await statsResponse.json()
      stats.value = statsPayload.items ?? stats.value
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '节能改造列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.warn-value {
  color: #b42318;
}
.cell-warn {
  color: #b42318;
  font-weight: 600;
}
.abnormal-row {
  background: #fef3f2;
}
.muted-text {
  color: var(--muted);
  font-size: 12px;
}
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
}
.modal-card {
  width: 420px;
  background: #fff;
  border-radius: 10px;
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.modal-card h3 {
  margin: 0;
}
.modal-hint {
  margin: 0;
  font-size: 12px;
  color: var(--muted);
}
.modal-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
}
.modal-field i {
  color: #b42318;
  font-style: normal;
  margin-left: 2px;
}
.modal-field input,
.filter-item select {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 13px;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 4px;
}
</style>
