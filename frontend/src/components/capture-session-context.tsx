import {
	type Dispatch,
	type ReactNode,
	type RefObject,
	type SetStateAction,
	createContext,
	useCallback,
	useContext,
	useEffect,
	useLayoutEffect,
	useMemo,
	useRef,
	useState
} from 'react'
import type { CSSProperties } from 'react'
import {
	type CaptureStatusResponse,
	type PageMatchPayload,
	type PipelineMsPayload,
	getCaptureWsUrl,
	getCaptureStatus,
	postCaptureFps,
	postCaptureMatchThreshold
} from '../lib/api-client'
import { normalizePipelineMs } from '../lib/capture-pipeline-debug'
import { parseMusicDrumDebug, type MusicDrumDebug } from '../lib/music-drum-debug'
import { cropRectToCanvasOverlayCss } from '../lib/preview-canvas-overlay'
import { parseReelingBarDebug, type ReelingBarDebug } from '../lib/reeling-bar-debug'

const FPS_MIN = 1
const FPS_MAX = 60
const MATCH_TH_MIN = 0
const MATCH_TH_MAX = 1
const WS_PREVIEW_HEADER_BYTES = 8

const REELING_OVERLAY_KEYS = ['left', 'right', 'scale'] as const

export function parsePageMatch(raw: unknown): PageMatchPayload {
	if (raw == null || typeof raw !== 'object') return null
	const o = raw as Record<string, unknown>
	const x = Math.round(Number(o.x))
	const y = Math.round(Number(o.y))
	const w = Math.max(0, Math.round(Number(o.w)))
	const h = Math.max(0, Math.round(Number(o.h)))
	if (![x, y, w, h].every(Number.isFinite)) return null
	const rawSim = o.similarity ?? o.confidence
	const similarity = Number(rawSim)
	return {
		page_id: String(o.page_id ?? ''),
		page_label: String(o.page_label ?? ''),
		similarity: Number.isFinite(similarity) ? similarity : 0,
		x,
		y,
		w,
		h
	}
}

export function formatLiveFpsLabel(liveFps: number | null): string {
	if (liveFps == null || liveFps < 0.05) return '— FPS'
	return `${liveFps >= 10 ? Math.round(liveFps) : liveFps.toFixed(1)} FPS`
}

type DraftSaving = { draft: number; saving: boolean }

type PreviewOverlay = {
	liveFps: number | null
	pageMatch: PageMatchPayload
	cropDims: { w: number; h: number } | null
	pipelineMs: PipelineMsPayload | null
	reelingBarDebug: ReelingBarDebug | null
	musicDrumDebug: MusicDrumDebug | null
}

const initialPreviewOverlay: PreviewOverlay = {
	liveFps: null,
	pageMatch: null,
	cropDims: null,
	pipelineMs: null,
	reelingBarDebug: null,
	musicDrumDebug: null
}

export type ReelingBarOverlayBox = {
	key: string
	style: CSSProperties
}

export type MusicDrumOverlayBox = {
	key: string
	style: CSSProperties
	label: string
	similarity: number | null
}

export type RefreshCaptureOptions = {
	/** 切换钓鱼/超强音后由后端重置阈值时，同步滑条并重连预览 WebSocket */
	syncMatchThreshold?: boolean
}

export type CaptureSessionContextValue = {
	capture: CaptureStatusResponse | null
	error: string | null
	preview: PreviewOverlay
	fps: DraftSaving
	setFps: Dispatch<SetStateAction<DraftSaving>>
	matchTh: DraftSaving
	setMatchTh: Dispatch<SetStateAction<DraftSaving>>
	canvasRef: RefObject<HTMLCanvasElement | null>
	matchBoxCss: CSSProperties | null
	reelingBarOverlayBoxes: ReelingBarOverlayBox[] | null
	musicDrumOverlayBoxes: MusicDrumOverlayBox[] | null
	applyCaptureSettings: () => Promise<void>
	refreshCapture: (options?: RefreshCaptureOptions) => Promise<void>
	previewDebug: boolean
	setPreviewDebug: Dispatch<SetStateAction<boolean>>
}

const CaptureSessionContext = createContext<CaptureSessionContextValue | null>(null)

export function useCaptureSession(): CaptureSessionContextValue {
	const v = useContext(CaptureSessionContext)
	if (v == null) throw new Error('useCaptureSession must be used within CaptureSessionProvider')
	return v
}

