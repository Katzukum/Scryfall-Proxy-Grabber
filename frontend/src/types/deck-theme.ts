export interface ThemeCard {
  id: string
  name: string
  set_code: string
  collector_number: string
  face_name: string
  image: string
  oracle_text: string
  mana_cost: string
  type_line: string
  flavor_text: string
}

export interface ThemeJob {
  id: string
  kind: "download" | "enhance" | "edit"
  state: "running" | "complete" | "failed" | "cancelled"
  current: number
  total: number
  message: string
  error?: string
  result?: {
    prompt?: string
    image?: string
    output_path?: string
    output_folder?: string
    card_id?: string
    elapsed_seconds?: number
  }
}

export interface ThemeModelStatus {
  ready: boolean
  installed_bytes: number
  total_bytes: number
  missing_files: number | string[]
  label: string
}

export interface ThemeStatus {
  directory: string
  platform_supported: boolean
  message: string
  editor: ThemeModelStatus
  enhancer: ThemeModelStatus
  job: ThemeJob | null
}

export interface ThemeEditOptions {
  card_id: string
  theme: string
  prompt: string
  width: number
  height: number
  steps: number
  seed: number
  device: "auto" | "cpu"
}
