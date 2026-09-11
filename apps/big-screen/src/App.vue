<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import './tokens.css'

const API_URL = import.meta.env.VITE_API_URL || ''

const marketState = ref(null)
const leaderboard = ref([])
const companies = ref([])
const connectionOk = ref(true)
const loading = ref(true)

async function refresh() {
  try {
    const [statusRes, leaderboardRes, companiesRes] = await Promise.all([
      fetch(`${API_URL}/api/market/status`),
      fetch(`${API_URL}/api/market/leaderboard`),
      fetch(`${API_URL}/api/market/companies`),
    ])

    if (!statusRes.ok || !leaderboardRes.ok || !companiesRes.ok) {
      throw new Error('API request failed')
    }

    marketState.value = await statusRes.json()
    leaderboard.value = await leaderboardRes.json()
    companies.value = await companiesRes.json()

    connectionOk.value = true
    loading.value = false
  } catch (e) {
    connectionOk.value = false
    loading.value = false
  }
}

function formatRemaining(seconds) {
  if (seconds == null) return '—:—'

  const m = Math.max(0, Math.floor(seconds / 60))
  const s = Math.max(0, Math.floor(seconds % 60))

  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function changePercent(company) {
  if (!company?.initial_price) return 0

  return (
    ((Number(company.current_price) - Number(company.initial_price)) /
      Number(company.initial_price)) *
    100
  )
}

function formatPrice(price) {
  return Number(price).toFixed(2)
}

function signedPercent(value) {
  const number = Number(value)

  if (number > 0) return `+${number.toFixed(1)}%`
  if (number < 0) return `${number.toFixed(1)}%`

  return '0.0%'
}

const rankedCompanies = computed(() => {
  return [...companies.value].sort(
    (a, b) => changePercent(b) - changePercent(a)
  )
})

const gainers = computed(() => {
  return rankedCompanies.value
    .filter((company) => changePercent(company) > 0)
    .slice(0, 5)
})

const losers = computed(() => {
  return [...rankedCompanies.value]
    .filter((company) => changePercent(company) < 0)
    .sort((a, b) => changePercent(a) - changePercent(b))
    .slice(0, 5)
})

const flatCompanies = computed(() => {
  return rankedCompanies.value.filter(
    (company) => changePercent(company) === 0
  )
})

const marketLabel = computed(() => {
  if (!marketState.value?.state) return 'CONNECTING'

  return marketState.value.state.replaceAll('_', ' ')
})

let poller

onMounted(() => {
  refresh()
  poller = setInterval(refresh, 3000)
})

onUnmounted(() => {
  clearInterval(poller)
})
</script>

<template>
  <div class="screen">

    <!-- HEADER -->
    <header class="topbar">

      <div class="brand">
        <div class="title">E-SUMMIT MARKET</div>
        <div class="subtitle">
          LIVE MARKET TERMINAL
          <span class="live-dot"></span>
        </div>
      </div>

      <div class="market-status">

        <div class="status-block">
          <span
            class="state"
            :class="marketState?.state?.toLowerCase()"
          >
            {{ marketLabel }}
          </span>

          <span v-if="connectionOk" class="connection">
            LIVE DATA
          </span>

          <span v-else class="offline">
            RECONNECTING…
          </span>
        </div>

        <div class="clock tabular-num">
          {{ formatRemaining(marketState?.remaining_seconds) }}
        </div>

      </div>
    </header>


    <!-- LEADERBOARD -->
    <section class="leaderboard-section">

      <div class="section-heading">
        <div>
          <span class="eyebrow">COMPETITION</span>
          <h1>Leaderboard</h1>
        </div>

        <span class="section-meta">
          TOP {{ Math.min(10, leaderboard.length) }}
        </span>
      </div>

      <div class="leaderboard-card">

        <table>

          <thead>
            <tr>
              <th class="rank-column">RANK</th>
              <th>TEAM</th>
              <th class="num">NET WORTH</th>
              <th class="num">RETURN</th>
            </tr>
          </thead>

          <tbody>

            <tr
              v-for="row in leaderboard.slice(0, 10)"
              :key="row.team_id"
              :class="{ leader: row.rank === 1 }"
            >

              <td class="rank">

                <span
                  v-if="row.rank === 1"
                  class="rank-badge first"
                >
                  1
                </span>

                <span
                  v-else-if="row.rank === 2"
                  class="rank-badge second"
                >
                  2
                </span>

                <span
                  v-else-if="row.rank === 3"
                  class="rank-badge third"
                >
                  3
                </span>

                <span v-else>
                  {{ row.rank }}
                </span>

              </td>

              <td class="team-name">
                {{ row.team_name }}
              </td>

              <td class="num tabular-num net-worth">
                ₹{{ Number(row.net_worth).toFixed(0) }}
              </td>

              <td
                class="num tabular-num return"
                :class="
                  row.return_percent >= 0
                    ? 'positive'
                    : 'negative'
                "
              >
                {{ signedPercent(row.return_percent) }}
              </td>

            </tr>

            <tr v-if="leaderboard.length === 0">

              <td colspan="4" class="empty">
                <span v-if="loading">Loading leaderboard…</span>
                <span v-else>Waiting for teams to enter the market…</span>
              </td>

            </tr>

          </tbody>

        </table>

      </div>

    </section>


    <!-- MOVERS -->
    <section class="movers-section">

      <div class="section-heading">

        <div>
          <span class="eyebrow">MARKET ACTIVITY</span>
          <h1>Top Movers</h1>
        </div>

        <span class="section-meta">
          {{ companies.length }} STOCKS
        </span>

      </div>


      <div class="movers-grid">


        <!-- GAINERS -->
        <div class="mover-card">

          <div class="mover-header">
            <div class="mover-title positive">
              TOP GAINERS
            </div>

            <div class="mover-indicator positive">
              ▲
            </div>
          </div>


          <div
            v-for="company in gainers"
            :key="company.company_id"
            class="mover-row"
          >

            <div class="mover-company">

              <strong>
                {{ company.ticker }}
              </strong>

              <span>
                {{ company.name }}
              </span>

            </div>


            <div class="mover-price">

              <span>
                ₹{{ formatPrice(company.current_price) }}
              </span>

              <strong class="positive">
                {{ signedPercent(changePercent(company)) }}
              </strong>

            </div>

          </div>


          <div v-if="gainers.length === 0" class="mover-empty">
            No stocks currently advancing
          </div>

        </div>


        <!-- LOSERS -->
        <div class="mover-card">

          <div class="mover-header">

            <div class="mover-title negative">
              TOP LOSERS
            </div>

            <div class="mover-indicator negative">
              ▼
            </div>

          </div>


          <div
            v-for="company in losers"
            :key="company.company_id"
            class="mover-row"
          >

            <div class="mover-company">

              <strong>
                {{ company.ticker }}
              </strong>

              <span>
                {{ company.name }}
              </span>

            </div>


            <div class="mover-price">

              <span>
                ₹{{ formatPrice(company.current_price) }}
              </span>

              <strong class="negative">
                {{ signedPercent(changePercent(company)) }}
              </strong>

            </div>

          </div>


          <div v-if="losers.length === 0" class="mover-empty">

            <span v-if="companies.length === 0">
              Waiting for market data…
            </span>

            <span v-else-if="flatCompanies.length === companies.length">
              No stocks have moved yet
            </span>

            <span v-else>
              No declining stocks
            </span>

          </div>

        </div>

      </div>

    </section>


    <!-- COMPANY BOARD -->
    <section class="market-board-section">

      <div class="section-heading board-heading">

        <div>
          <span class="eyebrow">MARKET 30</span>
          <h1>Company Board</h1>
        </div>

        <div class="board-meta">

          <span class="company-count">
            {{ companies.length }} COMPANIES
          </span>

          <span class="sort-label">
            SORTED BY PERFORMANCE
          </span>

        </div>

      </div>


      <div class="market-grid">

        <div
          v-for="company in rankedCompanies"
          :key="company.company_id"
          class="company-card"
          :class="{
            'company-up': changePercent(company) > 0,
            'company-down': changePercent(company) < 0
          }"
        >

          <div class="company-top">

            <strong class="ticker">
              {{ company.ticker }}
            </strong>

            <span
              class="company-change"
              :class="
                changePercent(company) >= 0
                  ? 'positive'
                  : 'negative'
              "
            >
              {{ signedPercent(changePercent(company)) }}
            </span>

          </div>


          <div class="company-name">
            {{ company.name }}
          </div>


          <div class="company-bottom">

            <span class="sector">
              {{ company.sector }}
            </span>

            <strong class="company-price tabular-num">
              ₹{{ formatPrice(company.current_price) }}
            </strong>

          </div>

        </div>


        <div
          v-if="companies.length === 0"
          class="board-empty"
        >
          Loading market data…
        </div>

      </div>

    </section>

  </div>
