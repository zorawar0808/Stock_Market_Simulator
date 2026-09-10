```vue
<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import './tokens.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const accessToken = ref(localStorage.getItem('esummit_admin_token') || '')
const isAuthenticated = computed(() => !!accessToken.value)

const email = ref('')
const password = ref('')
const loginError = ref('')
const loginBusy = ref(false)

const marketState = ref(null)
const leaderboard = ref([])
const actionError = ref('')
const actionBusy = ref('')

const currentState = computed(() => marketState.value?.state || 'UNKNOWN')

const canStart = computed(() =>
  currentState.value === 'WAITING' ||
  currentState.value === 'CLOSED'
)

const canPause = computed(() =>
  ['LIVE', 'EMERGENCY_FROZEN'].includes(currentState.value)
)

const canResume = computed(() =>
  ['PAUSED', 'EMERGENCY_FROZEN'].includes(currentState.value)
)

const canEnd = computed(() =>
  ['LIVE', 'PAUSED', 'EMERGENCY_FROZEN'].includes(currentState.value)
)

const canFreeze = computed(() =>
  ['LIVE', 'PAUSED'].includes(currentState.value)
)

const canUnfreeze = computed(() =>
  currentState.value === 'EMERGENCY_FROZEN'
)

/*
 * Market reset
 *
 * Reset is deliberately blocked while LIVE.
 * The backend also enforces this rule, but disabling the button here
 * prevents accidental attempts from the UI.
 */
const resetBusy = ref(false)
const resetError = ref('')

const canReset = computed(() =>
  !resetBusy.value &&
  currentState.value !== 'LIVE' &&
  !!accessToken.value
)

function authHeaders() {
  return {
    Authorization: `Bearer ${accessToken.value}`,
    'Content-Type': 'application/json',
  }
}

async function login() {
  loginError.value = ''
  loginBusy.value = true

  try {
    const res = await fetch(`${API_URL}/api/auth/admin/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        email: email.value,
        password: password.value,
      }),
    })

    const data = await res.json()

    if (!res.ok) {
      throw new Error(data.detail || 'LOGIN FAILED')
    }

    accessToken.value = data.access_token

    localStorage.setItem(
      'esummit_admin_token',
      data.access_token
    )

    await refresh()
    await loadCrisisEvents()
  } catch (e) {
    loginError.value = e.message
  } finally {
    loginBusy.value = false
  }
}

function logout() {
  accessToken.value = ''
  localStorage.removeItem('esummit_admin_token')

  marketState.value = null
  leaderboard.value = []
  actionError.value = ''
  resetError.value = ''
  resetBusy.value = false
}

async function refresh() {
  try {
    const [statusRes, leaderboardRes] = await Promise.all([
      fetch(`${API_URL}/api/market/status`),
      fetch(`${API_URL}/api/market/leaderboard`),
    ])

    if (!statusRes.ok) {
      throw new Error('Could not fetch market status')
    }

    if (!leaderboardRes.ok) {
      throw new Error('Could not fetch leaderboard')
    }

    marketState.value = await statusRes.json()
    leaderboard.value = await leaderboardRes.json()

    if (marketState.value?.state === 'CLOSED') {
      actionBusy.value = ''
    }
  } catch (e) {
    actionError.value =
      'Could not reach the backend — is it running?'
  }
}

async function runControl(action) {
  if (actionBusy.value || resetBusy.value) {
    return
  }

  actionError.value = ''
  actionBusy.value = action

  try {
    const res = await fetch(
      `${API_URL}/api/admin/market/${action}`,
      {
        method: 'POST',
        headers: authHeaders(),
      }
    )

    const text = await res.text()

    let data = {}

    try {
      data = text ? JSON.parse(text) : {}
    } catch {
      data = {}
    }

    if (!res.ok) {
      throw new Error(
        data.detail ||
        `${action.toUpperCase()} FAILED (${res.status})`
      )
    }

    await refresh()
  } catch (e) {
    actionError.value = e.message
  } finally {
    actionBusy.value = ''
  }
}

/*
 * Reset the entire market simulation state back to its original starting
 * condition.
 *
 * Backend behavior:
 * - Restores every company to its initial price.
 * - Clears generated price snapshots.
 * - Resets the market clock.
 * - Resets market state to WAITING.
 * - Preserves teams, cash, holdings and trade history.
 */
