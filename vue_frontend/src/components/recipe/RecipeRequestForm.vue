<template>
    <div class="form-grid">
        <div class="field">
            <label class="label">Selection Mode</label>
            <div class="mode-switch">
                <button
                    class="button mode-switch__button"
                    :class="modelValue.inputMode === 'material' ? 'is-dark' : 'is-light'"
                    @click="updateField('inputMode', 'material')"
                >
                    Material
                </button>
                <button
                    class="button mode-switch__button"
                    :class="modelValue.inputMode === 'recipe' ? 'is-dark' : 'is-light'"
                    @click="updateField('inputMode', 'recipe')"
                >
                    Recipe
                </button>
            </div>
        </div>

        <div class="field" v-if="modelValue.inputMode === 'material'">
            <label class="label">Material Type</label>
            <div class="select is-fullwidth">
                <select :value="modelValue.selectedMaterialId" @change="onMaterialChange($event.target.value)">
                    <option disabled value="">Select a material</option>
                    <option v-for="material in materials" :key="material.id" :value="material.id">
                        {{ material.name }}
                    </option>
                </select>
            </div>
        </div>

        <div class="field" v-if="modelValue.inputMode === 'recipe'">
            <label class="label">Recipe</label>
            <div class="select is-fullwidth">
                <select :value="modelValue.selectedRecipeId" @change="onRecipeChange($event.target.value)">
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
                <input
                    class="input"
                    type="text"
                    :value="modelValue.operator"
                    @input="updateField('operator', $event.target.value)"
                    placeholder="operator_demo"
                >
            </div>
        </div>

        <div class="field">
            <label class="label">Material Name</label>
            <p class="help-text">Experiment-level material identity, for example StirArmDemo.</p>
            <div class="control">
                <input
                    class="input"
                    type="text"
                    :value="modelValue.materialName"
                    @input="updateField('materialName', $event.target.value)"
                    placeholder="StirArmDemo"
                >
            </div>
        </div>

        <div class="field">
            <label class="label">Recipe Name</label>
            <p class="help-text">Human-readable recipe mapping name for this workflow.</p>
            <div class="control">
                <input
                    class="input"
                    type="text"
                    :value="modelValue.recipeName"
                    @input="updateField('recipeName', $event.target.value)"
                    placeholder="Timed stir then home"
                >
            </div>
        </div>

        <div class="field">
            <label class="label">Recipe Version</label>
            <div class="control">
                <input
                    class="input"
                    type="number"
                    min="1"
                    :value="modelValue.recipeVersion"
                    @input="updateField('recipeVersion', $event.target.value)"
                    placeholder="1"
                >
            </div>
        </div>

        <div class="field">
            <label class="label">Reaction Temperature (deg C)</label>
            <p class="help-text">Stored as a recipe parameter; hardware routing still stays in backend steps.</p>
            <div class="control">
                <input
                    class="input"
                    type="number"
                    step="0.1"
                    :value="modelValue.overrides.reaction_temperature_c"
                    @input="updateOverride('reaction_temperature_c', $event.target.value)"
                    placeholder="90.0"
                >
            </div>
        </div>

        <div class="field">
            <label class="label">Stirring Speed (rpm)</label>
            <p class="help-text">Mapped to the seeded STIR step speed key.</p>
            <div class="control">
                <input
                    class="input"
                    type="number"
                    :value="modelValue.overrides.stirring_speed_rpm"
                    @input="updateOverride('stirring_speed_rpm', $event.target.value)"
                    placeholder="700"
                >
            </div>
        </div>

        <div class="field">
            <label class="label">Stirring Time (sec)</label>
            <p class="help-text">Mapped to ESP32 command duration, for example cmd_2_800_10.</p>
            <div class="control">
                <input
                    class="input"
                    type="number"
                    min="1"
                    :value="modelValue.durationSec"
                    @input="updateField('durationSec', $event.target.value)"
                    placeholder="10"
                >
            </div>
        </div>

        <div class="field">
            <label class="label">Arm Waypoint Trajectory</label>
            <p class="help-text">Teaching-stage path preset. The backend stores it in MOVE_ARM goal.trajectory.</p>
            <div class="select is-fullwidth">
                <select :value="modelValue.armPathPreset" @change="updateField('armPathPreset', $event.target.value)">
                    <option value="home">home</option>
                    <option value="reactor_hover">reactor_hover</option>
                    <option value="home,reactor_hover">home -> reactor_hover</option>
                    <option value="reactor_hover,home">reactor_hover -> home</option>
                </select>
            </div>
        </div>
    </div>

    <div class="command-actions">
        <button class="button is-warning is-light" @click="$emit('upsert-recipe')" :disabled="savingRecipe">
            {{ savingRecipe ? 'Saving…' : 'Save Recipe Mapping' }}
        </button>
        <button class="button is-dark" @click="$emit('preview')" :disabled="!resolvedRecipeId || loadingPreview">
            {{ loadingPreview ? 'Resolving…' : 'Resolve Plan' }}
        </button>
        <button class="button is-info is-light" @click="$emit('create-job')" :disabled="!previewReady || creatingJob">
            {{ creatingJob ? 'Creating…' : 'Create Job' }}
        </button>
        <button class="button is-success" @click="$emit('start-job')" :disabled="!createdJob || startingJob">
            {{ startingJob ? 'Dispatching…' : 'Dispatch to Devices' }}
        </button>
    </div>

    <div v-if="formMessage" class="console-message console-message--info">
        {{ formMessage }}
    </div>

    <pre v-if="equivalentCommand" class="seed-command">{{ equivalentCommand }}</pre>

    <div v-if="errorMessage" class="console-message console-message--error">
        {{ errorMessage }}
    </div>