export function CaptureSessionProvider({ children }: { children: ReactNode }) {
	const [capture, setCapture] = useState<CaptureStatusResponse | null>(null)
	const [error, setError] = useState<string | null>(null)
	const [streamKey, setStreamKey] = useState(0)
	const [fps, setFps] = useState<DraftSaving>({ draft: 0, saving: false })
	const [matchTh, setMatchTh] = useState<DraftSaving>({ draft: 0, saving: false })
	const [preview, setPreview] = useState<PreviewOverlay>(initialPreviewOverlay)
	const [matchBoxCss, setMatchBoxCss] = useState<CSSProperties | null>(null)
	const [reelingBarOverlayBoxes, setReelingBarOverlayBoxes] = useState<ReelingBarOverlayBox[] | null>(null)
	const [musicDrumOverlayBoxes, setMusicDrumOverlayBoxes] = useState<MusicDrumOverlayBox[] | null>(null)
	const [layoutTick, setLayoutTick] = useState(0)
	const [previewDebug, setPreviewDebug] = useState(true)

	const { liveFps, pageMatch, cropDims, pipelineMs, reelingBarDebug, musicDrumDebug } = preview
	const fpsSyncedOnce = useRef(false)
	const matchThSyncedOnce = useRef(false)
	const canvasRef = useRef<HTMLCanvasElement>(null)
	const previewMimeRef = useRef('image/jpeg')

	const refreshCapture = useCallback(async (options?: RefreshCaptureOptions) => {
		try {
			const c = await getCaptureStatus()
			setCapture(c)
			setPreview(p => ({
				...p,
				pageMatch: parsePageMatch(c.page_match ?? null),
				cropDims: c.width > 0 && c.height > 0 ? { w: c.width, h: c.height } : p.cropDims,
				pipelineMs: c.pipeline_ms != null ? normalizePipelineMs(c.pipeline_ms) : p.pipelineMs,
				reelingBarDebug: parseReelingBarDebug(c.reeling_bar_debug ?? null),
				musicDrumDebug: parseMusicDrumDebug(c.music_drum_debug ?? null)
			}))
			previewMimeRef.current = c.preview_mime
			if (!fpsSyncedOnce.current) {
				setFps(f => ({ ...f, draft: Math.round(c.fps) }))
				fpsSyncedOnce.current = true
			}
			if (options?.syncMatchThreshold || !matchThSyncedOnce.current) {
				const th = Number(c.page_match_threshold)
				setMatchTh(m => ({ ...m, draft: Number.isFinite(th) ? th : 0.5 }))
				matchThSyncedOnce.current = true
			}
			if (options?.syncMatchThreshold) {
				setStreamKey(k => k + 1)
			}
			setError(null)
		} catch (e) {
			setError(e instanceof Error ? e.message : String(e))
		}
	}, [])

	useEffect(() => {
		void refreshCapture()
		const id = setInterval(() => void refreshCapture(), 800)
		return () => clearInterval(id)
	}, [refreshCapture])

	useEffect(() => {
		const canvas = canvasRef.current
		if (!canvas) return
		const ro = new ResizeObserver(() => setLayoutTick(t => t + 1))
		ro.observe(canvas)
		return () => ro.disconnect()
	}, [streamKey])

	useLayoutEffect(() => {
		const el = canvasRef.current
		if (!el || !pageMatch || pageMatch.w <= 0 || pageMatch.h <= 0) {
			setMatchBoxCss(null)
			return
		}
		const cropW = cropDims?.w ?? capture?.width ?? 0
		const cropH = cropDims?.h ?? capture?.height ?? 0
		if (cropW <= 0 || cropH <= 0) {
			setMatchBoxCss(null)
			return
		}
		const style = cropRectToCanvasOverlayCss(el, cropW, cropH, pageMatch.x, pageMatch.y, pageMatch.w, pageMatch.h)
		setMatchBoxCss(style ?? null)
	}, [pageMatch, layoutTick, cropDims, capture?.width, capture?.height])

	useLayoutEffect(() => {
		const el = canvasRef.current
		if (!el || pageMatch?.page_id !== 'reeling' || reelingBarDebug == null) {
			setReelingBarOverlayBoxes(null)
			return
		}
		const cropW = cropDims?.w ?? capture?.width ?? 0
		const cropH = cropDims?.h ?? capture?.height ?? 0
		if (cropW <= 0 || cropH <= 0) {
			setReelingBarOverlayBoxes(null)
			return
		}
		const boxes: ReelingBarOverlayBox[] = []
		for (const key of REELING_OVERLAY_KEYS) {
			const item = reelingBarDebug.items.find(i => i.key === key)
			if (item == null) continue
			const { x, y, w, h, similarity: sim } = item
			if (sim == null || !Number.isFinite(sim) || x == null || y == null || w == null || h == null || w <= 0 || h <= 0) continue
			const style = cropRectToCanvasOverlayCss(el, cropW, cropH, x, y, w, h)
			if (style == null) continue
			boxes.push({ key, style })
		}
		setReelingBarOverlayBoxes(boxes.length > 0 ? boxes : null)
	}, [pageMatch?.page_id, reelingBarDebug, layoutTick, cropDims, capture?.width, capture?.height])

	useLayoutEffect(() => {
		const el = canvasRef.current
		if (!el || capture?.capture_context !== 'music' || musicDrumDebug == null) {
			setMusicDrumOverlayBoxes(null)
			return
		}
		const cropW = cropDims?.w ?? capture?.width ?? 0
		const cropH = cropDims?.h ?? capture?.height ?? 0
		if (cropW <= 0 || cropH <= 0) {
			setMusicDrumOverlayBoxes(null)
			return
		}
		const boxes: MusicDrumOverlayBox[] = []
		for (const item of musicDrumDebug.items) {
			if (item.w <= 0 || item.h <= 0) continue
			const style = cropRectToCanvasOverlayCss(el, cropW, cropH, item.x, item.y, item.w, item.h)
			if (style == null) continue
			boxes.push({
				key: item.key,
				style,
				label: item.label,
				similarity: item.similarity
			})
		}
		setMusicDrumOverlayBoxes(boxes.length > 0 ? boxes : null)
	}, [capture?.capture_context, musicDrumDebug, layoutTick, cropDims, capture?.width, capture?.height])

	useEffect(() => {
		const canvas = canvasRef.current
		if (!canvas) return

		let cancelled = false
		const ws = new WebSocket(getCaptureWsUrl())
		ws.binaryType = 'arraybuffer'

		ws.onmessage = async ev => {
			if (typeof ev.data === 'string') {
				try {
					const o = JSON.parse(ev.data) as { mime?: string }
					if (o.mime) previewMimeRef.current = o.mime
				} catch {
					/* ignore */
				}
				return
			}
			const buf = ev.data as ArrayBuffer
			if (buf.byteLength <= WS_PREVIEW_HEADER_BYTES) return

			const view = new DataView(buf)
			const liveFps = view.getFloat32(0, false)
			const metaLen = view.getUint32(4, false)
			if (metaLen > 256 * 1024 || buf.byteLength < WS_PREVIEW_HEADER_BYTES + metaLen) return

			let pm: PageMatchPayload = null
			let wsCrop: { w: number; h: number } | null = null
			let metaPipelineMs: PipelineMsPayload | undefined
			let wsReeling: ReelingBarDebug | null | undefined
			let wsMusicDrum: MusicDrumDebug | null | undefined
			if (metaLen > 0) {
				try {
					const metaJson = new TextDecoder().decode(buf.slice(WS_PREVIEW_HEADER_BYTES, WS_PREVIEW_HEADER_BYTES + metaLen))
					const parsed = JSON.parse(metaJson) as {
						page_match?: unknown
						crop_width?: unknown
						crop_height?: unknown
						pipeline_ms?: unknown
						reeling_bar_debug?: unknown
						music_drum_debug?: unknown
					}
					pm = parsePageMatch(parsed.page_match ?? null)
					if (parsed.pipeline_ms != null) metaPipelineMs = normalizePipelineMs(parsed.pipeline_ms)
					const cw = Math.round(Number(parsed.crop_width))
					const ch = Math.round(Number(parsed.crop_height))
					if ([cw, ch].every(Number.isFinite) && cw > 0 && ch > 0) wsCrop = { w: cw, h: ch }
					if (parsed.reeling_bar_debug !== undefined) {
						wsReeling = parseReelingBarDebug(parsed.reeling_bar_debug)
					}
					if (parsed.music_drum_debug !== undefined) {
						wsMusicDrum = parseMusicDrumDebug(parsed.music_drum_debug)
					}
				} catch {
					/* ignore */
				}
			}

			const imageBuf = buf.slice(WS_PREVIEW_HEADER_BYTES + metaLen)
			const mime = previewMimeRef.current
			try {
				const blob = new Blob([imageBuf], { type: mime })
				const bmp = await createImageBitmap(blob)
				const ctx = canvas.getContext('2d')
				if (!ctx) {
					bmp.close()
					return
				}
				if (canvas.width !== bmp.width || canvas.height !== bmp.height) {
					canvas.width = bmp.width
					canvas.height = bmp.height
				}
				ctx.drawImage(bmp, 0, 0)
				bmp.close()

				if (!cancelled) {
					setPreview(prev => ({
						...prev,
						liveFps,
						pageMatch: pm,
						cropDims: wsCrop ?? prev.cropDims,
						...(metaPipelineMs !== undefined ? { pipelineMs: metaPipelineMs } : {}),
						...(wsReeling !== undefined ? { reelingBarDebug: wsReeling } : {}),
						...(wsMusicDrum !== undefined ? { musicDrumDebug: wsMusicDrum } : {})
					}))
				}
			} catch (e) {
				if (!cancelled) setError(e instanceof Error ? e.message : String(e))
			}
		}

		ws.onerror = () => {
			if (!cancelled) setError('预览连接异常')
		}
		ws.onclose = ev => {
			if (cancelled) return
			if (!ev.wasClean && ev.code !== 1000) setError(`预览已断开 (${ev.code})`)
		}

		return () => {
			cancelled = true
			ws.close()
		}
	}, [streamKey])

	const applyFps = useCallback(async () => {
		const n = Math.min(FPS_MAX, Math.max(FPS_MIN, Math.round(Number(fps.draft)) || FPS_MIN))
		setFps(f => ({ ...f, draft: n, saving: true }))
		try {
			const { fps: saved } = await postCaptureFps(n)
			setFps(f => ({ ...f, draft: Math.round(saved) }))
			setStreamKey(k => k + 1)
			setError(null)
			void refreshCapture()
		} catch (e) {
			setError(e instanceof Error ? e.message : String(e))
		} finally {
			setFps(f => ({ ...f, saving: false }))
		}
	}, [fps.draft, refreshCapture])

	const applyMatchThreshold = useCallback(async () => {
		const t = Math.min(MATCH_TH_MAX, Math.max(MATCH_TH_MIN, Number(matchTh.draft)))
		setMatchTh(m => ({ ...m, draft: t, saving: true }))
		try {
			const { page_match_threshold } = await postCaptureMatchThreshold(t)
			setMatchTh(m => ({ ...m, draft: page_match_threshold }))
			setStreamKey(k => k + 1)
			setError(null)
			void refreshCapture()
		} catch (e) {
			setError(e instanceof Error ? e.message : String(e))
		} finally {
			setMatchTh(m => ({ ...m, saving: false }))
		}
	}, [matchTh.draft, refreshCapture])

	const applyCaptureSettings = useCallback(async () => {
		await applyFps()
		await applyMatchThreshold()
	}, [applyFps, applyMatchThreshold])

	const value = useMemo<CaptureSessionContextValue>(
		() => ({
			capture,
			error,
			preview: { liveFps, pageMatch, cropDims, pipelineMs, reelingBarDebug, musicDrumDebug },
			fps,
			setFps,
			matchTh,
			setMatchTh,
			canvasRef,
			matchBoxCss,
			reelingBarOverlayBoxes,
			musicDrumOverlayBoxes,
			applyCaptureSettings,
			refreshCapture,
			previewDebug,
			setPreviewDebug
		}),
		[
			capture,
			error,
			liveFps,
			pageMatch,
			cropDims,
			pipelineMs,
			reelingBarDebug,
			musicDrumDebug,
			fps,
			matchTh,
			matchBoxCss,
			reelingBarOverlayBoxes,
			musicDrumOverlayBoxes,
			applyCaptureSettings,
			refreshCapture,
			previewDebug
		]
	)

	return <CaptureSessionContext.Provider value={value}>{children}</CaptureSessionContext.Provider>
}

export { FPS_MIN, FPS_MAX, MATCH_TH_MIN, MATCH_TH_MAX }