async function resetMarketToOriginal() {
  if (resetBusy.value || actionBusy.value) {
    return
  }

  if (currentState.value === 'LIVE') {
    resetError.value =
      'Cannot reset the market while it is LIVE. Pause or freeze it first.'
    return
  }

  const confirmed = window.confirm(
    'RESET MARKET TO ORIGINAL VALUES?\n\n' +
    'This will:\n' +
    '• restore every stock to its initial price\n' +
    '• clear generated price history\n' +
    '• reset the market clock\n' +
    '• return the market to WAITING\n\n' +
    'Teams, cash, holdings, and trade history will be preserved.\n\n' +
    'This action is intended for testing/demo recovery.\n\n' +
    'Continue?'
  )

  if (!confirmed) {
    return
  }

  resetBusy.value = true
  resetError.value = ''
  actionError.value = ''

  try {
    const res = await fetch(
      `${API_URL}/api/admin/market/reset-to-original`,
      {
        method: 'POST',
        headers: authHeaders(),
      }
    )

    const text = await res.text()

    let data = {}

    try {
      data = text ? JSON.parse(text) : {}
    } catch {
      data = {}
    }

    if (!res.ok) {
      throw new Error(
        data.detail ||
        `MARKET RESET FAILED (${res.status})`
      )
    }

    /*
     * Refresh the state immediately so the UI changes from
     * PAUSED/CLOSED/etc. to WAITING without requiring a page reload.
     */
    await refresh()

    /*
     * Clear any stale reset error after a successful reset.
     */
    resetError.value = ''
  } catch (e) {
    resetError.value =
      e.message || 'MARKET RESET FAILED'
  } finally {
    resetBusy.value = false
  }
}

const crisisEvents = ref([])
const crisisBusy = ref('')
const crisisError = ref('')

async function loadCrisisEvents() {
  try {
    const res = await fetch(`${API_URL}/api/admin/crisis/events`, {
      headers: authHeaders(),
    })

    if (!res.ok) {
      throw new Error('Could not fetch crisis events')
    }

    crisisEvents.value = await res.json()
  } catch (e) {
    crisisError.value = e.message
  }
}

async function triggerCrisis(eventId) {
  if (crisisBusy.value) return

  crisisBusy.value = eventId
  crisisError.value = ''

  try {
    const res = await fetch(
      `${API_URL}/api/admin/crisis/events/${eventId}/trigger`,
      {
        method: 'POST',
        headers: authHeaders(),
      }
    )

    const data = await res.json()

    if (!res.ok) {
      throw new Error(
        data.detail || 'CRISIS TRIGGER FAILED'
      )
    }

    await loadCrisisEvents()
  } catch (e) {
    crisisError.value = e.message
  } finally {
    crisisBusy.value = ''
  }
}

async function resetCrisis() {
  if (crisisBusy.value) return

  crisisBusy.value = 'reset'
  crisisError.value = ''

  try {
    const res = await fetch(`${API_URL}/api/admin/crisis/reset`, {
      method: 'POST',
      headers: authHeaders(),
    })

    const data = await res.json()

    if (!res.ok) {
      throw new Error(
        data.detail || 'CRISIS RESET FAILED'
      )
    }

    await loadCrisisEvents()
  } catch (e) {
    crisisError.value = e.message
  } finally {
    crisisBusy.value = ''
  }
}

let poller = null

onMounted(() => {
  refresh()
  loadCrisisEvents()

  poller = setInterval(() => {
    refresh()
    loadCrisisEvents()
  }, 3000)
})

onUnmounted(() => {
  if (poller) {
    clearInterval(poller)
  }
})
</script>

