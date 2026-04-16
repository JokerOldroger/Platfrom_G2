<template>
    <section class="ws-console">
        <header class="ws-header">
            <div>
                <p class="ws-header__eyebrow">Realtime Telemetry</p>
                <h1 class="title ws-header__title">Device Reply Console</h1>
                <p class="ws-header__copy">
                    Inspect legacy motor telemetry and the new standard `device_reply` stream for service and action execution.
                </p>
            </div>
            <div class="ws-header__status">
                <div class="status-chip">
                    <span class="status-chip__label">Socket</span>
                    <span class="status-chip__value">{{ socketState }}</span>
                </div>
                <div class="status-chip">
                    <span class="status-chip__label">Replies</span>
                    <span class="status-chip__value">{{ deviceReplies.length }}</span>
                </div>
            </div>
        </header>

        <section class="metric-row">
            <article class="metric-card">
                <span class="metric-card__label">Events Captured</span>
                <span class="metric-card__value">{{ events.length }}</span>
            </article>
            <article class="metric-card">
                <span class="metric-card__label">Legacy Motor Events</span>
                <span class="metric-card__value">{{ legacyMotorEvents.length }}</span>
            </article>
            <article class="metric-card">
                <span class="metric-card__label">Action Replies</span>
                <span class="metric-card__value">{{ actionReplies.length }}</span>
            </article>
            <article class="metric-card metric-card--alert">
                <span class="metric-card__label">Error Replies</span>
                <span class="metric-card__value">{{ failedReplies.length }}</span>
            </article>
        </section>

        <div class="ws-grid">
            <section class="panel-card">
                <div class="panel-header">
                    <div>
                        <p class="panel-kicker">Device Reply</p>
                        <h2 class="panel-title">Service / Action Status</h2>
                    </div>
                    <span class="panel-badge">Structured Replies</span>
                </div>

                <div v-if="deviceReplies.length" class="reply-table">
                    <div class="reply-table__head">
                        <span>Route</span>
                        <span>Interface</span>
                        <span>Status</span>
                        <span>Summary</span>
                    </div>
                    <article class="reply-row" v-for="reply in deviceReplies" :key="reply.key">
                        <div class="reply-cell">
                            <div class="reply-route">{{ reply.routeName }}</div>
                            <div class="reply-sub">{{ reply.deviceLabel }}</div>
                        </div>
                        <div class="reply-cell">
                            <span class="interface-badge" :class="interfaceBadgeClass(reply.interfaceType)">{{ reply.interfaceType }}</span>
                        </div>
                        <div class="reply-cell">
                            <span class="status-badge" :class="statusBadgeClass(reply.status)">{{ reply.status }}</span>
                        </div>
                        <div class="reply-cell">
                            <div class="reply-summary">{{ reply.summary }}</div>
                            <div class="reply-sub">{{ reply.time }}</div>
                        </div>
                    </article>
                </div>

                <div v-else class="empty-state">
                    No structured service/action replies received yet.
                </div>
            </section>

            <section class="panel-card">
                <div class="panel-header">
                    <div>
                        <p class="panel-kicker">Legacy ESP32 Feed</p>
                        <h2 class="panel-title">Motor Telemetry</h2>
                    </div>
                    <span class="panel-badge">Backward Compatible</span>
                </div>

                <div v-if="devices.length" class="device-stack">
                    <article class="device-card" v-for="device in devices" :key="device.id">
                        <div class="device-card__head">
                            <div>
                                <p class="device-card__title">ESP32_{{ device.id }}</p>
                                <p class="device-card__meta">Latest command: Motor {{ cmd.motor }} / speed {{ cmd.speed }} / time {{ cmd.time }}</p>
                            </div>
                        </div>

                        <div class="motor-grid">
                            <article class="motor-card" v-for="motor in device.motors" :key="motor.id">
                                <p class="motor-card__title">Motor {{ motor.id }}</p>
                                <p><strong>Status</strong> {{ motor.status }}</p>
                                <p><strong>Command</strong> {{ motor.time }}s @ {{ motor.speed }}</p>
                                <p><strong>PWM</strong> {{ motor.pwm }}</p>
                                <p><strong>PCNT</strong> {{ motor.pcnt }}</p>
                            </article>
                        </div>
                    </article>
                </div>

                <div v-else class="empty-state">
                    No legacy motor devices initialised.
                </div>
            </section>
        </div>

        <section class="panel-card panel-card--stream">
            <div class="panel-header">
                <div>
                    <p class="panel-kicker">Raw Stream</p>
                    <h2 class="panel-title">Realtime Event Timeline</h2>
                </div>
                <span class="panel-badge">WebSocket Feed</span>
            </div>

            <div v-if="events.length" class="event-stream">
                <article class="event-card" v-for="event in events" :key="event.key">
                    <div class="event-card__head">
                        <span class="event-topic">{{ event.topic }}</span>
                        <span class="event-time">{{ event.time }}</span>
                    </div>
                    <p class="event-summary">{{ event.summary }}</p>
                </article>
            </div>

            <div v-else class="empty-state">
                Realtime websocket events will appear here after the backend broadcasts MQTT updates.
            </div>
        </section>
    </section>
