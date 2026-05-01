export type CaptureStatusResponse = {
	ok: boolean
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

export function getCaptureStatus() {
	return fetchJson<CaptureStatusResponse>('/api/capture/status')
}

export function postCaptureFps(fps: number) {
	return fetchJson<{ fps: number }>('/api/capture/fps', {
		method: 'POST',
		body: JSON.stringify({ fps })
	})
}
