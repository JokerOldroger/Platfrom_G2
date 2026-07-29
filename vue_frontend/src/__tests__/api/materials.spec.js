import { describe, it, expect, vi } from 'vitest'
import materialsApi from '@/services/api/materials'
import client from '@/services/api/client'

describe('api/materials', () => {
  it('getMaterials calls GET /api/v1/materials/', async () => {
    const spy = vi.spyOn(client, 'get').mockResolvedValue({ data: [] })
    await materialsApi.getMaterials()
    expect(spy).toHaveBeenCalledWith('/api/v1/materials/')
    spy.mockRestore()
  })

  it('getRecipes calls GET /api/v1/recipes/', async () => {
    const spy = vi.spyOn(client, 'get').mockResolvedValue({ data: [] })
    await materialsApi.getRecipes()
    expect(spy).toHaveBeenCalledWith('/api/v1/recipes/')
    spy.mockRestore()
  })

  it('getRecipe calls GET /api/v1/recipes/{id}/', async () => {
    const spy = vi.spyOn(client, 'get').mockResolvedValue({ data: {} })
    await materialsApi.getRecipe(5)
    expect(spy).toHaveBeenCalledWith('/api/v1/recipes/5/')
    spy.mockRestore()
  })

  it('getRecipeSteps calls GET /api/v1/recipes/{id}/steps/', async () => {
    const spy = vi.spyOn(client, 'get').mockResolvedValue({ data: [] })
    await materialsApi.getRecipeSteps(5)
    expect(spy).toHaveBeenCalledWith('/api/v1/recipes/5/steps/')
    spy.mockRestore()
  })

  it('upsertStirArmDemoRecipe calls POST /api/v1/recipes/stir-arm-demo/upsert/', async () => {
    const spy = vi.spyOn(client, 'post').mockResolvedValue({ data: {} })
    const payload = { material_name: 'StirArmDemo', recipe_name: 'Timed stir then home' }
    await materialsApi.upsertStirArmDemoRecipe(payload)
    expect(spy).toHaveBeenCalledWith('/api/v1/recipes/stir-arm-demo/upsert/', payload)
    spy.mockRestore()
  })
})
