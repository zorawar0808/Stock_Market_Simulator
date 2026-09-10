<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import './tokens.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000'

const token = ref(localStorage.getItem('esummit_token') || '')

const email = ref('')
const password = ref('')
const name = ref('')
const invitationCode = ref('')

const isRegistering = ref(false)
const authError = ref('')
const loading = ref(false)

const market = ref(null)
const companies = ref([])
const selectedCompany = ref(null)
const history = ref([])

const portfolio = ref(null)
const holdings = ref([])
const trades = ref([])
const leaderboard = ref([])

const search = ref('')
const sector = ref('ALL')

const buyAmount = ref('')
const sellShares = ref('')

const message = ref('')
const error = ref('')

const countdown = ref(0)

let pollTimer = null
let countdownTimer = null

const loggedIn = computed(() => !!token.value)

const sectors = computed(() => {
  return [
    'ALL',
    ...new Set(
      companies.value
        .map(company => company.sector)
        .filter(Boolean)
    )
  ]
})

const filteredCompanies = computed(() => {
  const q = search.value.toLowerCase().trim()

  return companies.value.filter(company => {
    const matchesSector =
      sector.value === 'ALL' ||
      company.sector === sector.value

    const matchesSearch =
      !q ||
      company.name.toLowerCase().includes(q) ||
      company.ticker.toLowerCase().includes(q)

    return matchesSector && matchesSearch
  })
})

const selectedHolding = computed(() => {
  if (!selectedCompany.value) {
    return null
  }

  return holdings.value.find(
    holding =>
      String(holding.company_id) ===
      String(selectedCompany.value.company_id)
  )
})

const selectedChange = computed(() => {
  if (
    !selectedCompany.value ||
    !selectedCompany.value.initial_price
  ) {
    return 0
  }

  return (
    (
      (selectedCompany.value.current_price -
        selectedCompany.value.initial_price) /
      selectedCompany.value.initial_price
    ) * 100
  )
})

const chartPoints = computed(() => {
  if (!history.value.length) {
    return ''
  }

  const points = history.value
    .map(point => ({
      price: Number(point.price),
      timestamp: point.timestamp
    }))
    .filter(point => Number.isFinite(point.price))

  if (!points.length) {
    return ''
  }

  const prices = points.map(point => point.price)
  const min = Math.min(...prices)
  const max = Math.max(...prices)
  const range = max - min || Math.max(max * 0.01, 1)

  return points
    .map((point, index) => {
      const x =
        points.length === 1
          ? 50
          : (index / (points.length - 1)) * 100

      const y =
        95 -
        ((point.price - min) / range) * 90

      return `${x.toFixed(2)},${y.toFixed(2)}`
    })
    .join(' ')
})

function tradeTicker(trade) {
  return trade.ticker || companies.value.find(company => String(company.company_id) === String(trade.company_id))?.ticker || trade.company_id
}

function money(value) {
  return `₹${Number(value || 0).toFixed(2)}`
}

function pct(value) {
  const n = Number(value || 0)

  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`
}

function formatTime(value) {
  if (!value) {
    return '-'
  }

  return new Date(value).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

function formatCountdown(seconds) {
  const total = Math.max(
    0,
    Math.floor(Number(seconds || 0))
  )

  const minutes = Math.floor(total / 60)
  const secs = total % 60

  return `${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
}

async function api(path, options = {}) {
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {})
  }

  if (token.value) {
    headers.Authorization = `Bearer ${token.value}`
  }

  const response = await fetch(
    `${API_URL}${path}`,
    {
      ...options,
      headers
    }
  )

  let data = null

  try {
    data = await response.json()
  } catch {
    data = null
  }

  if (!response.ok) {
    throw new Error(
      data?.detail ||
      data?.message ||
      `Request failed (${response.status})`
    )
  }

  return data
}

async function login() {
  authError.value = ''

  try {
      const response = await fetch(
        `${API_URL}/api/auth/login`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            email: email.value,
            password: password.value
          })
        }
      )

    const data = await response.json()

    if (!response.ok) {
      throw new Error(
        data?.detail || 'Login failed'
      )
    }

    token.value = data.access_token

    localStorage.setItem(
      'esummit_token',
      token.value
    )

    await loadEverything()
  } catch (err) {
    authError.value = err.message
  }
}