</template>

<script>
export default {
    name: 'WebsocketConsoleView',
    mounted() {
        this.initDevices()
        this.connectWebsocket()
    },
    beforeUnmount() {
        if (this.client) {
            this.client.close()
        }
    },
    data() {
        return {
            client: null,
            socketState: 'Connecting',
            cmd: {
                motor: -1,
                speed: -1,
                time: -1
            },
            devices: [],
            events: []
        }
    },
    computed: {
        deviceReplies() {
            return this.events.filter(event => event.topic === 'device_reply')
        },
        legacyMotorEvents() {
            return this.events.filter(event => ['cmd', 'task_create', 'task_done', 'pcnt', 'pwm'].includes(event.topic))
        },
        actionReplies() {
            return this.deviceReplies.filter(event => event.interfaceType === 'action')
        },
        failedReplies() {
            return this.deviceReplies.filter(event => event.status === 'failed' || event.messageType === 'error')
        }
    },
    methods: {
        connectWebsocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
            this.client = new WebSocket(`${protocol}://127.0.0.1:8000/websocket/`)
            this.client.onopen = () => {
                this.socketState = 'Connected'
            }
            this.client.onclose = () => {
                this.socketState = 'Closed'
            }
            this.client.onerror = () => {
                this.socketState = 'Error'
            }
            this.client.onmessage = this.onMessage
        },
        initDevices() {
            for (let i = 0; i < 1; i += 1) {
                const device = {
                    id: i + 1,
                    motors: []
                }
                for (let j = 0; j < 4; j += 1) {
                    device.motors.push({
                        id: j,
                        status: 'Idle',
                        speed: -1,
                        time: -1,
                        pwm: -1,
                        pcnt: -1
                    })
                }
                this.devices.push(device)
            }
        },
        onMessage(event) {
            const payload = JSON.parse(event.data)

            if (payload.topic === 'device_reply') {
                this.pushEvent(this.normaliseDeviceReply(payload))
                return
            }

            this.updateLegacyDeviceState(payload)
            this.pushEvent(this.normaliseLegacyEvent(payload))
        },
        updateLegacyDeviceState(payload) {
            const deviceIndex = (payload.device || 1) - 1
            const device = this.devices[deviceIndex]
            if (!device || payload.motor == null) {
                return
            }

            const motor = device.motors[payload.motor]
            if (!motor) {
                return
            }

            switch (payload.topic) {
                case 'task_create':
                    motor.status = 'Busy'
                    motor.speed = payload.speed
                    motor.time = payload.time
                    break
                case 'task_done':
                    motor.status = 'Finished'
                    break
                case 'pwm':
                    motor.pwm = payload.pwm
                    break
                case 'pcnt':
                    motor.pcnt = payload.pcnt
                    break
                case 'cmd':
                    this.cmd.motor = payload.motor
                    this.cmd.speed = payload.speed
                    this.cmd.time = payload.time
                    break
                default:
                    break
            }
        },
        normaliseLegacyEvent(payload) {
            const summary = payload.topic === 'cmd'
                ? `Motor ${payload.motor} command speed=${payload.speed}, time=${payload.time}`
                : payload.topic === 'task_create'
                    ? `Motor ${payload.motor} task started for ${payload.time}s at speed ${payload.speed}`
                    : payload.topic === 'task_done'
                        ? `Motor ${payload.motor} task completed`
                        : payload.topic === 'pcnt'
                            ? `Motor ${payload.motor} PCNT=${payload.pcnt}`
                            : payload.topic === 'pwm'
                                ? `Motor ${payload.motor} PWM=${payload.pwm}`
                                : JSON.stringify(payload)

            return {
                key: `${Date.now()}-${Math.random()}`,
                topic: payload.topic || 'legacy',
                time: new Date().toLocaleTimeString(),
                summary
            }
        },
        normaliseDeviceReply(payload) {
            const body = payload.payload || {}
            const routeName = payload.route_name || body.route_name || 'device route'
            const deviceLabel = [payload.device_type, payload.device_id].filter(Boolean).join(':') || 'device'
            const summary = payload.message_type === 'ack'
                ? `${routeName} accepted by ${deviceLabel}`
                : payload.message_type === 'progress'
                    ? `${routeName} running${body.progress?.percent != null ? ` at ${body.progress.percent}%` : ''}${body.progress?.stage ? ` • ${body.progress.stage}` : ''}`
                    : payload.message_type === 'result'
                        ? `${routeName} completed successfully`
                        : `${routeName} failed: ${body.error?.message || body.message || 'unknown error'}`

            return {
                key: `${Date.now()}-${Math.random()}`,
                topic: 'device_reply',
                time: new Date().toLocaleTimeString(),
                summary,
                routeName,
                interfaceType: payload.interface_type || 'unknown',
                messageType: payload.message_type || 'unknown',
                status: payload.status || 'unknown',
                deviceLabel
            }
        },
        pushEvent(event) {
            this.events.unshift(event)
            this.events = this.events.slice(0, 20)
        },
        interfaceBadgeClass(interfaceType) {
            return `interface-badge--${interfaceType || 'topic'}`
        },
        statusBadgeClass(status) {
            if (['failed'].includes(status)) {
                return 'status-badge--failed'
            }
            if (['succeeded', 'done', 'completed'].includes(status)) {
                return 'status-badge--done'
            }
            if (['running', 'executing'].includes(status)) {
                return 'status-badge--running'
            }
            return 'status-badge--queued'
        }
    }
}
</script>

