import { useCallback, useEffect, useState } from 'react'
import { type CaptureStatusResponse, getCaptureMjpegUrl, getCaptureStatus, postCaptureConfig } from '../lib/api-client'

export function CapturePreviewSection() {
	const [capture, setCapture] = useState<CaptureStatusResponse | null>(null)
	const [error, setError] = useState<string | null>(null)
	const [busy, setBusy] = useState(false)
	const [regexDraft, setRegexDraft] = useState('^\\s*(异环|NTE)\\s*$')
	const [streamKey, setStreamKey] = useState(0)

	const refreshCapture = useCallback(async () => {
		try {
			const c = await getCaptureStatus()
			setCapture(c)
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

	const applyRegex = async () => {
		setBusy(true)
		try {
			await postCaptureConfig(regexDraft.trim())
			setStreamKey(k => k + 1)
			await refreshCapture()
			setError(null)
		} catch (e) {
			setError(e instanceof Error ? e.message : String(e))
		}
		setBusy(false)
	}

	const mjpegSrc = `${getCaptureMjpegUrl()}?k=${streamKey}`

	return (
		<section className='mb-8 rounded-2xl ring-slate-200/80'>
			<div className='flex flex-wrap items-end justify-between gap-4 border-b border-slate-100 pb-5'>
				<div>
					<h2 className='text-sm font-semibold text-slate-800'>游戏窗口预览</h2>
					<p className='mt-1 text-xs text-slate-500'>
						流地址 <code className='text-slate-600'>/api/capture/mjpeg</code>
						{import.meta.env.DEV ? '（开发模式直连 8848）' : ''}
					</p>
				</div>
				<button
					type='button'
					className='rounded-xl bg-white px-3 py-2 text-xs font-medium text-slate-700 ring-1 ring-slate-200 hover:bg-slate-50'
					onClick={() => setStreamKey(k => k + 1)}>
					重连画面
				</button>
			</div>

			<div className='mt-5 overflow-hidden rounded-xl bg-slate-100 ring-1 ring-slate-200/80'>
				<img key={streamKey} src={mjpegSrc} alt='game window' className='mx-auto max-h-[min(52vh,720px)] w-full object-contain' />
			</div>

			<div className='mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4'>
				<div className='rounded-xl bg-slate-50/90 p-3 ring-1 ring-slate-100'>
					<p className='text-xs font-medium tracking-wider text-slate-500 uppercase'>匹配</p>
					<p className='mt-1 font-mono text-xs text-slate-800'>{capture?.title_regex ?? '—'}</p>
				</div>
				<div className='rounded-xl bg-slate-50/90 p-3 ring-1 ring-slate-100'>
					<p className='text-xs font-medium tracking-wider text-slate-500 uppercase'>客户区</p>
					<p className='mt-1 font-mono text-sm text-slate-900'>{capture && capture.width > 0 ? `${capture.width} × ${capture.height}` : '—'}</p>
				</div>
				<div className='rounded-xl bg-slate-50/90 p-3 ring-1 ring-slate-100'>
					<p className='text-xs font-medium tracking-wider text-slate-500 uppercase'>HWND</p>
					<p className='mt-1 font-mono text-xs text-slate-700'>{capture?.hwnd != null ? String(capture.hwnd) : '—'}</p>
				</div>
				<div className='rounded-xl bg-slate-50/90 p-3 ring-1 ring-slate-100'>
					<p className='text-xs font-medium tracking-wider text-slate-500 uppercase'>状态</p>
					<p className='mt-1 text-sm text-slate-800'>{capture?.message ?? '—'}</p>
				</div>
			</div>

			<div className='mt-5 flex flex-col gap-3 sm:flex-row sm:items-end'>
				<label className='block min-w-0 flex-1'>
					<span className='text-xs font-medium text-slate-600'>标题正则（Python re 全匹配）</span>
					<input
						value={regexDraft}
						onChange={e => setRegexDraft(e.target.value)}
						className='mt-1.5 w-full rounded-xl border-0 bg-slate-50 px-3 py-2 font-mono text-sm text-slate-900 ring-1 ring-slate-200 focus:ring-2 focus:ring-sky-400'
						spellCheck={false}
					/>
				</label>
				<button
					type='button'
					disabled={busy}
					onClick={() => void applyRegex()}
					className='shrink-0 rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-45'>
					应用并重连
				</button>
			</div>

			{error && (
				<div role='alert' className='mt-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-900'>
					<p className='font-medium'>捕获 / 配置请求失败</p>
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
