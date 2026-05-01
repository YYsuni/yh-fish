export type RuntimeStatusResponse = {
	state: string
	message: string
	tick: number
}

export type HealthResponse = {
	ok: boolean
	version: string
}

export type CaptureStatusResponse = {
	ok: boolean
	title_regex: string
	hwnd: number | null
	width: number
	height: number
	fps: number
	message: string
}

/** 开发模式直连 8848，避免 Vite 代理缓冲 MJPEG 长连接 */
export function getCaptureMjpegUrl(): string {
	const base = import.meta.env.DEV ? 'http://127.0.0.1:8848' : ''
	return `${base}/api/capture/mjpeg`
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

export function getHealth() {
	return fetchJson<HealthResponse>('/api/health')
}

export function getRuntimeStatus() {
	return fetchJson<RuntimeStatusResponse>('/api/runtime/status')
}

export function postRuntimeStart() {
	return fetchJson<{ accepted: boolean; already_running: boolean }>('/api/runtime/start', { method: 'POST', body: '{}' })
}

export function postRuntimeStop() {
	return fetchJson<{ accepted: boolean }>('/api/runtime/stop', {
		method: 'POST',
		body: '{}'
	})
}

export function getCaptureStatus() {
	return fetchJson<CaptureStatusResponse>('/api/capture/status')
}

export function postCaptureConfig(titleRegex: string) {
	return fetchJson<{ title_regex: string }>('/api/capture/config', {
		method: 'POST',
		body: JSON.stringify({ title_regex: titleRegex })
	})
}
