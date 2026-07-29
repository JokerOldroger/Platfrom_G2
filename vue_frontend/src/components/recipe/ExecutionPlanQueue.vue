<template>
    <div v-if="steps.length" class="queue-table">
        <div class="queue-table__head">
            <span>Step</span>
            <span>Type</span>
            <span>Interface</span>
            <span>Target</span>
            <span>Seeded Action</span>
            <span>Parameters</span>
        </div>
        <article class="queue-row" v-for="step in steps" :key="step.id">
            <div class="queue-cell">
                <span class="queue-step">{{ step.step_no }}</span>
                <span class="queue-name">{{ step.name || step.step_type }}</span>
            </div>
            <div class="queue-cell">{{ step.step_type }}</div>
            <div class="queue-cell">
                <span class="interface-badge" :class="interfaceBadgeClass(resolveStepInterface(step))">
                    {{ resolveStepInterface(step) }}
                </span>
            </div>
            <div class="queue-cell queue-cell--mono">{{ resolveStepTarget(step) }}</div>
            <div class="queue-cell">{{ summariseSeededAction(step) }}</div>
            <div class="queue-cell">
                <pre>{{ formatParameters(step.parameters) }}</pre>
            </div>
        </article>
    </div>

    <div v-else class="empty-state">
        Resolve a plan to inspect the generated device sequence.
    </div>
</template>

<script>
export default {
    name: 'ExecutionPlanQueue',
    props: {
        steps: {
            type: Array,
            default: () => []
        }
    },
    methods: {
        formatParameters(parameters) {
            return JSON.stringify(parameters || {}, null, 2)
        },
        resolveStepInterface(step) {
            if (step.parameters?.interface_type) {
                return step.parameters.interface_type
            }
            if (['STIR', 'DISPENSE'].includes(step.step_type)) {
                return 'topic'
            }
            if (['MOVE_ARM', 'HEAT', 'CLEAN'].includes(step.step_type)) {
                return 'action'
            }
            if (['WAIT', 'SAMPLE'].includes(step.step_type)) {
                return 'service'
            }
            return 'topic'
        },
        resolveStepTarget(step) {
            const parameters = step.parameters || {}
            return parameters.topic
                || parameters.action_name
                || parameters.route_name
                || parameters.device_id
                || 'backend-managed route'
        },
        summariseSeededAction(step) {
            const parameters = step.parameters || {}
            if (step.step_type === 'STIR') {
                const speed = parameters.speed_key ? `speed=${parameters.speed_key}` : 'speed=recipe default'
                const duration = parameters.duration_sec != null
                    ? `duration=${parameters.duration_sec}s`
                    : parameters.fixed_rotations != null
                        ? `rotations=${parameters.fixed_rotations}`
                        : 'duration=backend computed'
                return `motor=${parameters.motor || 'n/a'} · ${speed} · ${duration}`
            }
            if (step.step_type === 'MOVE_ARM') {
                const trajectory = parameters.goal?.trajectory || []
                return `arm=${parameters.device_id || 'n/a'} · waypoint=${trajectory.join(' -> ') || 'n/a'}`
            }
            if (step.step_type === 'WAIT') {
                return parameters.wait_until || parameters.duration_sec
                    ? `wait=${parameters.wait_until || `${parameters.duration_sec}s`}`
                    : 'backend wait'
            }
            return parameters.device_id ? `device=${parameters.device_id}` : 'backend step'
        },
        interfaceBadgeClass(interfaceType) {
            return `interface-badge--${interfaceType || 'topic'}`
        }
    }
}
</script>

<style scoped>
.queue-table {
    border-radius: 18px;
    overflow: hidden;
    border: 1px solid rgba(15, 23, 36, 0.08);
}

.queue-table__head,
.queue-row {
    display: grid;
    grid-template-columns: 0.9fr 0.65fr 0.7fr 1fr 1.1fr 1.5fr;
    gap: 0.75rem;
    align-items: start;
    padding: 0.95rem 1rem;
}

.queue-table__head {
    background: #ecf2f8;
    color: #5f6d81;
    font-size: 0.74rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 700;
}

.queue-row {
    background: #ffffff;
    border-top: 1px solid rgba(15, 23, 36, 0.06);
}

.queue-row:nth-child(even) {
    background: #fafcfe;
}

.queue-cell {
    color: #1f2937;
    font-size: 0.92rem;
}

.queue-cell pre {
    margin: 0;
    padding: 0.85rem;
    background: #0f172a;
    color: #e2e8f0;
    border-radius: 14px;
    font-size: 0.8rem;
    overflow: auto;
    white-space: pre-wrap;
    word-break: break-word;
}

.queue-cell--mono {
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
    font-size: 0.84rem;
}

.queue-step {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 34px;
    height: 34px;
    border-radius: 10px;
    background: #e5edf6;
    color: #274c7d;
    font-size: 0.8rem;
    font-weight: 700;
    margin-right: 0.65rem;
}

.queue-name {
    font-weight: 700;
    color: #111827;
}

.interface-badge {
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

.empty-state {
    padding: 1.6rem;
    border-radius: 18px;
    border: 1px dashed rgba(100, 116, 139, 0.28);
    color: #64748b;
    background: #fbfcfd;
}

@media screen and (max-width: 960px) {
    .queue-table__head,
    .queue-row {
        grid-template-columns: 1fr;
    }
}
</style>
