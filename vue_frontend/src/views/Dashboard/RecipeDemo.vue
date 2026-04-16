<template>
    <section class="recipe-console">
        <header class="console-header">
            <div>
                <p class="eyebrow">Recipe Control Console</p>
                <h1 class="title console-title">Material Execution Workspace</h1>
                <p class="console-copy">
                    Resolve a material request into backend recipe logic, inspect the generated execution plan, and dispatch live device commands from one operator surface.
                </p>
            </div>
            <div class="console-header__status">
                <div class="status-chip">
                    <span class="status-chip__label">MQTT</span>
                    <span class="status-chip__value">{{ startResult ? (startResult.mqtt_available ? 'Ready' : 'Offline') : 'Unknown' }}</span>
                </div>
                <div class="status-chip">
                    <span class="status-chip__label">Job</span>
                    <span class="status-chip__value">{{ jobStatus?.job?.status || createdJob?.status || 'Not Started' }}</span>
                </div>
            </div>
        </header>

        <section class="metric-row">
            <article class="metric-card">
                <span class="metric-card__label">Selected Material</span>
                <span class="metric-card__value">{{ selectedMaterialName }}</span>
            </article>
            <article class="metric-card">
                <span class="metric-card__label">Resolved Recipe</span>
                <span class="metric-card__value">{{ selectedRecipe ? recipeLabel(selectedRecipe) : 'None' }}</span>
            </article>
            <article class="metric-card">
                <span class="metric-card__label">Dispatched Commands</span>
                <span class="metric-card__value">{{ startResult ? startResult.dispatched_messages.length : 0 }}</span>
            </article>
            <article class="metric-card metric-card--alert">
                <span class="metric-card__label">Failed Steps</span>
                <span class="metric-card__value">{{ jobStatus?.step_status_counts?.failed || 0 }}</span>
            </article>
        </section>

        <div class="console-grid">
            <section class="panel-card panel-card--form">
                <div class="panel-header">
                    <div>
                        <p class="panel-kicker">Operator Input</p>
                        <h2 class="panel-title">Recipe Request</h2>
                    </div>
                    <span class="panel-badge">Control Entry</span>
                </div>

                <div class="form-grid">
                    <div class="field">
                        <label class="label">Selection Mode</label>
                        <div class="mode-switch">
                            <button class="button mode-switch__button" :class="inputMode === 'material' ? 'is-dark' : 'is-light'" @click="inputMode = 'material'">
                                Material
                            </button>
                            <button class="button mode-switch__button" :class="inputMode === 'recipe' ? 'is-dark' : 'is-light'" @click="inputMode = 'recipe'">
                                Recipe
                            </button>
                        </div>
                    </div>

                    <div class="field" v-if="inputMode === 'material'">
                        <label class="label">Material Type</label>
                        <div class="select is-fullwidth">
                            <select v-model="selectedMaterialId" @change="onMaterialChange">
                                <option disabled value="">Select a material</option>
                                <option v-for="material in materials" :key="material.id" :value="material.id">
                                    {{ material.name }}
                                </option>
                            </select>
                        </div>
                    </div>

                    <div class="field" v-if="inputMode === 'recipe'">
                        <label class="label">Recipe</label>
                        <div class="select is-fullwidth">
                            <select v-model="selectedRecipeId" @change="onRecipeChange">
                                <option disabled value="">Select a recipe</option>
                                <option v-for="recipe in recipes" :key="recipe.id" :value="recipe.id">
                                    {{ recipeLabel(recipe) }}
                                </option>
                            </select>
                        </div>
                    </div>

                    <div class="field">
                        <label class="label">Operator</label>
                        <div class="control">
                            <input class="input" type="text" v-model="operator" placeholder="operator_demo">
                        </div>
                    </div>

                    <div class="field">
                        <label class="label">Override Temperature (deg C)</label>
                        <div class="control">
                            <input class="input" type="number" step="0.1" v-model="overrides.reaction_temperature_c" placeholder="90.0">
                        </div>
                    </div>

                    <div class="field">
                        <label class="label">Override Stirring Speed (rpm)</label>
                        <div class="control">
                            <input class="input" type="number" v-model="overrides.stirring_speed_rpm" placeholder="700">
                        </div>
                    </div>
                </div>

                <div class="command-actions">
                    <button class="button is-dark" @click="previewPlan" :disabled="!resolvedRecipeId || loadingPreview">
                        {{ loadingPreview ? 'Resolving…' : 'Resolve Plan' }}
                    </button>
                    <button class="button is-info is-light" @click="createDemoJob" :disabled="!previewReady || creatingJob">
                        {{ creatingJob ? 'Creating…' : 'Create Job' }}
                    </button>
                    <button class="button is-success" @click="startDemoJob" :disabled="!createdJob || startingJob">
                        {{ startingJob ? 'Dispatching…' : 'Dispatch to Devices' }}
                    </button>
                </div>

                <div v-if="formMessage" class="console-message console-message--info">
                    {{ formMessage }}
                </div>

                <div v-if="errorMessage" class="console-message console-message--error">
                    {{ errorMessage }}
                </div>
            </section>

            <section class="panel-card">
                <div class="panel-header">
                    <div>
                        <p class="panel-kicker">Resolved Recipe</p>
                        <h2 class="panel-title">Process Parameters</h2>
                    </div>
                    <span class="panel-badge">Backend Match</span>
                </div>

                <div v-if="selectedRecipe" class="parameter-grid">
                    <article class="parameter-card">
                        <span class="parameter-card__label">Material</span>
                        <span class="parameter-card__value">{{ selectedMaterialName }}</span>
                    </article>
                    <article class="parameter-card">
                        <span class="parameter-card__label">Recipe</span>
                        <span class="parameter-card__value">{{ recipeLabel(selectedRecipe) }}</span>
                    </article>
                    <article class="parameter-card">
                        <span class="parameter-card__label">DMAc</span>
                        <span class="parameter-card__value">{{ selectedRecipe.dmac_dosage_ml ?? 'N/A' }} mL</span>
                    </article>
                    <article class="parameter-card">
                        <span class="parameter-card__label">Water</span>
                        <span class="parameter-card__value">{{ selectedRecipe.water_dosage_ml ?? 'N/A' }} mL</span>
                    </article>
                    <article class="parameter-card">
                        <span class="parameter-card__label">Solvent pH</span>
                        <span class="parameter-card__value">{{ selectedRecipe.solvent_ph ?? 'N/A' }}</span>
                    </article>
                    <article class="parameter-card">
                        <span class="parameter-card__label">Temperature</span>
                        <span class="parameter-card__value">{{ previewParameters.reaction_temperature_c ?? selectedRecipe.reaction_temperature_c ?? 'N/A' }} deg C</span>
                    </article>
                    <article class="parameter-card">
                        <span class="parameter-card__label">Stirring Speed</span>
                        <span class="parameter-card__value">{{ previewParameters.stirring_speed_rpm ?? selectedRecipe.stirring_speed_rpm ?? 'N/A' }} rpm</span>
                    </article>
                    <article class="parameter-card">
                        <span class="parameter-card__label">Stirring Time</span>
                        <span class="parameter-card__value">{{ selectedRecipe.stirring_duration_min ?? 'N/A' }} min</span>
                    </article>
                </div>

                <div v-else class="empty-state">
                    Select a material or recipe to load backend recipe parameters.
                </div>
            </section>
        </div>

        <div class="console-grid console-grid--bottom">
            <section class="panel-card">
                <div class="panel-header">
                    <div>
                        <p class="panel-kicker">Execution Plan</p>
                        <h2 class="panel-title">Device Step Queue</h2>
                    </div>
                    <span class="panel-badge">{{ steps.length }} Step{{ steps.length === 1 ? '' : 's' }}</span>
                </div>

                <div v-if="steps.length" class="queue-table">
                    <div class="queue-table__head">
                        <span>Step</span>
                        <span>Type</span>
                        <span>Interface</span>
                        <span>Target Topic</span>
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
                        <div class="queue-cell queue-cell--mono">{{ step.parameters?.topic || 'robot/actions' }}</div>
                        <div class="queue-cell">
                            <pre>{{ formatParameters(step.parameters) }}</pre>
                        </div>
                    </article>
                </div>

                <div v-else class="empty-state">
                    Resolve a plan to inspect the generated device sequence.
                </div>
            </section>

            <section class="panel-card">
                <div class="panel-header">
                    <div>
                        <p class="panel-kicker">Execution State</p>
                        <h2 class="panel-title">Dispatch and Job Status</h2>
                    </div>
                    <span class="panel-badge">{{ createdJob ? `Job ${createdJob.id}` : 'No Job' }}</span>
                </div>

                <div v-if="jobStatus" class="status-grid">
                    <article class="status-box">
                        <span class="status-box__label">Job</span>
                        <span class="status-box__value">{{ jobStatus.job.status }}</span>
                    </article>
                    <article class="status-box">
                        <span class="status-box__label">Running</span>
                        <span class="status-box__value">{{ jobStatus.step_status_counts.running }}</span>
                    </article>
                    <article class="status-box">
                        <span class="status-box__label">Queued</span>
                        <span class="status-box__value">{{ jobStatus.step_status_counts.queued }}</span>
                    </article>
                    <article class="status-box">
                        <span class="status-box__label">Failed</span>
                        <span class="status-box__value">{{ jobStatus.step_status_counts.failed }}</span>
                    </article>
                </div>

                <div v-if="jobStatus?.outbox_messages?.length" class="outbox-table">
                    <div class="outbox-table__head">
                        <span>Topic</span>
                        <span>Interface</span>
                        <span>Status</span>
                        <span>Payload</span>
                    </div>
                    <article class="outbox-row" v-for="message in jobStatus.outbox_messages" :key="message.id">
                        <div class="outbox-cell outbox-cell--mono">{{ message.topic }}</div>
                        <div class="outbox-cell">
                            <span class="interface-badge" :class="interfaceBadgeClass(message.payload?.interface_type)">
                                {{ message.payload?.interface_type || 'topic' }}
                            </span>
                        </div>
                        <div class="outbox-cell">{{ message.status }}</div>
                        <div class="outbox-cell">
                            <pre>{{ formatParameters(message.payload) }}</pre>
                        </div>
                    </article>
                </div>

                <div v-else class="empty-state">
                    Create and dispatch a job to inspect outbox traffic and step state.
                </div>

                <div v-if="jobStatus?.step_executions?.length" class="reply-board">
                    <div class="reply-board__head">
                        <span>Step Runtime</span>
                        <span>Interface</span>
                        <span>Status</span>
                        <span>Latest Reply</span>
                    </div>
                    <article class="reply-row" v-for="execution in jobStatus.step_executions" :key="execution.id">
                        <div class="reply-cell">
                            <span class="queue-step">{{ execution.command_payload?.step_no || execution.id }}</span>
                            <span class="queue-name">{{ execution.command_payload?.name || execution.recipe_step }}</span>
                        </div>
                        <div class="reply-cell">
                            <span class="interface-badge" :class="interfaceBadgeClass(execution.command_payload?.interface_type)">
                                {{ execution.command_payload?.interface_type || 'topic' }}
                            </span>
                        </div>
                        <div class="reply-cell">{{ execution.status }}</div>
                        <div class="reply-cell">
                            <div class="reply-meta" v-if="execution.telemetry?.last_reply_message_type">
                                <span class="reply-type">{{ execution.telemetry.last_reply_message_type }}</span>
                                <span class="reply-status">{{ execution.telemetry.last_reply_status || 'n/a' }}</span>
                            </div>
                            <div class="reply-copy">{{ summariseExecutionReply(execution) }}</div>
                        </div>
                    </article>
                </div>
            </section>
        </div>

        <div class="console-grid console-grid--bottom">
            <section class="panel-card">
                <div class="panel-header">
                    <div>
                        <p class="panel-kicker">Realtime Feed</p>
                        <h2 class="panel-title">Device Event Stream</h2>
                    </div>
                    <span class="panel-badge">WebSocket</span>
                </div>

                <div v-if="liveEvents.length" class="event-stream">
                    <article class="event-card" v-for="event in liveEvents" :key="event.key">
                        <div class="event-card__head">
                            <span class="event-topic">
                                {{ event.topic }}
                                <span v-if="event.interfaceType" class="event-topic__meta">{{ event.interfaceType }}</span>
                            </span>
                            <span class="event-time">{{ event.time }}</span>
                        </div>
                        <p class="event-summary">{{ event.summary }}</p>
                        <div v-if="event.progressLabel" class="event-progress">
                            <span>{{ event.progressLabel }}</span>
                        </div>
                    </article>
                </div>

                <div v-else class="empty-state">
                    Realtime controller events will appear here after dispatch or telemetry updates.
                </div>
            </section>

            <section class="panel-card">
                <div class="panel-header">
                    <div>
                        <p class="panel-kicker">Operational View</p>
                        <h2 class="panel-title">Control Path</h2>
                    </div>
                    <span class="panel-badge">System Trace</span>
                </div>

                <div class="flow-list">
                    <article class="flow-card">
                        <span class="flow-index">01</span>
                        <div>
                            <p class="flow-title">Operator Request</p>
                            <p class="flow-copy">Material or recipe selection enters the orchestration path from the control console.</p>
                        </div>
                    </article>
                    <article class="flow-card">
                        <span class="flow-index">02</span>
                        <div>
                            <p class="flow-title">Backend Resolution</p>
                            <p class="flow-copy">The Django service resolves recipe parameters and device-specific execution steps.</p>
                        </div>
                    </article>
                    <article class="flow-card">
                        <span class="flow-index">03</span>
                        <div>
                            <p class="flow-title">MQTT Dispatch</p>
                            <p class="flow-copy">Job start publishes step payloads to the embedded control channel when MQTT is available.</p>
                        </div>
                    </article>
                    <article class="flow-card">
                        <span class="flow-index">04</span>
                        <div>
                            <p class="flow-title">Feedback Loop</p>
                            <p class="flow-copy">WebSocket events and backend polling close the loop so operators can verify physical execution.</p>
                        </div>
                    </article>
                </div>

                <div v-if="createdJob" class="job-summary">
                    <p class="job-summary__title">Current Job Context</p>
                    <div class="job-summary__row">
                        <span>Job ID</span>
                        <span>{{ createdJob.id }}</span>
                    </div>
                    <div class="job-summary__row">
                        <span>Operator</span>
                        <span>{{ createdJob.operator || 'N/A' }}</span>
                    </div>
                    <div class="job-summary__row">
                        <span>Dispatch Count</span>
                        <span>{{ startResult ? startResult.dispatched_messages.length : 0 }}</span>
                    </div>
                </div>
            </section>
        </div>
    </section>
