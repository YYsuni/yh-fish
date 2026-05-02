import { type CSSProperties, useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
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
import { CapturePipelineDebugPanel } from './capture-pipeline-debug-panel'

const FPS_MIN = 1
const FPS_MAX = 60
const MATCH_TH_MIN = 0
const MATCH_TH_MAX = 1
/** 二进制帧：`float32 BE` FPS + `uint32 BE` meta UTF-8 字节数 + JSON + 图像 */
const WS_PREVIEW_HEADER_BYTES = 8

function parsePageMatch(raw: unknown): PageMatchPayload {
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

function formatLiveFpsLabel(liveFps: number | null): string {
	if (liveFps == null || liveFps < 0.05) return '— FPS'
	return `${liveFps >= 10 ? Math.round(liveFps) : liveFps.toFixed(1)} FPS`
}

type DraftSaving = { draft: number; saving: boolean }

type PreviewOverlay = {
	liveFps: number | null
	pageMatch: PageMatchPayload
	/** 与 page_match 同帧的裁剪后逻辑尺寸（WS meta 或与轮询 capture 对齐） */
	cropDims: { w: number; h: number } | null
	pipelineMs: PipelineMsPayload | null
}

const initialPreviewOverlay: PreviewOverlay = {
	liveFps: null,
	pageMatch: null,
	cropDims: null,
	pipelineMs: null
}

export function CapturePreviewSection() {
	const [capture, setCapture] = useState<CaptureStatusResponse | null>(null)
	const [error, setError] = useState<string | null>(null)
	const [streamKey, setStreamKey] = useState(0)
	const [fps, setFps] = useState<DraftSaving>({ draft: 15, saving: false })
	const [matchTh, setMatchTh] = useState<DraftSaving>({ draft: 0.5, saving: false })
	const [preview, setPreview] = useState<PreviewOverlay>(initialPreviewOverlay)
	const [matchBoxCss, setMatchBoxCss] = useState<CSSProperties | null>(null)
	const [layoutTick, setLayoutTick] = useState(0)

	const { liveFps, pageMatch, cropDims, pipelineMs } = preview
	const fpsSyncedOnce = useRef(false)
	const matchThSyncedOnce = useRef(false)
	const canvasRef = useRef<HTMLCanvasElement>(null)
	const previewMimeRef = useRef('image/jpeg')

	const refreshCapture = useCallback(async () => {
		try {
			const c = await getCaptureStatus()
			setCapture(c)
			setPreview(p => ({
				...p,
				pageMatch: parsePageMatch(c.page_match ?? null),
				cropDims: c.width > 0 && c.height > 0 ? { w: c.width, h: c.height } : p.cropDims,
				pipelineMs: c.pipeline_ms != null ? normalizePipelineMs(c.pipeline_ms) : p.pipelineMs
			}))
			previewMimeRef.current = c.preview_mime
			if (!fpsSyncedOnce.current) {
				setFps(f => ({ ...f, draft: Math.round(c.fps) }))
				fpsSyncedOnce.current = true
			}
			if (!matchThSyncedOnce.current) {
				const th = Number(c.page_match_threshold)
				setMatchTh(m => ({ ...m, draft: Number.isFinite(th) ? th : 0.5 }))
				matchThSyncedOnce.current = true
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
		const clientW = el.clientWidth
		const clientH = el.clientHeight
		const bmpW = el.width
		const bmpH = el.height
		if (bmpW <= 0 || bmpH <= 0 || clientW <= 0 || clientH <= 0) {
			setMatchBoxCss(null)
			return
		}
		// page_match 为裁剪像素；画布位图为缩小预览，先映射到位图像素再按比例放入 object-contain
		const bx = (pageMatch.x * bmpW) / cropW
		const by = (pageMatch.y * bmpH) / cropH
		const bwR = (pageMatch.w * bmpW) / cropW
		const bhR = (pageMatch.h * bmpH) / cropH
		const uiScale = Math.min(clientW / bmpW, clientH / bmpH)
		const dw = bmpW * uiScale
		const dh = bmpH * uiScale
		const ox = (clientW - dw) / 2
		const oy = (clientH - dh) / 2
		setMatchBoxCss({
			left: ox + bx * uiScale,
			top: oy + by * uiScale,
			width: bwR * uiScale,
			height: bhR * uiScale
		})
	}, [pageMatch, layoutTick, cropDims, capture?.width, capture?.height])

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
			if (metaLen > 0) {
				try {
					const metaJson = new TextDecoder().decode(buf.slice(WS_PREVIEW_HEADER_BYTES, WS_PREVIEW_HEADER_BYTES + metaLen))
					const parsed = JSON.parse(metaJson) as {
						page_match?: unknown
						crop_width?: unknown
						crop_height?: unknown
						pipeline_ms?: unknown
					}
					pm = parsePageMatch(parsed.page_match ?? null)
					if (parsed.pipeline_ms != null) metaPipelineMs = normalizePipelineMs(parsed.pipeline_ms)
					const cw = Math.round(Number(parsed.crop_width))
					const ch = Math.round(Number(parsed.crop_height))
					if ([cw, ch].every(Number.isFinite) && cw > 0 && ch > 0) wsCrop = { w: cw, h: ch }
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
						...(metaPipelineMs !== undefined ? { pipelineMs: metaPipelineMs } : {})
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

	const summaryMatch = pageMatch ?? parsePageMatch(capture?.page_match ?? null)

	return (
		<section className='mb-8 w-[400px]'>
			<div className='relative w-full'>
				<canvas ref={canvasRef} className='block max-h-[480px] w-full rounded-md bg-slate-100 object-contain' />
				<div
					className='pointer-events-none absolute top-2 left-2 z-10 rounded-lg bg-slate-900/75 px-2.5 py-1 text-xs leading-none font-medium tracking-tight text-slate-100'
					aria-live='polite'>
					{formatLiveFpsLabel(liveFps)}
				</div>
				{matchBoxCss && <div className='pointer-events-none absolute z-9 rounded-xs ring-1 ring-red-600' style={matchBoxCss} aria-hidden />}
			</div>

			{error && <p className='mt-5 text-red-500'>{error}</p>}

			<div className='mt-5 flex flex-wrap items-end gap-4'>
				<div className='flex flex-col gap-1'>
					<label htmlFor='capture-fps' className='text-xs font-medium text-slate-500'>
						帧率（FPS）
					</label>
					<div className='flex items-center gap-2'>
						<input
							id='capture-fps'
							type='range'
							min={FPS_MIN}
							max={FPS_MAX}
							value={fps.draft}
							onChange={e => setFps(f => ({ ...f, draft: Number(e.target.value) }))}
							className='w-40 accent-slate-700'
						/>
						<input
							type='number'
							min={FPS_MIN}
							max={FPS_MAX}
							value={fps.draft}
							onChange={e => setFps(f => ({ ...f, draft: Number(e.target.value) }))}
							className='w-14 rounded-lg border border-slate-200 bg-white px-2 py-1 text-center text-xs text-slate-800 tabular-nums'
						/>
						<button
							type='button'
							disabled={fps.saving}
							className='rounded-xl bg-white px-3 py-2 text-xs font-medium text-slate-700 ring-1 ring-slate-200 hover:bg-slate-50 disabled:opacity-50'
							onClick={() => void applyFps()}>
							{fps.saving ? '保存中…' : '应用'}
						</button>
					</div>
				</div>
				<div className='flex flex-col gap-1'>
					<label htmlFor='capture-match-th' className='text-xs font-medium text-slate-500'>
						页面匹配阈值（0–1）
					</label>
					<div className='flex items-center gap-2'>
						<input
							id='capture-match-th'
							type='range'
							min={MATCH_TH_MIN}
							max={MATCH_TH_MAX}
							step={0.01}
							value={matchTh.draft}
							onChange={e => setMatchTh(m => ({ ...m, draft: Number(e.target.value) }))}
							className='w-40 accent-slate-700'
						/>
						<input
							type='number'
							min={MATCH_TH_MIN}
							max={MATCH_TH_MAX}
							step={0.01}
							value={matchTh.draft}
							onChange={e => setMatchTh(m => ({ ...m, draft: Number(e.target.value) }))}
							className='w-16 rounded-lg border border-slate-200 bg-white px-2 py-1 text-center text-xs text-slate-800 tabular-nums'
						/>
						<button
							type='button'
							disabled={matchTh.saving}
							className='rounded-xl bg-white px-3 py-2 text-xs font-medium text-slate-700 ring-1 ring-slate-200 hover:bg-slate-50 disabled:opacity-50'
							onClick={() => void applyMatchThreshold()}>
							{matchTh.saving ? '保存中…' : '应用'}
						</button>
					</div>
				</div>
			</div>

			<div className='mt-5 grid grid-cols-2 gap-3'>
				<div className='rounded-xl bg-slate-50/90 p-3 ring-1 ring-slate-100'>
					<p className='text-xs font-medium tracking-wider text-slate-500 uppercase'>页面识别</p>
					<p className='mt-1 text-sm text-slate-900'>{summaryMatch?.page_label || '—'}</p>
					<p className='mt-1 font-mono text-xs text-slate-600'>
						{summaryMatch && summaryMatch.w > 0 ? `x=${summaryMatch.x} y=${summaryMatch.y} w=${summaryMatch.w} h=${summaryMatch.h}` : '—'}
					</p>
					<p className='mt-1 font-mono text-xs text-slate-600'>相似度：{summaryMatch?.similarity.toFixed(4)}</p>
				</div>
				<div className='rounded-xl bg-slate-50/90 p-3 ring-1 ring-slate-100'>
					<p className='text-xs font-medium tracking-wider text-slate-500 uppercase'>窗口尺寸</p>
					<p className='mt-1 font-mono text-sm text-slate-900'>{capture && capture.width > 0 ? `${capture.width} × ${capture.height}` : '—'}</p>
				</div>
			</div>

			<CapturePipelineDebugPanel pipelineMs={pipelineMs} />
		</section>
	)
}
