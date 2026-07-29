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
            <label class="label">Override Temperature (deg C)</label>
            <p class="help-text">Optional chemistry parameter. Device routing remains defined by the backend recipe.</p>
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
            <label class="label">Override Stirring Speed (rpm)</label>
            <p class="help-text">Leave blank to use the seeded value, for example StirArmDemo v1 uses 800 rpm.</p>
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
    </div>

    <div class="command-actions">
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
        createdJob: {
            type: Object,
            default: null
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
    emits: ['update:model-value', 'preview', 'create-job', 'start-job', 'material-change', 'recipe-change'],
    methods: {
        recipeLabel(recipe) {
            const material = this.materials.find(item => item.id === recipe.material_type)
            const materialName = material ? material.name : `Material ${recipe.material_type}`
            return `${materialName} / v${recipe.version}`
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

@media screen and (max-width: 960px) {
    .form-grid {
        grid-template-columns: 1fr;
    }

    .mode-switch {
        flex-wrap: wrap;
    }
}
</style>