</template>

<script>
import axios from 'axios'

export default {
    name: 'RecipeDemoView',
    created() {
        this.loadInitialData()
        this.connectRealtimeFeed()
    },
    beforeUnmount() {
        this.stopStatusPolling()
        if (this.wsClient) {
            this.wsClient.close()
        }
    },
    data() {
        return {
            inputMode: 'material',
            materials: [],
            recipes: [],
            steps: [],
            selectedMaterialId: '',
            selectedRecipeId: '',
            operator: 'operator_demo',
            overrides: {
                reaction_temperature_c: '',
                stirring_speed_rpm: ''
            },
            previewParameters: {},
            createdJob: null,
            startResult: null,
            jobStatus: null,
            loadingPreview: false,
            creatingJob: false,
            startingJob: false,
            formMessage: '',
            errorMessage: '',
            statusPoller: null,
            wsClient: null,
            liveEvents: []
        }
    },
    computed: {
        selectedRecipe() {
            return this.recipes.find(recipe => recipe.id === Number(this.selectedRecipeId)) || null
        },
        selectedMaterialName() {
            if (!this.selectedRecipe) {
                return 'No material selected'
            }
            const material = this.materials.find(item => item.id === this.selectedRecipe.material_type)
            return material ? material.name : 'Matched material'
        },
        resolvedRecipeId() {
            return this.selectedRecipe ? this.selectedRecipe.id : ''
        },
        previewReady() {
            return Boolean(this.selectedRecipe && this.steps.length)
        },
        latestDeviceReply() {
            return this.liveEvents.find(event => event.topic === 'device_reply') || null
        }
    },
    methods: {
        recipeLabel(recipe) {
            const material = this.materials.find(item => item.id === recipe.material_type)
            const materialName = material ? material.name : `Material ${recipe.material_type}`
            return `${materialName} / v${recipe.version}`
        },
        sanitizeOverrides() {
            const result = {}
            if (this.overrides.reaction_temperature_c !== '') {
                result.reaction_temperature_c = Number(this.overrides.reaction_temperature_c)
            }
            if (this.overrides.stirring_speed_rpm !== '') {
                result.stirring_speed_rpm = Number(this.overrides.stirring_speed_rpm)
            }
            return result
        },
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
        interfaceBadgeClass(interfaceType) {
            return `interface-badge--${interfaceType || 'topic'}`
        },
        summariseExecutionReply(execution) {
            const reply = execution.telemetry?.last_device_reply
            if (!reply) {
                return execution.error_message || 'No device reply yet.'
            }
            if (reply.message_type === 'progress') {
                const percent = reply.progress?.percent
                const stage = reply.progress?.stage
                return percent != null ? `Progress ${percent}%${stage ? ` • ${stage}` : ''}` : (stage || 'Progress update received.')
            }
            if (reply.message_type === 'result') {
                return reply.result ? JSON.stringify(reply.result) : 'Execution completed successfully.'
            }
            if (reply.message_type === 'error') {
                return reply.error?.message || reply.message || execution.error_message || 'Execution failed.'
            }
            return reply.status || reply.message_type || 'Reply received.'
        },
        connectRealtimeFeed() {
            const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
            this.wsClient = new WebSocket(`${protocol}://127.0.0.1:8000/websocket/`)
            this.wsClient.onmessage = this.onRealtimeMessage
        },
        onRealtimeMessage(event) {
            const payload = JSON.parse(event.data)
            const summary = payload.topic === 'cmd'
                ? `Motor ${payload.motor} received command speed=${payload.speed}, time=${payload.time}`
                : payload.topic === 'task_create'
                    ? `Motor ${payload.motor} started task for ${payload.time}s at speed ${payload.speed}`
                    : payload.topic === 'task_done'
                        ? `Motor ${payload.motor} reported task completion`
                        : payload.topic === 'pcnt'
                            ? `Motor ${payload.motor} PCNT=${payload.pcnt}`
                            : payload.topic === 'pwm'
                                ? `Motor ${payload.motor} PWM=${payload.pwm}`
                                : payload.topic === 'device_reply'
                                    ? this.summariseDeviceReplyEvent(payload)
                                    : JSON.stringify(payload)

            this.liveEvents.unshift({
                key: `${Date.now()}-${Math.random()}`,
                topic: payload.topic || 'event',
                time: new Date().toLocaleTimeString(),
                summary,
                interfaceType: payload.interface_type || '',
                progressLabel: payload.payload?.progress?.percent != null
                    ? `${payload.payload.progress.percent}% · ${payload.payload.progress.stage || payload.status || 'running'}`
                    : ''
            })
            this.liveEvents = this.liveEvents.slice(0, 10)
        },
        summariseDeviceReplyEvent(payload) {
            const body = payload.payload || {}
            const routeName = payload.route_name || body.route_name || 'device route'
            const device = [payload.device_type, payload.device_id].filter(Boolean).join(':')
            if (payload.message_type === 'ack') {
                return `${routeName} accepted by ${device || 'device'}`
            }
            if (payload.message_type === 'progress') {
                const percent = body.progress?.percent
                const stage = body.progress?.stage
                return `${routeName} running${percent != null ? ` at ${percent}%` : ''}${stage ? ` • ${stage}` : ''}`
            }
            if (payload.message_type === 'result') {
                return `${routeName} completed on ${device || 'device'}`
            }
            if (payload.message_type === 'error') {
                return `${routeName} failed: ${body.error?.message || body.message || 'unknown error'}`
            }
            return `${routeName} reported ${payload.status || payload.message_type || 'update'}`
        },
        stopStatusPolling() {
            if (this.statusPoller) {
                clearInterval(this.statusPoller)
                this.statusPoller = null
            }
        },
        startStatusPolling() {
            this.stopStatusPolling()
            this.fetchJobStatus()
            this.statusPoller = setInterval(() => {
                this.fetchJobStatus()
            }, 3000)
        },
        async fetchJobStatus() {
            if (!this.createdJob) {
                return
            }
            try {
                const response = await axios.get(`/api/v1/jobs/${this.createdJob.id}/status/`)
                this.jobStatus = response.data
            } catch (error) {
                console.log(error)
            }
        },
        async loadInitialData() {
            try {
                const [materialsResponse, recipesResponse] = await Promise.all([
                    axios.get('/api/v1/materials/'),
                    axios.get('/api/v1/recipes/')
                ])
                this.materials = materialsResponse.data
                this.recipes = recipesResponse.data
            } catch (error) {
                this.errorMessage = 'Failed to load material or recipe data from the backend.'
                console.log(error)
            }
        },
        onMaterialChange() {
            const matchedRecipe = this.recipes.find(recipe => recipe.material_type === Number(this.selectedMaterialId))
            this.selectedRecipeId = matchedRecipe ? matchedRecipe.id : ''
            this.steps = []
            this.previewParameters = {}
            this.formMessage = matchedRecipe
                ? 'The selected material has been mapped to an active backend recipe.'
                : 'No recipe is currently registered for this material.'
        },
        onRecipeChange() {
            const recipe = this.selectedRecipe
            this.selectedMaterialId = recipe ? recipe.material_type : ''
            this.steps = []
            this.previewParameters = {}
            this.formMessage = recipe ? 'A specific recipe definition is now targeted for execution.' : ''
        },
        async previewPlan() {
            if (!this.resolvedRecipeId) {
                this.errorMessage = 'Select a material or recipe before resolving the execution plan.'
                return
            }

            this.loadingPreview = true
            this.errorMessage = ''
            this.formMessage = ''
            this.createdJob = null
            this.startResult = null
            this.jobStatus = null
            this.stopStatusPolling()
            const overrides = this.sanitizeOverrides()

            try {
                const [recipeResponse, stepsResponse] = await Promise.all([
                    axios.get(`/api/v1/recipes/${this.resolvedRecipeId}/`),
                    axios.get(`/api/v1/recipes/${this.resolvedRecipeId}/steps/`)
                ])

                const recipe = recipeResponse.data
                this.previewParameters = {
                    dmac_dosage_ml: recipe.dmac_dosage_ml,
                    water_dosage_ml: recipe.water_dosage_ml,
                    solvent_ph: recipe.solvent_ph,
                    reaction_temperature_c: recipe.reaction_temperature_c,
                    stirring_speed_rpm: recipe.stirring_speed_rpm,
                    stirring_duration_min: recipe.stirring_duration_min,
                    ...overrides
                }
                this.steps = stepsResponse.data
                this.formMessage = 'Execution plan resolved from backend recipe data and linked device steps.'
            } catch (error) {
                this.errorMessage = 'Unable to resolve the operation plan. Check whether the recipe and its steps exist.'
                console.log(error)
            } finally {
                this.loadingPreview = false
            }
        },
        async createDemoJob() {
            if (!this.resolvedRecipeId) {
                this.errorMessage = 'Resolve a valid recipe before creating a job.'
                return
            }

            this.creatingJob = true
            this.errorMessage = ''
            this.formMessage = ''
            this.startResult = null
            this.jobStatus = null
            this.stopStatusPolling()

            try {
                const response = await axios.post('/api/v1/jobs/', {
                    recipe_id: this.resolvedRecipeId,
                    operator: this.operator,
                    overrides: this.sanitizeOverrides()
                })
                this.createdJob = response.data
                this.formMessage = 'Execution job created. The orchestration layer is ready for live dispatch.'
            } catch (error) {
                this.errorMessage = 'Job creation failed. Make sure the recipe has at least one configured step.'
                console.log(error)
            } finally {
                this.creatingJob = false
            }
        },
        async startDemoJob() {
            if (!this.createdJob) {
                this.errorMessage = 'Create a job before dispatching commands to devices.'
                return
            }

            this.startingJob = true
            this.errorMessage = ''
            this.formMessage = ''

            try {
                const response = await axios.post(`/api/v1/jobs/${this.createdJob.id}/start/`, {})
                this.startResult = response.data
                this.formMessage = response.data.mqtt_available
                    ? 'Commands were published to MQTT. Monitor the event stream and execution board for live feedback.'
                    : 'The job started, but the MQTT client is unavailable on the backend. Device dispatch did not occur.'
                this.startStatusPolling()
            } catch (error) {
                this.errorMessage = 'Dispatch failed. Check backend logs, step parameters, and MQTT availability.'
                console.log(error)
            } finally {
                this.startingJob = false
            }
        }
    }
}
</script>