async function register() {
  authError.value = ''

  try {
    await api(
      '/api/auth/register',
      {
        method: 'POST',
        body: JSON.stringify({
          email: email.value,
          password: password.value,
          name: name.value,
          invitation_code: invitationCode.value
        })
      }
    )

    isRegistering.value = false

    authError.value =
      'Registration successful. Please log in.'
  } catch (err) {
    authError.value = err.message
  }
}

function logout() {
  token.value = ''

  localStorage.removeItem(
    'esummit_token'
  )

  stopPolling()
}

async function loadMarket() {
  market.value =
    await api('/api/market/status')

  countdown.value =
    Number(
      market.value?.remaining_seconds || 0
    )
}

async function loadCompanies() {
  companies.value =
    await api('/api/market/companies')

  if (
    !selectedCompany.value &&
    companies.value.length
  ) {
    selectedCompany.value =
      companies.value[0]
  } else if (selectedCompany.value) {
    const updated =
      companies.value.find(
        company =>
          String(company.company_id) ===
          String(
            selectedCompany.value.company_id
          )
      )

    if (updated) {
      selectedCompany.value = updated
    }
  }
}

async function loadPortfolio() {
  portfolio.value =
    await api('/api/teams/me/portfolio')
}

async function loadHoldings() {
  holdings.value =
    await api('/api/teams/me/holdings')
}

async function loadTrades() {
  trades.value =
    await api('/api/trades/history')
}

async function loadLeaderboard() {
  leaderboard.value =
    await api('/api/market/leaderboard')
}

async function loadHistory() {
  if (!selectedCompany.value) {
    return
  }

  try {
    history.value =
      await api(
        `/api/market/companies/${selectedCompany.value.company_id}/history`
      )
  } catch {
    history.value = []
  }
}

