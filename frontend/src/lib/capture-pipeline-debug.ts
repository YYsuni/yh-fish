import type { PipelineMsPayload } from './api-client'

/** 与后端 `capture_pipeline_debug.PIPELINE_TIMING_KEYS` 顺序一致 */
export const PIPELINE_KEYS = ['find_hwnd_ms', 'decode_ms', 'template_match_ms', 'scale_encode_ms'] as const

export type PipelineTimingKey = (typeof PIPELINE_KEYS)[number]

export const PIPELINE_LABELS: Record<PipelineTimingKey, string> = {
	find_hwnd_ms: '查找窗口',
	decode_ms: '解码（标题栏 + JPEG + 裁剪）',
	template_match_ms: '模板匹配',
	scale_encode_ms: '缩小 + JPEG 编码'
}

export function normalizePipelineMs(raw: unknown): PipelineMsPayload {
	const o = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {}
	const out: PipelineMsPayload = {}
	for (const k of PIPELINE_KEYS) {
		const n = Number(o[k])
		out[k] = Number.isFinite(n) ? n : 0
	}
	return out
}

export function dominantPipelineKey(pipe: PipelineMsPayload): PipelineTimingKey | null {
	let best: PipelineTimingKey | null = null
	let bestV = 0
	for (const k of PIPELINE_KEYS) {
		const v = pipe[k] ?? 0
		if (v > bestV) {
			bestV = v
			best = k
		}
	}
	return bestV >= 0.05 ? best : null
}