<style scoped>
.recipe-console {
    padding: 1.25rem;
    min-height: calc(100vh - 4rem);
    background:
        linear-gradient(180deg, #101925 0%, #152132 20%, #eef3f8 20%, #eef3f8 100%);
}

.console-header {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    align-items: stretch;
    margin-bottom: 1.4rem;
    padding: 1.25rem 1.4rem;
    border-radius: 20px;
    background: linear-gradient(180deg, rgba(9, 14, 22, 0.88) 0%, rgba(19, 29, 45, 0.9) 100%);
    border: 1px solid rgba(148, 163, 184, 0.15);
    box-shadow: 0 18px 40px rgba(5, 10, 18, 0.3);
}

.eyebrow {
    margin-bottom: 0.3rem;
    color: #8fb3d9;
    font-size: 0.8rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    font-weight: 700;
}

.console-title {
    margin-bottom: 0.5rem !important;
    color: #f8fafc;
}

.console-copy {
    max-width: 56rem;
    color: #adbacd;
    line-height: 1.6;
}

.console-header__status {
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

.console-grid {
    display: grid;
    grid-template-columns: minmax(0, 1.25fr) minmax(360px, 0.95fr);
    gap: 1.25rem;
    margin-bottom: 1.25rem;
}

.console-grid--bottom {
    align-items: start;
}

.panel-card {
    padding: 1.35rem;
    border-radius: 20px;
    background: rgba(255, 255, 255, 0.96);
    border: 1px solid rgba(13, 22, 38, 0.08);
    box-shadow: 0 14px 36px rgba(15, 23, 36, 0.08);
}

.panel-card--form {
    min-height: 100%;
}

.panel-header {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    align-items: flex-start;
    margin-bottom: 1rem;
}

.panel-kicker {
    color: #9c5f16;
    font-size: 0.74rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    margin-bottom: 0.25rem;
    font-weight: 700;
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

.form-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.9rem;
}

.mode-switch {
    display: flex;
    gap: 0.55rem;
}

.mode-switch__button {
    min-width: 112px;
}

.command-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
    margin-top: 1rem;
}

.console-message {
    margin-top: 1rem;
    padding: 0.85rem 1rem;
    border-radius: 14px;
    border: 1px solid transparent;
}

.console-message--info {
    background: #eef6ff;
    border-color: #d4e6ff;
    color: #285b97;
}

.console-message--error {
    background: #fff2f2;
    border-color: #f5d0d0;
    color: #a13b3b;
}

.parameter-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.85rem;
}

