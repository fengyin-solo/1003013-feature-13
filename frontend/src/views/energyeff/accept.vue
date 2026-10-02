<template>
  <section class="page">
    <header class="page-head">
      <div>
        <h2>节能改造验收评估</h2>
        <p class="page-desc">
          按改造前后实测用电提交：基准期取改造前留档数据，连续观察期不足 7 天不予采信。
          同一项目只认第一次验收，提交后自动返回列表。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="goList">返回列表</button>
      </div>
    </header>

    <div v-if="errorMessage" class="error-banner">{{ errorMessage }}</div>

    <form v-if="entry" class="accept-form" @submit.prevent="submit">
      <article class="form-block">
        <h3>项目信息</h3>
        <dl class="info-grid">
          <div><dt>项目编号</dt><dd>{{ entry['项目编号'] }}</dd></div>
          <div><dt>所属站点</dt><dd>{{ entry['所属站点'] }}</dd></div>
          <div><dt>改造内容</dt><dd>{{ entry['改造内容'] }}</dd></div>
          <div><dt>立项预估节电率</dt><dd>{{ entry['预估节电率'] || '—' }}</dd></div>
          <div><dt>立项投资金额</dt><dd>{{ formatNumber(entry['投资金额']) }} 元</dd></div>
          <div><dt>当前状态</dt><dd>{{ entry.status }}</dd></div>
        </dl>
      </article>

      <article class="form-block">
        <h3>改造前基准期用电（改造开始时留档）</h3>
        <dl class="info-grid">
          <div>
            <dt>基准期用电（度）</dt>
            <dd>{{ entry['基准期用电'] ?? '未留档' }}</dd>
          </div>
          <div>
            <dt>基准期天数</dt>
            <dd>{{ entry['基准期天数'] ?? '—' }}</dd>
          </div>
        </dl>
        <p v-if="entry['基准期用电'] == null" class="block-hint warn">
          改造开始时未留基准期数据，请在本次验收一并补录；已留档的基准期数据验收时不得修改。
        </p>
        <div v-if="entry['基准期用电'] == null" class="field-row">
          <label>
            <span>基准期用电（度）<i>*</i></span>
            <input v-model.number="form['基准期用电']" type="number" min="0" step="0.01" required />
          </label>
          <label>
            <span>基准期天数<i>*</i></span>
            <input v-model.number="form['基准期天数']" type="number" min="1" step="1" required />
          </label>
        </div>
      </article>

      <article class="form-block">
        <h3>连续观察期实测数据</h3>
        <div class="field-row">
          <label>
            <span>观察期用电（度）<i>*</i></span>
            <input v-model.number="form['观察期用电']" type="number" min="0" step="0.01" required />
          </label>
          <label>
            <span>观察期天数（不少于 7 天）<i>*</i></span>
            <input v-model.number="form['观察期天数']" type="number" min="7" step="1" required />
          </label>
          <label>
            <span>电价（元/度）<i>*</i></span>
            <input v-model.number="form['电价']" type="number" min="0" step="0.01" required />
          </label>
          <label>
            <span>实际投资（元，留空取立项金额）</span>
            <input v-model.number="form['实际投资']" type="number" min="0" step="0.01" />
          </label>
        </div>
      </article>

      <article class="form-block">
        <h3>验收结论</h3>
        <textarea
          v-model="form['验收结论']"
          rows="3"
          placeholder="留空则使用默认结论：验收通过，节电率与投资回收期以改造前后实测数据重算结果为准。"
        ></textarea>
      </article>

      <p v-if="submitError" class="error-text">{{ submitError }}</p>
      <div class="form-actions">
        <button class="btn" type="button" @click="goList">取消</button>
        <button class="btn primary" type="submit" :disabled="submitting">
          {{ submitting ? '提交中…' : '提交验收（仅认第一次）' }}
        </button>
      </div>
    </form>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type Entry = Record<string, string | number | null>

const route = useRoute()
const router = useRouter()
const entryId = String(route.params.id)

const entry = ref<Entry | null>(null)
const errorMessage = ref('')
const submitError = ref('')
const submitting = ref(false)
const form = reactive<Record<string, number | string>>({
  基准期用电: '',
  基准期天数: '',
  观察期用电: '',
  观察期天数: '',
  电价: '',
  实际投资: '',
  验收结论: '',
})

function formatNumber(value: unknown): string {
  if (value == null || value === '') return '—'
  return String(value)
}

function goList() {
  // 验收结论改完/提交完都回到列表这一页。
  void router.push({ path: '/energyeff' })
}

async function load() {
  try {
    const response = await request(`/api/energyeff/${entryId}`)
    if (!response.ok) throw new Error('节能项目读取失败')
    const data: Entry = await response.json()
    entry.value = data
    if (data.status !== '评估中') {
      errorMessage.value =
        data.status === '已验收'
          ? '该项目已验收，同一项目重复提交验收只认第一次；可在详情页修改验收结论。'
          : `项目当前为「${String(data.status)}」，暂不能提交验收。`
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '节能项目读取失败'
  }
}

async function submit() {
  if (!entry.value || entry.value.status !== '评估中') {
    submitError.value = errorMessage.value || '当前项目状态不允许提交验收'
    return
  }
  submitError.value = ''
  submitting.value = true
  const values: Record<string, unknown> = { action: '验收评估' }
  for (const [key, value] of Object.entries(form)) {
    if (value !== '') values[key] = value
  }
  try {
    const response = await request(`/api/energyeff/${entryId}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const result = await response.json()
    if (!result.ok) {
      submitError.value = result.message ?? '验收提交失败'
      return
    }
    // 提交成功：验收结论已落档，回到列表页看刷新后的实测节电率。
    goList()
  } catch (error) {
    submitError.value = error instanceof Error ? error.message : '验收提交失败'
  } finally {
    submitting.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.error-banner {
  background: #fef3f2;
  border: 1px solid #fecdca;
  color: #b42318;
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 13px;
  margin-bottom: 12px;
}
.accept-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.form-block {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 16px;
}
.form-block h3 {
  margin: 0 0 10px;
  font-size: 14px;
}
.info-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px 16px;
  margin: 0;
}
.info-grid dt {
  font-size: 12px;
  color: var(--muted);
}
.info-grid dd {
  margin: 2px 0 0;
  font-size: 13px;
}
.block-hint {
  font-size: 12px;
  margin: 8px 0;
}
.block-hint.warn {
  color: #b42318;
}
.field-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}
.field-row label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
}
.field-row i,
.field-row + .field-row i {
  color: #b42318;
  font-style: normal;
}
.field-row input,
textarea {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 13px;
  font-family: inherit;
}
.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