<style scoped>
.ws-console {
    padding: 1.25rem;
    min-height: calc(100vh - 4rem);
    background:
        linear-gradient(180deg, #101925 0%, #152132 22%, #eef3f8 22%, #eef3f8 100%);
}

.ws-header {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: 1.4rem;
    padding: 1.25rem 1.4rem;
    border-radius: 20px;
    background: linear-gradient(180deg, rgba(9, 14, 22, 0.88) 0%, rgba(19, 29, 45, 0.9) 100%);
    border: 1px solid rgba(148, 163, 184, 0.15);
    box-shadow: 0 18px 40px rgba(5, 10, 18, 0.3);
}

.ws-header__eyebrow,
.panel-kicker {
    margin-bottom: 0.3rem;
    color: #8fb3d9;
    font-size: 0.8rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    font-weight: 700;
}

.ws-header__title {
    margin-bottom: 0.45rem !important;
    color: #f8fafc;
}

.ws-header__copy {
    max-width: 56rem;
    color: #adbacd;
    line-height: 1.6;
}

.ws-header__status {
    display: flex;
    gap: 0.8rem;
}

.status-chip {
    display: flex;
    flex-direction: column;
    justify-content: center;
    min-width: 120px;
    padding: 0.8rem 0.95rem;
    border-radius: 16px;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(148, 163, 184, 0.14);
}

.status-chip__label {
    color: #8ea2bd;
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}

.status-chip__value {
    color: #f8fafc;
    font-size: 0.98rem;
    font-weight: 700;
}

.metric-row {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0.85rem;
    margin-bottom: 1.4rem;
}

.metric-card {
    display: flex;
    flex-direction: column;
    gap: 0.22rem;
    padding: 0.95rem 1rem;
    border-radius: 16px;
    background: #ffffff;
    border: 1px solid rgba(15, 23, 36, 0.08);
    box-shadow: 0 10px 24px rgba(15, 23, 36, 0.08);
}

.metric-card--alert {
    border-left: 4px solid #d4584f;
}

.metric-card__label {
    color: #64748b;
    font-size: 0.76rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 700;
}

.metric-card__value {
    color: #111827;
    font-size: 1.05rem;
    font-weight: 700;
}

.ws-grid {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: 1.25rem;
    margin-bottom: 1.25rem;
}

.panel-card {
    padding: 1.35rem;
    border-radius: 20px;
    background: rgba(255, 255, 255, 0.96);
    border: 1px solid rgba(13, 22, 38, 0.08);
    box-shadow: 0 14px 36px rgba(15, 23, 36, 0.08);
}

.panel-card--stream {
    margin-bottom: 1rem;
}

.panel-header {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    align-items: flex-start;
    margin-bottom: 1rem;
}

.panel-title {
    color: #111827;
    font-size: 1.18rem;
    font-weight: 700;
}

.panel-badge {
    display: inline-flex;
    align-items: center;
    height: fit-content;
    padding: 0.3rem 0.7rem;
    border-radius: 999px;
    background: #eef3fb;
    color: #325891;
    font-size: 0.76rem;
    font-weight: 700;
}

.reply-table {
    border-radius: 18px;
    overflow: hidden;
    border: 1px solid rgba(15, 23, 36, 0.08);
}

.reply-table__head,
.reply-row {
    display: grid;
    grid-template-columns: 1fr 0.7fr 0.7fr 1.4fr;
    gap: 0.75rem;
    align-items: start;
    padding: 0.95rem 1rem;
}

.reply-table__head {
    background: #ecf2f8;
    color: #5f6d81;
    font-size: 0.74rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 700;
}

.reply-row {
    background: #ffffff;
    border-top: 1px solid rgba(15, 23, 36, 0.06);
}

.reply-row:nth-child(even) {
    background: #fafcfe;
}

.reply-cell {
    color: #1f2937;
    font-size: 0.92rem;
}

.reply-route,
.device-card__title,
.motor-card__title {
    color: #111827;
    font-weight: 700;
}

.reply-sub,
.device-card__meta {
    color: #64748b;
    font-size: 0.82rem;
}

.reply-summary {
    color: #475569;
    line-height: 1.55;
}

.interface-badge,
.status-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 84px;
    padding: 0.28rem 0.55rem;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}

