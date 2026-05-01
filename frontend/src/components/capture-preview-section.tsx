import { useCallback, useEffect, useRef, useState } from 'react'
import { type CaptureStatusResponse, getCaptureMjpegUrl, getCaptureStatus, postCaptureFps } from '../lib/api-client'

const FPS_MIN = 1
const FPS_MAX = 60

export function CapturePreviewSection() {
	const [capture, setCapture] = useState<CaptureStatusResponse | null>(null)
	const [error, setError] = useState<string | null>(null)
	const [streamKey, setStreamKey] = useState(0)
	const [fpsDraft, setFpsDraft] = useState(30)
	const [fpsSaving, setFpsSaving] = useState(false)
	const fpsSyncedOnce = useRef(false)

	const refreshCapture = useCallback(async () => {
		try {
			const c = await getCaptureStatus()
			setCapture(c)
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

	const mjpegSrc = `${getCaptureMjpegUrl()}?k=${streamKey}`

	return (
		<section className='mb-8 rounded-2xl ring-slate-200/80'>
			<div className='flex flex-wrap items-end justify-between gap-4 border-b border-slate-100 pb-5'>
				<div>
					<h2 className='text-sm font-semibold text-slate-800'>游戏窗口预览</h2>
					<p className='mt-1 text-xs text-slate-500'>
						<code className='text-slate-600'>/api/capture/mjpeg</code>
						{import.meta.env.DEV ? ' · 开发直连 8848' : ''}
					</p>
				</div>
				<button
					type='button'
					className='rounded-xl bg-white px-3 py-2 text-xs font-medium text-slate-700 ring-1 ring-slate-200 hover:bg-slate-50'
					onClick={() => setStreamKey(k => k + 1)}>
					重连画面
				</button>
			</div>

			<div className='mt-5 overflow-hidden bg-slate-100 ring-1 ring-slate-200/80'>
				<img key={streamKey} src={mjpegSrc} alt='game window' className='mx-auto w-full object-contain' />
			</div>

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

			<div className='mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4'>
				<div className='rounded-xl bg-slate-50/90 p-3 ring-1 ring-slate-100'>
					<p className='text-xs font-medium tracking-wider text-slate-500 uppercase'>客户区</p>
					<p className='mt-1 font-mono text-sm text-slate-900'>{capture && capture.width > 0 ? `${capture.width} × ${capture.height}` : '—'}</p>
				</div>
				<div className='rounded-xl bg-slate-50/90 p-3 ring-1 ring-slate-100'>
					<p className='text-xs font-medium tracking-wider text-slate-500 uppercase'>HWND</p>
					<p className='mt-1 font-mono text-xs text-slate-700'>{capture?.hwnd != null ? String(capture.hwnd) : '—'}</p>
				</div>
				<div className='rounded-xl bg-slate-50/90 p-3 ring-1 ring-slate-100 sm:col-span-2'>
					<p className='text-xs font-medium tracking-wider text-slate-500 uppercase'>状态</p>
					<p className='mt-1 text-xs text-slate-700'>{capture?.message ?? '—'}</p>
				</div>
			</div>

			{error && (
				<div role='alert' className='mt-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-900'>
					<p className='font-medium'>请求失败</p>
					<p className='mt-1 break-all opacity-90'>{error}</p>
					<p className='mt-3 text-xs text-red-800/75'>
						开发：在项目根运行 <code className='rounded bg-red-100/80 px-1'>pnpm dev</code>，另开{' '}
						<code className='rounded bg-red-100/80 px-1'>python python/main.py --dev</code>
					</p>
				</div>
			)}
		</section>
	)
}