.parameter-card,
.status-box,
.event-card,
.flow-card {
    border-radius: 16px;
    border: 1px solid rgba(15, 23, 36, 0.08);
}

.parameter-card {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    padding: 0.9rem 1rem;
    background: #f9fbfe;
}

.parameter-card__label,
.status-box__label {
    color: #64748b;
    font-size: 0.74rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 700;
}

.parameter-card__value,
.status-box__value {
    color: #111827;
    font-weight: 700;
}

.queue-table,
.outbox-table {
    border-radius: 18px;
    overflow: hidden;
    border: 1px solid rgba(15, 23, 36, 0.08);
}

.queue-table__head,
.queue-row {
    display: grid;
    grid-template-columns: 0.9fr 0.7fr 0.7fr 1fr 1.5fr;
    gap: 0.75rem;
    align-items: start;
    padding: 0.95rem 1rem;
}

.outbox-table__head,
.outbox-row {
    display: grid;
    grid-template-columns: 0.9fr 0.7fr 0.5fr 1.4fr;
    gap: 0.75rem;
    align-items: start;
    padding: 0.95rem 1rem;
}

.queue-table__head,
.outbox-table__head {
    background: #ecf2f8;
    color: #5f6d81;
    font-size: 0.74rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 700;
}

.queue-row,
.outbox-row {
    background: #ffffff;
    border-top: 1px solid rgba(15, 23, 36, 0.06);
}