<template>
  <div class="shell">

    <!-- LOGIN -->
    <template v-if="!isAuthenticated">

      <div class="auth-card">

        <div class="brand">
          E-SUMMIT ADMIN
        </div>

        <h1>Market Control</h1>

        <p class="muted">
          Sign in to manage the E-Summit market.
        </p>

        <form @submit.prevent="login">

          <label>
            Email

            <input
              v-model="email"
              type="email"
              autocomplete="username"
              required
            />
          </label>

          <label>
            Password

            <input
              v-model="password"
              type="password"
              autocomplete="current-password"
              required
            />
          </label>

          <p
            v-if="loginError"
            class="error"
          >
            {{ loginError }}
          </p>

          <button
            class="submit"
            type="submit"
            :disabled="loginBusy"
          >
            {{ loginBusy ? 'Logging in…' : 'Log in' }}
          </button>

        </form>

      </div>

    </template>


    <!-- ADMIN CONSOLE -->
    <template v-else>

      <div class="console">

        <!-- TOP BAR -->
        <header class="topbar">

          <div class="brand">
            E-SUMMIT ADMIN
          </div>

          <div
            class="state-pill"
            :class="currentState.toLowerCase()"
          >
            {{ currentState }}
          </div>

          <button
            class="logout"
            type="button"
            @click="logout"
          >
            Log out
          </button>

        </header>


        <!-- MARKET CONTROLS -->
        <section class="controls panel">

          <div class="section-header">

            <div>
              <h2>Market controls</h2>

              <p class="muted">
                Control the live market state.
              </p>
            </div>

            <div class="state-display">
              {{ currentState }}
            </div>

          </div>


          <div class="button-row">

            <button
              type="button"
              :disabled="!!actionBusy || resetBusy || !canStart"
              @click="runControl('start')"
            >
              {{ actionBusy === 'start' ? 'Starting…' : 'Start' }}
            </button>


            <button
              type="button"
              :disabled="!!actionBusy || resetBusy || !canPause"
              @click="runControl('pause')"
            >
              {{ actionBusy === 'pause' ? 'Pausing…' : 'Pause' }}
            </button>


            <button
              type="button"
              :disabled="!!actionBusy || resetBusy || !canResume"
              @click="runControl('resume')"
            >
              {{ actionBusy === 'resume' ? 'Resuming…' : 'Resume' }}
            </button>


            <button
              type="button"
              :disabled="!!actionBusy || resetBusy || !canEnd"
              @click="runControl('end')"
            >
              {{ actionBusy === 'end' ? 'Ending…' : 'End' }}
            </button>


            <button
              type="button"
              class="danger"
              :disabled="!!actionBusy || resetBusy || !canFreeze"
              @click="runControl('emergency-freeze')"
            >
              {{
                actionBusy === 'emergency-freeze'
                  ? 'Freezing…'
                  : 'Emergency Freeze'
              }}
            </button>


            <button
              type="button"
              :disabled="!!actionBusy || resetBusy || !canUnfreeze"
              @click="runControl('unfreeze')"
            >
              {{ actionBusy === 'unfreeze' ? 'Unfreezing…' : 'Unfreeze' }}
            </button>

          </div>


          <div
            v-if="actionError"
            class="error action-error"
          >
            {{ actionError }}
          </div>


          <!-- MARKET RESET -->
          <div class="reset-market-section">

            <div class="reset-market-info">

              <div class="reset-market-title">
                Market failsafe
              </div>

              <div class="reset-market-description">
                Restore all stock prices and the market clock to their
                original starting state.
              </div>

            </div>

            <button
              type="button"
              class="reset-market-button"
              :disabled="!canReset || !!actionBusy"
              @click="resetMarketToOriginal"
            >
              {{
                resetBusy
                  ? 'Resetting…'
                  : 'Reset Market'
              }}
            </button>

          </div>


          <div
            v-if="currentState === 'LIVE'"
            class="reset-market-hint"
          >
            Reset is disabled while the market is LIVE. Pause or freeze
            the market first.
          </div>


          <div
            v-if="resetError"
            class="error action-error"
          >
            {{ resetError }}
          </div>

        </section>


        <!-- CRISIS CONTROL -->
        <section class="crisis panel">

          <div class="section-header">

            <div>
              <h2>Crisis events</h2>

              <p class="muted">
                Trigger live market events during the simulation.
              </p>
            </div>

            <div class="crisis-actions">

              <div class="team-count">
                {{ crisisEvents.length }} events
              </div>

              <button
                type="button"
                class="crisis-reset"
                :disabled="!!crisisBusy"
                @click="resetCrisis"
              >
                {{
                  crisisBusy === 'reset'
                    ? 'Resetting…'
                    : 'Reset events'
                }}
              </button>

            </div>

          </div>


          <div
            v-if="crisisError"
            class="error action-error"
          >
            {{ crisisError }}
          </div>


          <div class="crisis-list">

            <div
              v-for="event in crisisEvents"
              :key="event.event_id"
              class="crisis-card"
            >

              <div class="crisis-info">

                <div class="crisis-type">
                  {{ event.type.replaceAll('_', ' ') }}
                </div>

                <h3>
                  {{ event.headline }}
                </h3>

                <p>
                  {{ event.description }}
                </p>

                <div class="crisis-impact">

                  <span>
                    {{ event.impact_direction }}
                  </span>

                  <span>
                    {{ (Number(event.impact_range_min) * 100).toFixed(0) }}%
                    →
                    {{ (Number(event.impact_range_max) * 100).toFixed(0) }}%
                  </span>

                </div>

              </div>


              <button
                type="button"
                class="crisis-trigger"
                :disabled="
                  !!crisisBusy ||
                  event.status === 'EXECUTED'
                "
                @click="triggerCrisis(event.event_id)"
              >
                {{
                  crisisBusy === event.event_id
                    ? 'Triggering…'
                    : event.status === 'EXECUTED'
                      ? 'Triggered'
                      : 'Trigger event'
                }}
              </button>

            </div>


            <div
              v-if="crisisEvents.length === 0"
              class="empty"
            >
              No crisis events available.
            </div>

          </div>

        </section>


        <!-- LEADERBOARD -->
        <section class="leaderboard panel">

          <div class="section-header">

            <div>
              <h2>Leaderboard</h2>

              <p class="muted">
                Live team rankings
              </p>
            </div>

            <div class="team-count">
              {{ leaderboard.length }} teams
            </div>

          </div>


          <div class="table-wrapper">

            <table>

              <thead>

                <tr>
                  <th>Rank</th>
                  <th>Team</th>
                  <th class="num">Cash</th>
                  <th class="num">Portfolio</th>
                  <th class="num">Net worth</th>
                  <th class="num">Return %</th>
                </tr>

              </thead>


              <tbody>

                <tr
                  v-for="row in leaderboard"
                  :key="row.team_id"
                >

                  <td>
                    <strong>
                      {{ row.rank }}
                    </strong>
                  </td>

                  <td>
                    {{ row.team_name }}
                  </td>

                  <td class="num tabular-num">
                    ₹{{ Number(row.cash).toFixed(2) }}
                  </td>

                  <td class="num tabular-num">
                    ₹{{ Number(row.portfolio_value).toFixed(2) }}
                  </td>

                  <td class="num tabular-num">
                    ₹{{ Number(row.net_worth).toFixed(2) }}
                  </td>

                  <td
                    class="num tabular-num"
                    :class="
                      Number(row.return_percent) >= 0
                        ? 'positive'
                        : 'negative'
                    "
                  >
                    {{ Number(row.return_percent).toFixed(2) }}%
                  </td>

                </tr>


                <tr v-if="leaderboard.length === 0">

                  <td
                    colspan="6"
                    class="empty"
                  >
                    No teams yet.
                  </td>

                </tr>

              </tbody>

            </table>

          </div>

        </section>

      </div>

    </template>

  </div>