async function loadEverything() {
  loading.value = true
  error.value = ''

  try {
    await Promise.all([
      loadMarket(),
      loadCompanies(),
      loadPortfolio(),
      loadHoldings(),
      loadTrades(),
      loadLeaderboard()
    ])

    await loadHistory()

    startPolling()
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

async function refreshData() {
  if (!token.value) {
    return
  }

  try {
    await Promise.all([
      loadMarket(),
      loadCompanies(),
      loadPortfolio(),
      loadHoldings(),
      loadTrades(),
      loadLeaderboard()
    ])

    await loadHistory()
  } catch (err) {
    error.value = err.message
  }
}

async function buy() {
  message.value = ''
  error.value = ''

  const amount = Number(buyAmount.value)

  if (!amount || amount <= 0) {
    error.value = 'Enter a valid amount.'
    return
  }

  if (!selectedCompany.value) {
    error.value = 'Select a company first.'
    return
  }

  try {
    const idempotencyKey =
      crypto.randomUUID()

    await api(
      '/api/trades/buy',
      {
        method: 'POST',
        body: JSON.stringify({
          company_id:
            selectedCompany.value.company_id,
          amount,
          idempotency_key:
            idempotencyKey
        })
      }
    )

    message.value =
      `Bought ${selectedCompany.value.ticker} for ${money(amount)}.`

    buyAmount.value = ''

    await Promise.all([
      loadPortfolio(),
      loadHoldings(),
      loadTrades(),
      loadLeaderboard(),
      loadCompanies()
    ])

    await loadHistory()
  } catch (err) {
    error.value = err.message
  }
}

async function sell() {
  message.value = ''
  error.value = ''

  if (!selectedCompany.value) {
    error.value = 'Select a company first.'
    return
  }

  const shares = Number(sellShares.value)

  if (!shares || shares <= 0) {
    error.value =
      'Enter a valid share quantity.'
    return
  }

  try {
    await api(
      '/api/trades/sell',
      {
        method: 'POST',
        body: JSON.stringify({
          company_id:
            selectedCompany.value.company_id,
          shares,
          sell_all: false,
          idempotency_key:
            crypto.randomUUID()
        })
      }
    )

    message.value =
      `Sold ${shares.toFixed(4)} shares of ${selectedCompany.value.ticker}.`

    sellShares.value = ''

    await Promise.all([
      loadPortfolio(),
      loadHoldings(),
      loadTrades(),
      loadLeaderboard(),
      loadCompanies()
    ])

    await loadHistory()
  } catch (err) {
    error.value = err.message
  }
}

async function sellAll() {
  message.value = ''
  error.value = ''

  if (!selectedCompany.value) {
    return
  }

  try {
    await api(
      '/api/trades/sell',
      {
        method: 'POST',
        body: JSON.stringify({
          company_id:
            selectedCompany.value.company_id,
          sell_all: true,
          idempotency_key:
            crypto.randomUUID()
        })
      }
    )

    message.value =
      `Sold all ${selectedCompany.value.ticker} holdings.`

    await Promise.all([
      loadPortfolio(),
      loadHoldings(),
      loadTrades(),
      loadLeaderboard(),
      loadCompanies()
    ])

    await loadHistory()
  } catch (err) {
    error.value = err.message
  }
}

function startPolling() {
  stopPolling()

  pollTimer =
    setInterval(refreshData, 4000)

  countdownTimer =
    setInterval(() => {
      if (countdown.value > 0) {
        countdown.value -= 1
      }
    }, 1000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
  }

  if (countdownTimer) {
    clearInterval(countdownTimer)
  }

  pollTimer = null
  countdownTimer = null
}

watch(
  selectedCompany,
  async () => {
    await loadHistory()
  }
)

onMounted(async () => {
  if (token.value) {
    await loadEverything()
  }
})

onUnmounted(() => {
  stopPolling()
})
</script>

<template>
  <div class="app">
    <div
      v-if="!loggedIn"
      class="auth-page"
    >
      <div class="auth-card">
        <div class="brand">
          E-SUMMIT <span>MARKET</span>
        </div>

```
    <h1>
      {{
        isRegistering
          ? 'Create Account'
          : 'Participant Login'
      }}
    </h1>

    <p class="muted">
      {{
        isRegistering
          ? 'Join your team and enter the market.'
          : 'Enter the E-Summit trading terminal.'
      }}
    </p>

    <form
      @submit.prevent="
        isRegistering
          ? register()
          : login()
      "
    >
      <div
        v-if="isRegistering"
        class="field"
      >
        <label>Name</label>

        <input
          v-model="name"
          required
          placeholder="Your name"
        />
      </div>

      <div class="field">
        <label>Email</label>

        <input
          v-model="email"
          type="email"
          required
          placeholder="you@example.com"
        />
      </div>

      <div class="field">
        <label>Password</label>

        <input
          v-model="password"
          type="password"
          required
          placeholder="Password"
        />
      </div>

      <div
        v-if="isRegistering"
        class="field"
      >
        <label>Invitation code</label>

        <input
          v-model="invitationCode"
          required
          placeholder="Team invitation code"
        />
      </div>

      <div
        v-if="authError"
        class="error"
      >
        {{ authError }}
      </div>

      <button
        class="primary full"
        type="submit"
      >
        {{
          isRegistering
            ? 'Create account'
            : 'Sign in'
        }}
      </button>
    </form>

    <button
      class="link-button"
      @click="
        isRegistering = !isRegistering
      "
    >
      {{
        isRegistering
          ? 'Already have an account? Sign in'
          : 'Need an account? Register'
      }}
    </button>
  </div>
</div>

<div
  v-else
  class="terminal"
>
  <header class="topbar">
    <div class="brand">
      E-SUMMIT <span>MARKET</span>
    </div>

    <div class="market-status">
      <span
        class="status-dot"
        :class="{
          live: market?.state === 'LIVE',
          paused:
            market?.state === 'PAUSED'
        }"
      ></span>

      {{ market?.state || 'LOADING' }}

      <strong
        v-if="market?.state === 'LIVE'"
      >
        {{ formatCountdown(countdown) }}
      </strong>
    </div>

    <div class="top-stats">
      <div>
        <small>Cash</small>
        <strong>
          {{ money(portfolio?.cash) }}
        </strong>
      </div>

      <div>
        <small>Portfolio</small>
        <strong>
          {{
            money(
              portfolio?.portfolio_value
            )
          }}
        </strong>
      </div>

      <div>
        <small>Net Worth</small>
        <strong>
          {{ money(portfolio?.net_worth) }}
        </strong>
      </div>

      <button
        class="logout"
        @click="logout"
      >
        Log out
      </button>
    </div>
  </header>

  <div
    v-if="loading"
    class="loading"
  >
    Loading market...
  </div>

  <div class="terminal-grid">
    <aside class="sidebar panel">
      <div class="panel-title">
        <span>MARKET</span>

        <span class="count">
          {{ filteredCompanies.length }}
        </span>
      </div>

      <input
        v-model="search"
        class="search"
        placeholder="Search company or ticker..."
      />

      <div class="sectors">
        <button
          v-for="item in sectors"
          :key="item"
          :class="{
            active: sector === item
          }"
          @click="sector = item"
        >
          {{ item }}
        </button>
      </div>

      <div class="company-list">
        <button
          v-for="company in filteredCompanies"
          :key="company.company_id"
          class="company-row"
          :class="{
            selected:
              selectedCompany?.company_id ===
              company.company_id
          }"
          @click="
            selectedCompany = company
          "
        >
          <div>
            <strong>
              {{ company.ticker }}
            </strong>

            <span>
              {{ company.name }}
            </span>
          </div>

          <div class="company-price">
            <strong>
              {{ money(company.current_price) }}
            </strong>

            <small>
              {{ company.sector }}
            </small>
          </div>
        </button>
      </div>
    </aside>

    <main class="main-column">
      <section
        class="panel company-header"
      >
        <div>
          <div class="ticker">
            {{
              selectedCompany?.ticker ||
              '---'
            }}
          </div>

          <h1>
            {{
              selectedCompany?.name ||
              'Select a company'
            }}
          </h1>

          <p>
            {{
              selectedCompany?.description ||
              ''
            }}
          </p>
        </div>

        <div class="price-box">
          <div class="current-price">
            {{
              money(
                selectedCompany?.current_price
              )
            }}
          </div>

          <div
            class="change"
            :class="{
              negative:
                selectedChange < 0
            }"
          >
            {{ pct(selectedChange) }}
          </div>
        </div>
      </section>

      <section class="panel chart-panel">
        <div class="panel-title">
          <span>PRICE HISTORY</span>

          <span class="chart-meta">
            {{ history.length }} TICKS
          </span>
        </div>

        <div class="chart">
          <div class="chart-grid">
            <span></span>
            <span></span>
            <span></span>
            <span></span>
            <span></span>
          </div>

          <svg
            v-if="chartPoints"
            class="price-chart"
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
            aria-label="Price history chart"
          >
            <polyline
              :points="chartPoints"
              fill="none"
              class="price-line"
              vector-effect="non-scaling-stroke"
            />
          </svg>

          <div
            v-if="!chartPoints"
            class="chart-empty"
          >
            Waiting for price data...
          </div>
        </div>

        <div
          v-if="history.length"
          class="chart-footer"
        >
          <span>
            LOW
            <strong>
              {{ money(Math.min(...history.map(p => Number(p.price)))) }}
            </strong>
          </span>

          <span>
            HIGH
            <strong>
              {{ money(Math.max(...history.map(p => Number(p.price)))) }}
            </strong>
          </span>

          <span>
            LAST
            <strong>
              {{ money(history[history.length - 1]?.price) }}
            </strong>
          </span>
        </div>
      </section>

      <section class="panel">
        <div class="panel-title">
          YOUR HOLDING
        </div>

        <div
          v-if="selectedHolding"
          class="holding-detail"
        >
          <div>
            <small>Shares</small>

            <strong>
              {{
                Number(
                  selectedHolding.shares
                ).toFixed(4)
              }}
            </strong>
          </div>

          <div>
            <small>Average Price</small>

            <strong>
              {{
                money(
                  selectedHolding.average_purchase_price
                )
              }}
            </strong>
          </div>

          <div>
            <small>Current Value</small>

            <strong>
              {{
                money(
                  selectedHolding.holding_value
                )
              }}
            </strong>
          </div>

          <div>
            <small>P/L</small>

            <strong
              :class="{
                positive:
                  Number(
                    selectedHolding.unrealized_pl
                  ) >= 0,
                negative:
                  Number(
                    selectedHolding.unrealized_pl
                  ) < 0
              }"
            >
              {{
                money(
                  selectedHolding.unrealized_pl
                )
              }}
            </strong>
          </div>
        </div>

        <div
          v-else
          class="empty"
        >
          You don't currently hold this
          company.
        </div>
      </section>
    </main>

    <aside class="right-column">
      <section
        class="panel trade-panel"
      >
        <div class="panel-title">
          <span>ORDER</span>

          <span
            class="trade-state"
            :class="{
              disabled:
                market?.state !== 'LIVE'
            }"
          >
            {{
              market?.state === 'LIVE'
                ? 'TRADING OPEN'
                : 'CLOSED'
            }}
          </span>
        </div>

        <div class="order-company">
          <strong>
            {{ selectedCompany?.ticker }}
          </strong>

          <span>
            {{
              money(
                selectedCompany?.current_price
              )
            }}
          </span>
        </div>

        <label>
          BUY — Amount (₹)
        </label>

        <input
          v-model="buyAmount"
          type="number"
          min="1"
          step="0.01"
          placeholder="1000"
          :disabled="
            market?.state !== 'LIVE'
          "
        />

        <button
          class="buy-button"
          :disabled="
            market?.state !== 'LIVE'
          "
          @click="buy"
        >
          BUY
        </button>

        <div class="divider"></div>

        <label>
          SELL — Shares
        </label>

        <input
          v-model="sellShares"
          type="number"
          min="0.0001"
          step="0.0001"
          placeholder="10"
          :disabled="
            market?.state !== 'LIVE'
          "
        />

        <button
          class="sell-button"
          :disabled="
            market?.state !== 'LIVE'
          "
          @click="sell"
        >
          SELL
        </button>

        <button
          class="sell-all"
          :disabled="
            market?.state !== 'LIVE' ||
            !selectedHolding
          "
          @click="sellAll"
        >
          SELL ALL
        </button>

        <div
          v-if="message"
          class="success"
        >
          {{ message }}
        </div>

        <div
          v-if="error"
          class="error"
        >
          {{ error }}
        </div>
      </section>

      <section class="panel">
        <div class="panel-title">
          LEADERBOARD
        </div>

        <div
          v-for="team in leaderboard.slice(0, 8)"
          :key="team.team_id"
          class="leader-row"
        >
          <span class="rank">
            {{ team.rank }}
          </span>

          <strong>
            {{ team.team_name }}
          </strong>

          <span>
            {{ money(team.net_worth) }}
          </span>
        </div>
      </section>
    </aside>
  </div>

  <section class="bottom-grid">
    <div class="panel">
      <div class="panel-title">
        YOUR HOLDINGS
      </div>

      <div
        v-if="holdings.length"
        class="table"
      >
        <div class="table-head">
          <span>Company</span>
          <span>Shares</span>
          <span>Avg Price</span>
          <span>Value</span>
          <span>P/L</span>
        </div>

        <div
          v-for="holding in holdings"
          :key="
            holding.holding_id ||
            holding.company_id
          "
          class="table-row"
        >
          <span>
            <strong>
              {{
                holding.ticker ||
                holding.company_name
              }}
            </strong>
          </span>

          <span>
            {{
              Number(
                holding.shares
              ).toFixed(4)
            }}
          </span>

          <span>
            {{
              money(
                holding.average_purchase_price
              )
            }}
          </span>

          <span>
            {{
              money(
                holding.holding_value
              )
            }}
          </span>

          <span
            :class="{
              positive:
                Number(
                  holding.unrealized_pl
                ) >= 0,
              negative:
                Number(
                  holding.unrealized_pl
                ) < 0
            }"
          >
            {{
              money(
                holding.unrealized_pl
              )
            }}
          </span>
        </div>
      </div>

      <div
        v-else
        class="empty"
      >
        No holdings yet.
      </div>
    </div>

    <div class="panel">
      <div class="panel-title">
        ORDER HISTORY
      </div>

      <div
        v-if="trades.length"
        class="trade-history"
      >
        <div
          v-for="trade in trades.slice(0, 10)"
          :key="trade.trade_id"
          class="history-row"
        >
          <span
            class="trade-type"
            :class="
              trade.type?.toLowerCase()
            "
          >
            {{ trade.type }}
          </span>

          <strong>
            {{
              tradeTicker(trade)
            }}
          </strong>

          <span>
            {{
              Number(
                trade.shares
              ).toFixed(4)
            }}
            shares
          </span>

          <span>
            {{
              money(
                trade.execution_price
              )
            }}
          </span>

          <span>
            {{ formatTime(trade.timestamp) }}
          </span>

          <span>
            {{ trade.status }}
          </span>
        </div>
      </div>

      <div
        v-else
        class="empty"
      >
        No trades yet.
      </div>
    </div>
  </section>
</div>
```

  </div>
</template>

<style>
* {
  box-sizing: border-box;
}

body {
  margin: 0;
  background: #071018;
  color: #e8eef4;
  font-family:
    Inter,
    ui-sans-serif,
    system-ui,
    -apple-system,
    BlinkMacSystemFont,
    "Segoe UI",
    sans-serif;
}

button,
input {
  font: inherit;
}

button {
  cursor: pointer;
}

.app {
  min-height: 100vh;
}

.auth-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px;
  background:
    radial-gradient(
      circle at 50% 20%,
      #102434 0,
      #071018 45%,
      #04090e 100%
    );
}

.auth-card {
  width: min(420px, 100%);
  background: #0c1721;
  border: 1px solid #203342;
  border-radius: 16px;
  padding: 32px;
  box-shadow:
    0 30px 80px rgba(0, 0, 0, 0.45);
}

.brand {
  font-size: 18px;
  font-weight: 900;
  letter-spacing: 0.12em;
}

.brand span {
  opacity: 0.45;
}

.auth-card h1 {
  margin: 32px 0 8px;
  font-size: 28px;
}

.muted {
  color: #8293a1;
}

.field {
  margin-top: 18px;
}

.field label,
.trade-panel label {
  display: block;
  margin-bottom: 7px;
  color: #91a2b0;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

input {
  width: 100%;
  border: 1px solid #253b4b;
  background: #08131c;
  color: #fff;
  padding: 12px 13px;
  border-radius: 8px;
  outline: none;
}

input:focus {
  border-color: #6389a3;
}

.primary,
.buy-button,
.sell-button {
  border: 0;
  border-radius: 8px;
  padding: 12px;
  font-weight: 800;
  margin-top: 18px;
}

.primary {
  background: #dbe8ef;
  color: #071018;
}

.full {
  width: 100%;
}

.link-button {
  width: 100%;
  border: 0;
  background: transparent;
  color: #91b4ca;
  margin-top: 20px;
}

.error,
.success {
  padding: 10px 12px;
  margin-top: 12px;
  border-radius: 7px;
  font-size: 13px;
}

.error {
  background: #38191d;
  color: #ff9da6;
  border: 1px solid #63252d;
}

.success {
  background: #143123;
  color: #91dfb0;
  border: 1px solid #245b3d;
}

.terminal {
  min-height: 100vh;
  background: #071018;
}

.topbar {
  height: 72px;
  display: flex;
  align-items: center;
  gap: 28px;
  padding: 0 24px;
  border-bottom: 1px solid #1b2c39;
  background: #09141d;
  position: sticky;
  top: 0;
  z-index: 10;
}

.market-status {
  display: flex;
  align-items: center;
  gap: 9px;
  font-size: 12px;
  color: #9cafbd;
}

.market-status strong {
  color: #fff;
  margin-left: 5px;
  font-variant-numeric: tabular-nums;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #66737d;
}

.status-dot.live {
  background: #55d88a;
  box-shadow:
    0 0 12px rgba(85, 216, 138, 0.65);
}

.status-dot.paused {
  background: #e3b95d;
}

.top-stats {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 26px;
}

.top-stats div {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.top-stats small {
  color: #6e8290;
  font-size: 10px;
  text-transform: uppercase;
}

.top-stats strong {
  font-size: 13px;
}

.logout {
  border: 1px solid #263b49;
  background: transparent;
  color: #91a2b0;
  padding: 8px 13px;
  border-radius: 7px;
}

.loading {
  padding: 20px;
  text-align: center;
  color: #7e929f;
}

.terminal-grid {
  display: grid;
  grid-template-columns:
    270px minmax(0, 1fr) 300px;
  gap: 14px;
  padding: 14px;
}

.panel {
  background: #0b1721;
  border: 1px solid #1b2e3c;
  border-radius: 10px;
  overflow: hidden;
}

.sidebar {
  min-height: 610px;
}

.panel-title {
  padding: 14px 15px;
  border-bottom: 1px solid #1b2e3c;
  color: #8498a6;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.1em;
  display: flex;
  justify-content: space-between;
}

.count {
  color: #617582;
}

.search {
  margin: 12px;
  width: calc(100% - 24px);
}

.sectors {
  display: flex;
  gap: 5px;
  padding: 0 12px 12px;
  overflow-x: auto;
}

.sectors button {
  flex: 0 0 auto;
  border: 1px solid #223746;
  color: #8296a4;
  background: #09141d;
  padding: 6px 8px;
  border-radius: 6px;
  font-size: 10px;
}

.sectors button.active {
  background: #1b3344;
  color: #dce9f0;
}

.company-list {
  max-height: 500px;
  overflow-y: auto;
}

.company-row {
  width: 100%;
  display: flex;
  justify-content: space-between;
  text-align: left;
  border: 0;
  border-top: 1px solid #142631;
  background: transparent;
  color: #fff;
  padding: 12px;
}

.company-row:hover,
.company-row.selected {
  background: #112330;
}

.company-row > div:first-child {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.company-row strong {
  font-size: 13px;
}

.company-row span {
  color: #718693;
  font-size: 10px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.company-price {
  text-align: right;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.company-price strong {
  font-size: 12px;
}

.company-price small {
  color: #617582;
  font-size: 9px;
}

.main-column {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.company-header {
  padding: 22px;
  display: flex;
  justify-content: space-between;
  gap: 20px;
}

.ticker {
  color: #7392a5;
  font-size: 12px;
  letter-spacing: 0.1em;
  font-weight: 800;
}

.company-header h1 {
  margin: 5px 0;
  font-size: 25px;
}

.company-header p {
  margin: 8px 0 0;
  color: #718592;
  font-size: 12px;
  max-width: 620px;
}

.price-box {
  text-align: right;
  min-width: 150px;
}

.current-price {
  font-size: 28px;
  font-weight: 900;
}

.change {
  margin-top: 5px;
  color: #65d492;
  font-size: 13px;
}

.change.negative,
.negative {
  color: #ed737d;
}

.positive {
  color: #65d492;
}

.chart-panel {
  min-height: 290px;
}


.chart {
  position: relative;
  width: 100%;
  height: 320px;
  overflow: hidden;
  background: var(--bg-panel);
}

.price-chart {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  overflow: visible;
  z-index: 2;
}

.price-line {
  stroke: var(--accent);
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.chart-grid {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  z-index: 1;
  pointer-events: none;
}

.chart-grid span {
  display: block;
  width: 100%;
  border-top: 1px solid var(--border);
  opacity: 0.55;
}

.chart-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.08em;
}

.chart-meta {
  font-family: var(--font-mono);
  color: var(--text-muted);
  font-size: 9px;
}

.chart-footer {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  border-top: 1px solid var(--border);
}

.chart-footer span {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 8px;
  letter-spacing: 0.08em;
}

.chart-footer span + span {
  border-left: 1px solid var(--border);
}

.chart-footer strong {
  color: var(--text-primary);
  font-size: 11px;
  font-weight: 500;
}


.chart {
  height: 245px;
  position: relative;
  padding: 18px;
}

.chart svg {
  width: 100%;
  height: 100%;
  color: #80b3cf;
}

.chart-empty {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  color: #5e737f;
  font-size: 12px;
}

.holding-detail {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
  padding: 18px;
}

.holding-detail div {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.holding-detail small {
  color: #617582;
  font-size: 10px;
  text-transform: uppercase;
}

.holding-detail strong {
  font-size: 14px;
}

.empty {
  padding: 22px;
  color: #637783;
  font-size: 12px;
}

.right-column {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.trade-panel {
  padding-bottom: 18px;
}

.trade-state {
  color: #65d492;
}

.trade-state.disabled {
  color: #ed737d;
}

.order-company {
  display: flex;
  justify-content: space-between;
  padding: 18px 15px;
  font-size: 14px;
}

.order-company span {
  color: #8da1ae;
}

.trade-panel > label,
.trade-panel > input,
.trade-panel > button {
  margin-left: 15px;
  margin-right: 15px;
  width: calc(100% - 30px);
}

.trade-panel > label {
  margin-top: 14px;
}

.buy-button {
  background: #4bcf82;
  color: #06130b;
}

.sell-button {
  background: #dc6873;
  color: #fff;
}

.buy-button:disabled,
.sell-button:disabled,
.sell-all:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.sell-all {
  margin-top: 8px;
  border: 1px solid #583139;
  background: transparent;
  color: #dc7b84;
  padding: 10px;
  border-radius: 8px;
}

.divider {
  height: 1px;
  background: #1b2e3c;
  margin: 20px 15px;
}

.leader-row {
  display: grid;
  grid-template-columns: 25px 1fr auto;
  gap: 8px;
  align-items: center;
  padding: 10px 13px;
  border-top: 1px solid #142631;
  font-size: 11px;
}

.rank {
  color: #617783;
}

.leader-row strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.leader-row > span:last-child {
  color: #a6b7c0;
}

.bottom-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  padding: 0 14px 14px;
}

.table-head,
.table-row {
  display: grid;
  grid-template-columns:
    1.5fr 1fr 1fr 1fr 1fr;
  gap: 10px;
  align-items: center;
  padding: 11px 14px;
  font-size: 11px;
}

.table-head {
  color: #5f7582;
  text-transform: uppercase;
  font-size: 9px;
}

.table-row {
  border-top: 1px solid #142631;
  color: #91a4af;
}

.table-row strong {
  color: #d8e3e8;
}

.trade-history {
  max-height: 250px;
  overflow-y: auto;
}

.history-row {
  display: grid;
  grid-template-columns:
    50px 1fr 1.3fr 1fr 1fr 1fr;
  gap: 8px;
  align-items: center;
  padding: 11px 14px;
  border-top: 1px solid #142631;
  color: #8da0ac;
  font-size: 10px;
}

.history-row strong {
  color: #dce5e9;
}

.trade-type {
  font-weight: 900;
}

.trade-type.buy {
  color: #65d492;
}

.trade-type.sell {
  color: #ed737d;
}

@media (max-width: 1100px) {
  .terminal-grid {
    grid-template-columns:
      230px minmax(0, 1fr);
  }

  .right-column {
    grid-column: 1 / -1;
    display: grid;
    grid-template-columns: 1fr 1fr;
  }

  .bottom-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .topbar {
    height: auto;
    flex-wrap: wrap;
    padding: 15px;
  }

  .top-stats {
    width: 100%;
    margin-left: 0;
    overflow-x: auto;
  }

  .terminal-grid {
    grid-template-columns: 1fr;
  }

  .sidebar {
    min-height: auto;
  }

  .company-list {
    max-height: 300px;
  }

  .right-column {
    grid-template-columns: 1fr;
  }

  .holding-detail {
    grid-template-columns: 1fr 1fr;
  }

  .company-header {
    flex-direction: column;
  }

  .price-box {
    text-align: left;
  }
}
</style>