</template>


<style scoped>
.screen {
  min-height: 100vh;
  padding: 36px 52px 70px;
}


/* =========================
   HEADER
========================= */

.topbar {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  padding-bottom: 28px;
  border-bottom: 1px solid var(--border);
}

.brand {
  display: flex;
  flex-direction: column;
}

.title {
  font-size: 28px;
  font-weight: 800;
  letter-spacing: 0.1em;
}

.subtitle {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 7px;
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.14em;
}

.live-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--positive);
  box-shadow: 0 0 8px var(--positive);
}

.market-status {
  display: flex;
  align-items: center;
  gap: 28px;
}

.status-block {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
}

.state {
  font-size: 19px;
  font-weight: 800;
  letter-spacing: 0.05em;
}

.state.live {
  color: var(--positive);
}

.state.paused,
.state.emergency_frozen {
  color: var(--warning);
}

.state.closed {
  color: var(--negative);
}

.connection {
  color: var(--text-muted);
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.12em;
}

.offline {
  color: var(--negative);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.1em;
}

.clock {
  min-width: 115px;
  font-size: 38px;
  font-weight: 800;
  letter-spacing: 0.03em;
}


/* =========================
   SECTIONS
========================= */

section {
  margin-top: 38px;
}

.section-heading {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 17px;
}

