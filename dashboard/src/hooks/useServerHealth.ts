import { useWorkers } from './useWorkers'

/** Server health snapshot surfaced via the AI worker's health payload. */
export interface ServerHealthSnapshot {
  status: string
  model: string
  llm_backend: string
  llm_engine_loaded: boolean
  model_available: boolean
  resource_profile: string
  performance_mode: boolean
  orpheus_enabled: boolean
  gpu_budget: {
    qwen_backend: string
    qwen_utilization: number | null
    orpheus_utilization: number
    combined_utilization: number
    cap: number
  }
  plan_admission: {
    max_inflight: number
    inflight: number
    admitted: number
    rejected: number
  }
  converse_sessions: {
    active_sessions: number
    registered: number
    preempted: number
    unregistered: number
    robots: string[]
  }
  llm: {
    backend: string
    model: string
    loaded: boolean
    max_inflight: number
    active_generations: number
    gpu_memory_utilization: number
    max_model_len: number
    max_num_seqs: number
    max_num_batched_tokens: number
    guided_decoding: boolean
    chat_template: boolean
    model_family: string
    template_config: {
      family: string
      chat_template_kwargs: Record<string, unknown>
      notes: string
    } | null
    generation_defaults: {
      temperature: number
      max_output_tokens: number
      timeout_s: number
      enable_thinking: boolean
    }
    engine_metrics: Record<string, number>
  }
}

export interface AIWorkerHealth {
  connected: boolean
  state: string
  session_id: string
  server_health: ServerHealthSnapshot | null
  generation_overrides: Record<string, number>
}

/**
 * Extracts server health from the AI worker's health payload.
 * Piggybacks on the existing useWorkers() poll (2s interval).
 */
export function useServerHealth() {
  const { data: workers, isLoading } = useWorkers()
  const aiHealth = workers?.ai?.health as AIWorkerHealth | undefined
  return {
    serverHealth: (aiHealth?.server_health ?? null) as ServerHealthSnapshot | null,
    generationOverrides: aiHealth?.generation_overrides ?? {},
    aiConnected: aiHealth?.connected ?? false,
    isLoading,
  }
}
