/** `pages.json` 中 `features[].debug=true` 时服务端每帧附带的 ROI / 模板 JPEG（Base64、无 data URL 前缀） */
export type TemplateDebugEntry = {
	page_id: string
	page_label: string
	template_file: string
	similarity: number
	region: readonly [number, number, number, number]
	roi_jpeg_base64: string
	template_jpeg_base64: string
}

export type PageMatchPayload = {
	page_id: string
	page_label: string
	/** OpenCV TM_CCOEFF_NORMED 峰值，约 [0,1]；解析时兼容历史字段 confidence */
	similarity: number
	/** 与 `/api/capture/status` 中 width×height 同坐标系（裁标题栏与边距后的客户区像素） */
	x: number
	y: number
	w: number
	h: number
	template_debug?: TemplateDebugEntry[]
} | null

export type CaptureStatusResponse = {
	ok: boolean
	hwnd: number | null
	width: number
	height: number
	fps: number
	preview_mime: string
	page_match: PageMatchPayload
	/** OpenCV 模板匹配判定下限 TM_CCOEFF_NORMED，约 [0,1] */
	page_match_threshold: number
}

/** 与当前页面同源；开发时代理由 Vite 转发 WS */
export function getCaptureWsUrl(): string {
	const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
	return `${proto}//${window.location.host}/api/capture/ws`
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
	const res = await fetch(path, {
		...init,
		headers: {
			'Content-Type': 'application/json',
			...(init?.headers ?? {})
		}
	})
	if (!res.ok) {
		const text = await res.text().catch(() => '')
		throw new Error(`${res.status} ${res.statusText}${text ? `: ${text}` : ''}`)
	}
	return (await res.json()) as T
}

export function getCaptureStatus() {
	return fetchJson<CaptureStatusResponse>('/api/capture/status')
}

export function postCaptureFps(fps: number) {
	return fetchJson<{ fps: number }>('/api/capture/fps', {
		method: 'POST',
		body: JSON.stringify({ fps })
	})
}

export function postCaptureMatchThreshold(threshold: number) {
	return fetchJson<{ page_match_threshold: number }>('/api/capture/match-threshold', {
		method: 'POST',
		body: JSON.stringify({ threshold })
	})
}