.eyebrow {
  color: var(--text-muted);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.16em;
}

h1 {
  margin: 5px 0 0;
  font-size: 26px;
  line-height: 1;
  letter-spacing: -0.02em;
}

.section-meta {
  color: var(--text-muted);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.1em;
}


/* =========================
   LEADERBOARD
========================= */

.leaderboard-card {
  overflow: hidden;
  border: 1px solid var(--border);
  background: var(--surface);
}

table {
  width: 100%;
  border-collapse: collapse;
}

th {
  text-align: left;
  color: var(--text-muted);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.1em;
  padding: 14px 20px;
  border-bottom: 1px solid var(--border);
}

td {
  padding: 13px 20px;
  border-bottom: 1px solid var(--border);
  font-size: 19px;
}

tbody tr:last-child td {
  border-bottom: 0;
}

tbody tr.leader {
  background: var(--surface-raised);
}

.rank-column {
  width: 80px;
}

.rank {
  width: 80px;
  color: var(--text-muted);
  font-weight: 700;
}

.rank-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  font-size: 13px;
  font-weight: 800;
}

.rank-badge.first,
.rank-badge.second,
.rank-badge.third {
  border: 1px solid var(--border);
}

.team-name {
  font-weight: 700;
}

.net-worth {
  font-weight: 700;
}

.return {
  font-weight: 700;
}

.num {
  text-align: right;
}

.empty {
  text-align: center;
  color: var(--text-muted);
  padding: 38px;
  font-size: 15px;
}


/* =========================
   MOVERS
========================= */

.movers-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
}

.mover-card {
  overflow: hidden;
  border: 1px solid var(--border);
  background: var(--surface);
  padding: 18px 20px;
}

.mover-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 7px;
}

.mover-title {
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.13em;
}

.mover-indicator {
  font-size: 14px;
  font-weight: 900;
}

.mover-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  min-height: 55px;
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
}

.mover-row:last-of-type {
  border-bottom: 0;
}

.mover-company {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.mover-company strong {
  font-size: 17px;
  letter-spacing: 0.03em;
}

.mover-company span {
  color: var(--text-muted);
  font-size: 11px;
}

.mover-price {
  display: flex;
  align-items: center;
  gap: 18px;
}

.mover-price span {
  color: var(--text-primary);
  font-size: 15px;
  font-weight: 600;
}

.mover-price strong {
  min-width: 64px;
  text-align: right;
  font-size: 15px;
}

.mover-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 275px;
  color: var(--text-muted);
  font-size: 13px;
}


/* =========================
   COMPANY BOARD
========================= */

.board-heading {
  align-items: flex-end;
}

.board-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 5px;
}

.company-count {
  color: var(--text-primary);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.1em;
}

.sort-label {
  color: var(--text-muted);
  font-size: 9px;
  letter-spacing: 0.08em;
}

.market-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 10px;
}

.company-card {
  position: relative;
  min-height: 105px;
  border: 1px solid var(--border);
  padding: 14px;
  background: var(--surface);
  overflow: hidden;
}

.company-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 3px;
  height: 100%;
  background: transparent;
}

.company-card.company-up::before {
  background: var(--positive);
}

.company-card.company-down::before {
  background: var(--negative);
}

.company-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.ticker {
  font-size: 16px;
  font-weight: 800;
  letter-spacing: 0.05em;
}

.company-change {
  font-size: 11px;
  font-weight: 800;
}

.company-name {
  margin-top: 7px;
  min-height: 31px;
  color: var(--text-primary);
  font-size: 12px;
  line-height: 1.25;
}

.company-bottom {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 8px;
  margin-top: 13px;
}

.sector {
  max-width: 55%;
  overflow: hidden;
  color: var(--text-muted);
  font-size: 9px;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.company-price {
  font-size: 17px;
  font-weight: 800;
}

.board-empty {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 180px;
  border: 1px solid var(--border);
  color: var(--text-muted);
}


/* =========================
   RESPONSIVE
========================= */

@media (max-width: 1200px) {
  .screen {
    padding: 28px 30px 60px;
  }

  .market-grid {
    grid-template-columns: repeat(4, 1fr);
  }
}

@media (max-width: 950px) {
  .topbar {
    align-items: flex-start;
    gap: 22px;
  }

  .market-status {
    gap: 16px;
  }

  .clock {
    font-size: 30px;
  }

  .market-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (max-width: 750px) {
  .screen {
    padding: 22px;
  }

  .topbar {
    flex-direction: column;
  }

  .market-status {
    width: 100%;
    justify-content: space-between;
  }

  .status-block {
    align-items: flex-start;
  }

  .movers-grid {
    grid-template-columns: 1fr;
  }

  .market-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .board-meta {
    align-items: flex-end;
  }
}
</style>
