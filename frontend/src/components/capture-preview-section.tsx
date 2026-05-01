import { useCallback, useEffect, useRef, useState } from 'react'
import { type CaptureStatusResponse, getCaptureWsUrl, getCaptureStatus, postCaptureFps } from '../lib/api-client'

const FPS_MIN = 1
const FPS_MAX = 60

const WS_LIVE_FPS_BYTES = 4

/** 绘制左上角由服务端统计的实测 FPS */
function drawLiveFpsBadge(ctx: CanvasRenderingContext2D, canvasW: number, liveFps: number) {
	const margin = Math.max(10, Math.round(canvasW * 0.018))
	const fontSize = Math.max(14, Math.round(canvasW * 0.034))
	const label =
		liveFps < 0.05 ? '— FPS' : `${liveFps >= 10 ? Math.round(liveFps) : liveFps.toFixed(1)} FPS`
	ctx.save()
	ctx.font = `600 ${fontSize}px ui-monospace, SFMono-Regular, monospace`
	const tw = ctx.measureText(label).width
	const bh = Math.round(fontSize * 1.45)
	const bw = tw + fontSize * 1.1
	const x = margin
	const y = margin
	ctx.fillStyle = 'rgba(15, 23, 42, 0.75)'
	if (typeof ctx.roundRect === 'function') {
		ctx.beginPath()
		ctx.roundRect(x, y, bw, bh, 8)
		ctx.fill()
	} else {
		ctx.fillRect(x, y, bw, bh)
	}
	ctx.fillStyle = '#f1f5f9'
	ctx.textBaseline = 'middle'
	ctx.textAlign = 'left'
	ctx.fillText(label, x + fontSize * 0.55, y + bh / 2)
	ctx.restore()
}

export function CapturePreviewSection() {
	const [capture, setCapture] = useState<CaptureStatusResponse | null>(null)
	const [error, setError] = useState<string | null>(null)
	const [streamKey, setStreamKey] = useState(0)
	const [fpsDraft, setFpsDraft] = useState(15)
	const [fpsSaving, setFpsSaving] = useState(false)
	const fpsSyncedOnce = useRef(false)
	const canvasRef = useRef<HTMLCanvasElement>(null)
	const previewMimeRef = useRef('image/jpeg')

	const refreshCapture = useCallback(async () => {
		try {
			const c = await getCaptureStatus()
			setCapture(c)
			previewMimeRef.current = c.preview_mime
			if (!fpsSyncedOnce.current) {
				setFpsDraft(Math.round(c.fps))
				fpsSyncedOnce.current = true
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
			if (buf.byteLength <= WS_LIVE_FPS_BYTES) return

			const view = new DataView(buf)
			const liveFps = view.getFloat32(0, false)
			const imageBuf = buf.slice(WS_LIVE_FPS_BYTES)

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

				drawLiveFpsBadge(ctx, canvas.width, liveFps)
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
		const n = Math.min(FPS_MAX, Math.max(FPS_MIN, Math.round(Number(fpsDraft)) || FPS_MIN))
		setFpsDraft(n)
		setFpsSaving(true)
		try {
			const { fps } = await postCaptureFps(n)
			setFpsDraft(Math.round(fps))
			setStreamKey(k => k + 1)
			setError(null)
			void refreshCapture()
		} catch (e) {
			setError(e instanceof Error ? e.message : String(e))
		} finally {
			setFpsSaving(false)
		}
	}, [fpsDraft, refreshCapture])

	return (
		<section className='mb-8 w-[400px]'>
			<canvas ref={canvasRef} className='block max-h-[480px] w-full rounded-md bg-slate-100 object-contain' />

			{error && <p className='mt-5 text-red-500'>{error}</p>}

			<div className='mt-5 flex flex-wrap items-end gap-4'>
				<div className='flex flex-col gap-1'>
					<label htmlFor='capture-fps' className='text-xs font-medium text-slate-500'>
						预览帧率（FPS）
					</label>
					<div className='flex items-center gap-2'>
						<input
							id='capture-fps'
							type='range'
							min={FPS_MIN}
							max={FPS_MAX}
							value={fpsDraft}
							onChange={e => setFpsDraft(Number(e.target.value))}
							className='w-40 accent-slate-700'
						/>
						<input
							type='number'
							min={FPS_MIN}
							max={FPS_MAX}
							value={fpsDraft}
							onChange={e => setFpsDraft(Number(e.target.value))}
							className='w-14 rounded-lg border border-slate-200 bg-white px-2 py-1 text-center text-xs text-slate-800 tabular-nums'
						/>
						<button
							type='button'
							disabled={fpsSaving}
							className='rounded-xl bg-white px-3 py-2 text-xs font-medium text-slate-700 ring-1 ring-slate-200 hover:bg-slate-50 disabled:opacity-50'
							onClick={() => void applyFps()}>
							{fpsSaving ? '保存中…' : '应用'}
						</button>
					</div>
				</div>
			</div>

			<div className='mt-5 grid grid-cols-2 gap-3'>
				<div className='rounded-xl bg-slate-50/90 p-3 ring-1 ring-slate-100'>
					<p className='text-xs font-medium tracking-wider text-slate-500 uppercase'>窗口尺寸</p>
					<p className='mt-1 font-mono text-sm text-slate-900'>{capture && capture.width > 0 ? `${capture.width} × ${capture.height}` : '—'}</p>
				</div>
				<div className='rounded-xl bg-slate-50/90 p-3 ring-1 ring-slate-100'>
					<p className='text-xs font-medium tracking-wider text-slate-500 uppercase'>窗口 ID</p>
					<p className='mt-1 font-mono text-xs text-slate-700'>{capture?.hwnd != null ? String(capture.hwnd) : '—'}</p>
				</div>
			</div>
		</section>
	)
}
