<template>
    <section class="recipe-console">
        <ConsoleHeader
            eyebrow="Recipe Control Console"
            title="Material Execution Workspace"
            copy="Resolve a material request into backend recipe logic, inspect the generated execution plan, and dispatch live device commands from one operator surface."
            :status-items="[
                { label: 'MQTT', value: mqttStatusLabel },
                { label: 'Job', value: jobStatusLabel }
            ]"
        />

        <section class="metric-row">
            <MetricCard label="Selected Material" :value="selectedMaterialName" />
            <MetricCard label="Resolved Recipe" :value="selectedRecipe ? recipeLabel(selectedRecipe) : 'None'" />
            <MetricCard label="Dispatched Commands" :value="startResult ? startResult.dispatched_messages.length : 0" />
            <MetricCard label="Failed Steps" :value="jobStatus?.step_status_counts?.failed || 0" accent />
        </section>

        <div class="console-grid">
            <section class="panel-card panel-card--form">
                <PanelHeader kicker="Operator Input" title="Recipe Request" badge="Control Entry" />
                <RecipeRequestForm
                    v-model="formModel"
                    :materials="materials"
                    :recipes="recipes"
                    :resolved-recipe-id="resolvedRecipeId"
                    :preview-ready="previewReady"
                    :loading-preview="loadingPreview"
                    :creating-job="creatingJob"
                    :starting-job="startingJob"
                    :created-job="createdJob"
                    :form-message="formMessage"
                    :error-message="errorMessage"
                    @preview="previewPlan"
                    @create-job="createDemoJob"
                    @start-job="startDemoJob"
                    @material-change="onMaterialChange"
                    @recipe-change="onRecipeChange"
                />
            </section>

            <section class="panel-card">
                <PanelHeader kicker="Resolved Recipe" title="Process Parameters" badge="Backend Match" />
                <RecipeParameters
                    :selected-recipe="selectedRecipe"
                    :selected-material-name="selectedMaterialName"
                    :preview-parameters="previewParameters"
                />
            </section>
        </div>

        <div class="console-grid console-grid--bottom">
            <section class="panel-card">
                <PanelHeader
                    kicker="Execution Plan"
                    title="Device Step Queue"
                    :badge="steps.length + ' Step' + (steps.length === 1 ? '' : 's')"
                />
                <ExecutionPlanQueue :steps="steps" />
            </section>

            <section class="panel-card">
                <PanelHeader
                    kicker="Execution State"
                    title="Dispatch and Job Status"
                    :badge="createdJob ? `Job ${createdJob.id}` : 'No Job'"
                />
                <JobStatusBoard :job-status="jobStatus" />
            </section>
        </div>

        <div class="console-grid console-grid--bottom">
            <section class="panel-card">
                <PanelHeader kicker="Realtime Feed" title="Device Event Stream" badge="WebSocket" />
                <RecipeEventStream :events="liveEvents" />
            </section>

            <section class="panel-card">
                <PanelHeader kicker="Operational View" title="Control Path" badge="System Trace" />
                <ControlPath :created-job="createdJob" :start-result="startResult" />
            </section>
        </div>
    </section>
</template>

<script>
import materialsApi from '@/services/api/materials.js'
import jobsApi from '@/services/api/jobs.js'
import ConsoleHeader from '@/components/ui/ConsoleHeader.vue'
import MetricCard from '@/components/ui/MetricCard.vue'
import PanelHeader from '@/components/ui/PanelHeader.vue'
import RecipeRequestForm from '@/components/recipe/RecipeRequestForm.vue'
import RecipeParameters from '@/components/recipe/RecipeParameters.vue'
import ExecutionPlanQueue from '@/components/recipe/ExecutionPlanQueue.vue'
import JobStatusBoard from '@/components/recipe/JobStatusBoard.vue'
import RecipeEventStream from '@/components/recipe/RecipeEventStream.vue'
import ControlPath from '@/components/recipe/ControlPath.vue'