</template>


<style scoped>

.shell {
  min-height: 100vh;
  background: var(--bg-base);
}

.auth-card {
  width: min(400px, calc(100% - 32px));
  margin: 100px auto;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 32px;
}

.auth-card h1 {
  margin: 30px 0 8px;
  font-size: 25px;
  color: var(--text-primary);
}

.muted {
  color: var(--text-secondary);
}

form {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-top: 24px;
}

label {
  display: flex;
  flex-direction: column;
  gap: 7px;
  font-size: 12px;
  color: var(--text-secondary);
}

input {
  width: 100%;
  background: var(--bg-base);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 11px 12px;
  color: var(--text-primary);
  font-size: 14px;
}

input:focus {
  outline: none;
  border-color: var(--accent);
}

.submit {
  background: var(--accent);
  border: none;
  border-radius: var(--radius-sm);
  color: #fff;
  padding: 11px 0;
  font-size: 14px;
  font-weight: 600;
}

button {
  cursor: pointer;
}

button:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.error {
  color: var(--negative);
  font-size: 12.5px;
}

.action-error {
  margin-top: 18px;
  padding: 12px;
  border: 1px solid var(--negative);
  border-radius: var(--radius-sm);
  background: rgba(255, 80, 90, 0.08);
}

.topbar {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px 24px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-panel);
}

