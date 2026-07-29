import client from './client'

export default {
  getMaterials() {
    return client.get('/api/v1/materials/')
  },

  getRecipes() {
    return client.get('/api/v1/recipes/')
  },

  getRecipe(id) {
    return client.get(`/api/v1/recipes/${id}/`)
  },

  getRecipeSteps(id) {
    return client.get(`/api/v1/recipes/${id}/steps/`)
  },

  upsertStirArmDemoRecipe(payload) {
    return client.post('/api/v1/recipes/stir-arm-demo/upsert/', payload)
  }
}
