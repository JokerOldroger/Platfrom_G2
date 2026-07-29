<template>
    <div v-if="selectedRecipe" class="parameter-grid">
        <article class="parameter-card">
            <span class="parameter-card__label">Material</span>
            <span class="parameter-card__value">{{ selectedMaterialName }}</span>
        </article>
        <article class="parameter-card">
            <span class="parameter-card__label">Recipe</span>
            <span class="parameter-card__value">{{ recipeLabel }}</span>
        </article>
        <article class="parameter-card">
            <span class="parameter-card__label">Recipe Name</span>
            <span class="parameter-card__value">{{ selectedRecipe.name || 'N/A' }}</span>
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
</template>

<script>
export default {
    name: 'RecipeParameters',
    props: {
        selectedRecipe: {
            type: Object,
            default: null
        },
        selectedMaterialName: {
            type: String,
            default: 'No material selected'
        },
        previewParameters: {
            type: Object,
            default: () => ({})
        }
    },
    computed: {
        recipeLabel() {
            if (!this.selectedRecipe) return 'None'
            return `${this.selectedMaterialName} / v${this.selectedRecipe.version}`
        }
    }
}
</script>

<style scoped>
.parameter-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.85rem;
}

.parameter-card {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    padding: 0.9rem 1rem;
    border-radius: 16px;
    background: #f9fbfe;
    border: 1px solid rgba(15, 23, 36, 0.08);
}

.parameter-card__label {
    color: #64748b;
    font-size: 0.74rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 700;
}

.parameter-card__value {
    color: #111827;
    font-weight: 700;
}

.empty-state {
    padding: 1.6rem;
    border-radius: 18px;
    border: 1px dashed rgba(100, 116, 139, 0.28);
    color: #64748b;
    background: #fbfcfd;
}

@media screen and (max-width: 960px) {
    .parameter-grid {
        grid-template-columns: 1fr;
    }
}
</style>