.state-pill {
  font-size: 11px;
  letter-spacing: 0.05em;
  padding: 5px 10px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  color: var(--text-secondary);
}

.state-pill.waiting {
  color: var(--text-secondary);
}

.state-pill.live {
  color: var(--positive);
  border-color: var(--positive);
}

.state-pill.paused,
.state-pill.emergency_frozen {
  color: var(--warning);
  border-color: var(--warning);
}

.state-pill.ending {
  color: var(--warning);
  border-color: var(--warning);
}

.state-pill.closed {
  color: var(--negative);
  border-color: var(--negative);
}

.logout {
  margin-left: auto;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  padding: 7px 14px;
  font-size: 13px;
}

.console {
  min-height: 100vh;
}

.controls,
.leaderboard {
  margin: 20px 24px;
  padding: 22px;
}

.panel {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 18px;
}

h2 {
  font-size: 14px;
  color: var(--text-primary);
  font-weight: 600;
  margin: 0;
}

.section-header p {
  margin: 5px 0 0;
  font-size: 12px;
}

.state-display,
.team-count {
  color: var(--text-secondary);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.button-row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.button-row button {
  background: var(--bg-base);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  padding: 10px 16px;
  font-size: 13px;
  transition: opacity 0.15s ease;
}

.button-row button:hover:not(:disabled) {
  border-color: var(--accent);
}

.button-row button.danger {
  border-color: var(--negative);
  color: var(--negative);
}


/*
 * MARKET RESET
 */

.reset-market-section {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  margin-top: 20px;
  padding-top: 18px;
  border-top: 1px solid var(--border);
}

.reset-market-info {
  min-width: 0;
}

.reset-market-title {
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 600;
}

.reset-market-description {
  margin-top: 5px;
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 1.5;
}

.reset-market-button {
  flex-shrink: 0;
  background: transparent;
  border: 1px solid var(--negative);
  border-radius: var(--radius-sm);
  color: var(--negative);
  padding: 10px 16px;
  font-size: 13px;
  font-weight: 600;
  transition:
    background 0.15s ease,
    border-color 0.15s ease,
    opacity 0.15s ease;
}

.reset-market-button:hover:not(:disabled) {
  background: rgba(255, 80, 90, 0.08);
  border-color: var(--negative);
}

.reset-market-hint {
  margin-top: 10px;
  color: var(--warning);
  font-size: 11px;
}


/*
 * CRISIS
 */

.crisis-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.crisis-reset {
  background: transparent;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  padding: 7px 10px;
  font-size: 11px;
  cursor: pointer;
}

.crisis-reset:hover:not(:disabled) {
  border-color: var(--accent);
  color: var(--text-primary);
}

.crisis-reset:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.table-wrapper {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

th {
  text-align: left;
  color: var(--text-secondary);
  font-weight: 500;
  padding: 10px;
  border-bottom: 1px solid var(--border);
}

td {
  padding: 11px 10px;
  border-bottom: 1px solid var(--border);
  color: var(--text-primary);
}

.num {
  text-align: right;
}

.tabular-num {
  font-variant-numeric: tabular-nums;
}

.positive {
  color: var(--positive);
}

.negative {
  color: var(--negative);
}

.empty {
  text-align: center;
  color: var(--text-muted);
  padding: 25px;
}

@media (max-width: 700px) {

  .topbar {
    padding: 14px;
  }

  .controls,
  .leaderboard {
    margin: 14px;
    padding: 16px;
  }

  .section-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .button-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
  }

  .button-row button {
    width: 100%;
  }

  .reset-market-section {
    align-items: flex-start;
    flex-direction: column;
  }

  .reset-market-button {
    width: 100%;
  }

}

</style>
```

### Then build it

After replacing the file:

```bash
cd ~/Projects/e-summit-market
npm --prefix apps/admin run build
```

If that says the build succeeded, restart/reload your admin frontend.

Your market controls should now look roughly like:

**Start | Pause | Resume | End | Emergency Freeze | Unfreeze**

Then below them:

> **Market failsafe**
> Restore all stock prices and the market clock to their original starting state.
> **[ Reset Market ]**

The button will be **disabled while LIVE**, and clicking it while paused/frozen/closed will require confirmation before calling the already-tested backend endpoint.