.queue-row:nth-child(even),
.outbox-row:nth-child(even) {
    background: #fafcfe;
}

.queue-cell,
.outbox-cell {
    color: #1f2937;
    font-size: 0.92rem;
}

.queue-cell pre,
.outbox-cell pre {
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

.queue-cell--mono,
.outbox-cell--mono {
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

.status-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0.85rem;
    margin-bottom: 1rem;
}

.status-box {
    padding: 0.9rem 1rem;
    background: #f6f9ff;
}

.event-stream,
.flow-list {
    display: grid;
    gap: 0.85rem;
}

.event-card {
    padding: 0.95rem 1rem;
    background: #f9fbfe;
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

.event-topic__meta {
    margin-left: 0.45rem;
    color: #64748b;
    font-size: 0.76rem;
    font-weight: 600;
    text-transform: uppercase;
}

.event-time {
    color: #64748b;
    font-size: 0.82rem;
}

.event-summary {
    color: #475569;
    line-height: 1.55;
}

.event-progress {
    margin-top: 0.5rem;
    color: #285b97;
    font-size: 0.82rem;
    font-weight: 700;
}

.reply-board {
    margin-top: 1rem;
    border-radius: 18px;
    overflow: hidden;
    border: 1px solid rgba(15, 23, 36, 0.08);
}

.reply-board__head,
.reply-row {
    display: grid;
    grid-template-columns: 1fr 0.7fr 0.6fr 1.6fr;
    gap: 0.75rem;
    align-items: start;
    padding: 0.9rem 1rem;
}

.reply-board__head {
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

.reply-meta {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 0.25rem;
    flex-wrap: wrap;
}

.reply-type,
.reply-status {
    font-size: 0.74rem;
    font-weight: 700;
    text-transform: uppercase;
    color: #5b6575;
}

.reply-copy {
    color: #475569;
    line-height: 1.5;
}

.flow-card {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 0.8rem;
    padding: 0.95rem 1rem;
    background: #f7fafc;
}

.flow-index {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    border-radius: 10px;
    background: #e5edf6;
    color: #274c7d;
    font-size: 0.82rem;
    font-weight: 700;
}

.flow-title {
    color: #111827;
    font-weight: 700;
    margin-bottom: 0.2rem;
}

.flow-copy {
    color: #475569;
    line-height: 1.55;
}

.job-summary {
    margin-top: 1rem;
    padding: 1rem;
    border-radius: 16px;
    background: #f4f7fb;
    border: 1px solid rgba(15, 23, 36, 0.08);
}

.job-summary__title {
    color: #111827;
    font-weight: 700;
    margin-bottom: 0.65rem;
}

.job-summary__row {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    color: #334155;
}

.job-summary__row + .job-summary__row {
    margin-top: 0.45rem;
}

.empty-state {
    padding: 1.6rem;
    border-radius: 18px;
    border: 1px dashed rgba(100, 116, 139, 0.28);
    color: #64748b;
    background: #fbfcfd;
}

@media screen and (max-width: 1180px) {
    .metric-row,
    .console-grid {
        grid-template-columns: 1fr;
    }
}

@media screen and (max-width: 960px) {
    .form-grid,
    .parameter-grid,
    .status-grid,
    .queue-table__head,
    .queue-row,
    .outbox-table__head,
    .outbox-row {
        grid-template-columns: 1fr;
    }
}

@media screen and (max-width: 768px) {
    .recipe-console {
        padding: 1rem;
    }

    .console-header {
        flex-direction: column;
    }

    .console-header__status,
    .command-actions,
    .mode-switch {
        flex-wrap: wrap;
    }
}
</style>
