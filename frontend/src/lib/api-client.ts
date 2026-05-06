export type PageMatchPayload = {
	page_id: string
	page_label: string
	similarity: number
	x: number
	y: number
	w: number
	h: number
} | null

/** 与后端 `capture_pipeline_debug.PIPELINE_TIMING_KEYS` 对齐的毫秒耗时（缺省键按 0） */
export type PipelineMsPayload = Record<string, number>

export type CaptureContextId = 'fish' | 'music' | 'manager'

export type CaptureStatusResponse = {
	ok: boolean
	hwnd: number | null
	width: number
	height: number
	fps: number
	preview_mime: string
	/** 后端页面模板数据源：钓鱼 pages.json / 超强音 music/page.json */
	capture_context: CaptureContextId
	page_match: PageMatchPayload
	page_match_threshold: number
	pipeline_ms?: PipelineMsPayload
	/** 正在溜鱼页时由后端填充：子模板匹配耗时与各项相似度/矩形 */
	reeling_bar_debug?: unknown
	/** 超强音模式：四槽鼓点 ROI 匹配框与相似度 */
	music_drum_debug?: unknown
}

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

export function postCaptureContext(context: CaptureContextId) {
	return fetchJson<{ capture_context: CaptureContextId; page_match_threshold: number }>('/api/capture/context', {
		method: 'POST',
		body: JSON.stringify({ context })
	})
}

export type AutoFishLogicState = 'fishing' | 'sell-fish' | 'bait'

export type AutoFishStatusResponse = {
	running: boolean
	last_page_id: string | null
	logic_state: AutoFishLogicState
	/** 无鱼饵时是否走卖鱼；false 时直接切鱼饵逻辑 */
	sell_fish_on_no_bait: boolean
	/** 钓鱼结束页（fishing-end）累计触发次数 */
	fish_lost_total: number
}

export function getAutoFishStatus() {
	return fetchJson<AutoFishStatusResponse>('/api/auto-fish/status')
}

export function postAutoFishStart() {
	return fetchJson<{ running: boolean; started: boolean }>('/api/auto-fish/start', {
		method: 'POST',
		body: JSON.stringify({})
	})
}

export function postAutoFishStop() {
	return fetchJson<{ running: boolean }>('/api/auto-fish/stop', {
		method: 'POST',
		body: JSON.stringify({})
	})
}

export function postAutoFishLogicState(logic_state: AutoFishLogicState) {
	return fetchJson<AutoFishStatusResponse>('/api/auto-fish/logic', {
		method: 'POST',
		body: JSON.stringify({ logic_state })
	})
}

export function postAutoFishSellOnNoBait(enabled: boolean) {
	return fetchJson<AutoFishStatusResponse>('/api/auto-fish/sell-on-no-bait', {
		method: 'POST',
		body: JSON.stringify({ enabled })
	})
}

export type MusicStatusResponse = {
	running: boolean
	last_page_id: string | null
}

export function getMusicStatus() {
	return fetchJson<MusicStatusResponse>('/api/music/status')
}

export function postMusicStart() {
	return fetchJson<{ running: boolean; started: boolean }>('/api/music/start', {
		method: 'POST',
		body: JSON.stringify({})
	})
}

export function postMusicStop() {
	return fetchJson<{ running: boolean }>('/api/music/stop', {
		method: 'POST',
		body: JSON.stringify({})
	})
}

export type ManagerStatusResponse = {
	running: boolean
	last_page_id: string | null
	/** 执行器运行中且处于店长特供页时节流更新的多实例匹配调试（与捕获管线无关） */
	match_debug?: unknown
}

export function getManagerStatus() {
	return fetchJson<ManagerStatusResponse>('/api/manager/status')
}

export function postManagerStart() {
	return fetchJson<{ running: boolean; started: boolean }>('/api/manager/start', {
		method: 'POST',
		body: JSON.stringify({})
	})
}

export function postManagerStop() {
	return fetchJson<{ running: boolean }>('/api/manager/stop', {
		method: 'POST',
		body: JSON.stringify({})
	})
}

export type HotkeyPayload = {
	key: string | null
	ctrl: boolean
	shift: boolean
	alt: boolean
	meta: boolean
}

export type AppSettingsPayload = {
	start: HotkeyPayload
	stop: HotkeyPayload
	/** 物理点击整窗坐标换算为客户区后额外加上的 X（像素）；向左用负数，默认 0 */
	click_offset_x: number
	/** 物理点击整窗坐标换算为客户区后额外加上的 Y（像素）；向上用负数，默认 0 */
	click_offset_y: number
}

export function getAppSettings() {
	return fetchJson<AppSettingsPayload>('/api/settings')
}

export function postAppSettings(body: AppSettingsPayload) {
	return fetchJson<AppSettingsPayload>('/api/settings', {
		method: 'POST',
		body: JSON.stringify(body)
	})
}

export type MsgLogLine = { t: number; m: string }

export type MsgLogResponse = { lines: MsgLogLine[] }

export function getMsgLog() {
	return fetchJson<MsgLogResponse>('/api/msg/log')
}