export default {
    name: 'RecipeDemoView',
    components: {
        ConsoleHeader,
        MetricCard,
        PanelHeader,
        RecipeRequestForm,
        RecipeParameters,
        ExecutionPlanQueue,
        JobStatusBoard,
        RecipeEventStream,
        ControlPath
    },
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
            demoDefaults: {
                materialName: 'StirArmDemo',
                recipeVersion: 1
            },
            formModel: {
                inputMode: 'material',
                selectedMaterialId: '',
                selectedRecipeId: '',
                operator: 'operator_demo',
                overrides: {
                    reaction_temperature_c: '',
                    stirring_speed_rpm: ''
                }
            },
            materials: [],
            recipes: [],
            steps: [],
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
            return this.recipes.find(recipe => recipe.id === Number(this.formModel.selectedRecipeId)) || null
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
        mqttStatusLabel() {
            if (!this.startResult) return 'Unknown'
            return this.startResult.mqtt_available ? 'Ready' : 'Offline'
        },
        jobStatusLabel() {
            return this.jobStatus?.job?.status || this.createdJob?.status || 'Not Started'
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
            if (this.formModel.overrides.reaction_temperature_c !== '') {
                result.reaction_temperature_c = Number(this.formModel.overrides.reaction_temperature_c)
            }
            if (this.formModel.overrides.stirring_speed_rpm !== '') {
                result.stirring_speed_rpm = Number(this.formModel.overrides.stirring_speed_rpm)
            }
            return result
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
                const response = await jobsApi.getJobStatus(this.createdJob.id)
                this.jobStatus = response.data
                const status = response.data?.job?.status
                if (['DONE', 'FAILED', 'ABORTED'].includes(status)) {
                    this.stopStatusPolling()
                }
            } catch (error) {
                console.log(error)
            }
        },
        async loadInitialData() {
            try {
                const [materialsResponse, recipesResponse] = await Promise.all([
                    materialsApi.getMaterials(),
                    materialsApi.getRecipes()
                ])
                this.materials = materialsResponse.data
                this.recipes = recipesResponse.data
                await this.selectSeededDemoRecipe()
            } catch (error) {
                this.errorMessage = 'Failed to load material or recipe data from the backend.'
                console.log(error)
            }
        },
        async selectSeededDemoRecipe() {
            if (this.formModel.selectedRecipeId || !this.recipes.length) {
                return
            }

            const material = this.materials.find(item => item.name === this.demoDefaults.materialName)
            const matchedRecipe = this.recipes.find(recipe => (
                recipe.material_type === material?.id
                && Number(recipe.version) === this.demoDefaults.recipeVersion
            ))

            if (!material || !matchedRecipe) {
                this.formMessage = 'Load or seed StirArmDemo v1 before running the motor-arm closed-loop demo.'
                return
            }

            this.formModel = {
                ...this.formModel,
                inputMode: 'recipe',
                selectedMaterialId: material.id,
                selectedRecipeId: matchedRecipe.id
            }
            this.formMessage = 'StirArmDemo v1 selected from backend seed data. Resolve the plan before creating a job.'
            await this.previewPlan()
        },
        onMaterialChange(materialId) {
            const matchedRecipe = this.recipes
                .filter(recipe => recipe.material_type === Number(materialId))
                .sort((left, right) => Number(right.version) - Number(left.version) || right.id - left.id)[0]
            this.formModel.selectedRecipeId = matchedRecipe ? matchedRecipe.id : ''
            this.steps = []
            this.previewParameters = {}
            this.formMessage = matchedRecipe
                ? 'The selected material has been mapped to an active backend recipe.'
                : 'No recipe is currently registered for this material.'
        },
        onRecipeChange(recipeId) {
            const recipe = this.recipes.find(item => item.id === Number(recipeId))
            this.formModel.selectedMaterialId = recipe ? recipe.material_type : ''
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
                    materialsApi.getRecipe(this.resolvedRecipeId),
                    materialsApi.getRecipeSteps(this.resolvedRecipeId)
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
                const response = await jobsApi.createJob({
                    recipe_id: this.resolvedRecipeId,
                    operator: this.formModel.operator,
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
                const response = await jobsApi.startJob(this.createdJob.id)
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
        linear-gradient(180deg, #101925 4%, #152132 15%, #eef3f8 30%, #eef3f8 100%);
}

.metric-row {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0.85rem;
    margin-bottom: 1.4rem;
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

@media screen and (max-width: 1180px) {
    .metric-row,
    .console-grid {
        grid-template-columns: 1fr;
    }
}

@media screen and (max-width: 768px) {
    .recipe-console {
        padding: 1rem;
    }
}
</style>