</template>

<script>
export default {
    name: 'RecipeRequestForm',
    props: {
        modelValue: {
            type: Object,
            required: true
        },
        materials: {
            type: Array,
            default: () => []
        },
        recipes: {
            type: Array,
            default: () => []
        },
        resolvedRecipeId: {
            type: [String, Number],
            default: ''
        },
        previewReady: {
            type: Boolean,
            default: false
        },
        loadingPreview: {
            type: Boolean,
            default: false
        },
        creatingJob: {
            type: Boolean,
            default: false
        },
        startingJob: {
            type: Boolean,
            default: false
        },
        savingRecipe: {
            type: Boolean,
            default: false
        },
        createdJob: {
            type: Object,
            default: null
        },
        equivalentCommand: {
            type: String,
            default: ''
        },
        formMessage: {
            type: String,
            default: ''
        },
        errorMessage: {
            type: String,
            default: ''
        }
    },
    emits: ['update:model-value', 'preview', 'create-job', 'start-job', 'upsert-recipe', 'material-change', 'recipe-change'],
    methods: {
        recipeLabel(recipe) {
            const material = this.materials.find(item => item.id === recipe.material_type)
            const materialName = material ? material.name : `Material ${recipe.material_type}`
            return `${materialName} / ${recipe.name || 'Recipe'} / v${recipe.version}`
        },
        updateField(key, value) {
            this.$emit('update:model-value', { ...this.modelValue, [key]: value })
        },
        updateOverride(key, value) {
            this.$emit('update:model-value', {
                ...this.modelValue,
                overrides: { ...this.modelValue.overrides, [key]: value }
            })
        },
        onMaterialChange(value) {
            this.updateField('selectedMaterialId', Number(value))
            this.$emit('material-change', Number(value))
        },
        onRecipeChange(value) {
            this.updateField('selectedRecipeId', Number(value))
            this.$emit('recipe-change', Number(value))
        }
    }
}
</script>

<style scoped>
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

.help-text {
    margin: -0.2rem 0 0.45rem;
    color: #64748b;
    font-size: 0.78rem;
    line-height: 1.35;
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

.seed-command {
    margin-top: 1rem;
    padding: 0.85rem;
    border-radius: 14px;
    background: #111827;
    color: #e5e7eb;
    font-size: 0.78rem;
    white-space: pre-wrap;
    word-break: break-word;
}

@media screen and (max-width: 960px) {
    .form-grid {
        grid-template-columns: 1fr;
    }

    .mode-switch {
        flex-wrap: wrap;
    }
}
</style>