.interface-badge--topic {
    background: #edf6ff;
    color: #1f5f95;
}

.interface-badge--service {
    background: #f1f5e8;
    color: #4f6f1f;
}

.interface-badge--action {
    background: #fff3e8;
    color: #9a5711;
}

.status-badge--queued {
    background: #edf2ff;
    color: #3651a3;
}

.status-badge--running {
    background: #eef9f3;
    color: #1f7a4c;
}

.status-badge--done {
    background: #eef9f3;
    color: #1f7a4c;
}

.status-badge--failed {
    background: #fff1f1;
    color: #a13b3b;
}

.device-stack,
.event-stream {
    display: grid;
    gap: 0.85rem;
}

.device-card,
.event-card,
.motor-card {
    border-radius: 16px;
    border: 1px solid rgba(15, 23, 36, 0.08);
    background: #f9fbfe;
}

.device-card {
    padding: 1rem;
}

.motor-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.75rem;
    margin-top: 0.85rem;
}

.motor-card {
    padding: 0.9rem 1rem;
}

.motor-card p {
    color: #475569;
    margin-bottom: 0.25rem;
}

.event-card {
    padding: 0.95rem 1rem;
}

.event-card__head {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: 0.35rem;
}

.event-topic {
    color: #111827;
    font-weight: 700;
}

.event-time {
    color: #64748b;
    font-size: 0.82rem;
}

.event-summary {
    color: #475569;
    line-height: 1.55;
}

.empty-state {
    padding: 1.6rem;
    border-radius: 18px;
    border: 1px dashed rgba(100, 116, 139, 0.28);
    color: #64748b;
    background: #fbfcfd;
}

@media screen and (max-width: 1080px) {
    .metric-row,
    .ws-grid {
        grid-template-columns: 1fr;
    }
}

@media screen and (max-width: 860px) {
    .reply-table__head,
    .reply-row,
    .motor-grid {
        grid-template-columns: 1fr;
    }
}

@media screen and (max-width: 768px) {
    .ws-console {
        padding: 1rem;
    }

    .ws-header {
        flex-direction: column;
    }

    .ws-header__status {
        flex-wrap: wrap;
    }
}
</style>
