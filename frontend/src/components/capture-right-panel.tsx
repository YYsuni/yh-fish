import { Card, Divider, Icon } from 'animal-island-ui'
import { formatLiveFpsLabel, parsePageMatch, useCaptureSession } from './capture-session-context'
import { MsgTerminalPanel } from './msg-terminal-panel'

export function CaptureRightPanel() {
	const { capture, error, preview, canvasRef, matchBoxCss, reelingBarOverlayBoxes } = useCaptureSession()
	const { liveFps, pageMatch, reelingBarDebug } = preview
	const summaryMatch = pageMatch ?? parsePageMatch(capture?.page_match ?? null)
	const pageId = summaryMatch?.page_id ?? ''
	const showReelingMeta = pageId === 'reeling' && reelingBarDebug != null

	return (
		<div className='flex min-h-0 min-w-0 flex-col gap-3 overflow-y-auto'>
			<div className='flex items-center gap-2'>
				<Icon name='icon-camera' size={26} bounce />
				<span className='font-medium'>窗口捕获预览</span>
			</div>

			<div className='relative w-full max-w-md'>
				<canvas ref={canvasRef} className='block max-h-[420px] w-full rounded-md bg-[#e8e4d4] object-contain' />
				<div
					className='pointer-events-none absolute top-2 left-2 z-10 rounded-lg bg-[#8ac68a]/95 px-2.5 py-1 text-xs leading-none font-medium tracking-tight text-white shadow-sm'
					aria-live='polite'>
					{formatLiveFpsLabel(liveFps)}
				</div>
				{summaryMatch?.page_label && (
					<div
						className='pointer-events-none absolute top-3 right-2 z-10 rounded-lg bg-[#fc736d]/95 p-2 px-2.5 py-1 text-xs leading-none font-medium tracking-tight text-white shadow-sm'
						aria-live='polite'>
						{summaryMatch?.page_label}
					</div>
				)}
				{matchBoxCss && <div className='pointer-events-none absolute z-9 rounded-sm ring-2 ring-[#fc736d]' style={matchBoxCss} aria-hidden />}
				{reelingBarOverlayBoxes?.map(b => (
					<div key={b.key} className={`pointer-events-none absolute z-11 rounded-sm ring-2 ring-[#fc736d]`} style={b.style} aria-hidden />
				))}
			</div>

			{error != null && error !== '' && (
				<Card color='app-red' className='p-3'>
					<p className='text-sm'>{error}</p>
				</Card>
			)}

			<div className='grid grid-cols-2 gap-3'>
				<Card color='app-teal' className='p-3'>
					<p className='text-xs font-medium tracking-wider uppercase opacity-90'>页面识别</p>
					<p className='mt-1 font-mono text-sm opacity-90'>相似度：{summaryMatch?.similarity.toFixed(4)}</p>
				</Card>
				<Card color='app-blue' className='p-3'>
					<p className='text-xs font-medium tracking-wider uppercase opacity-90'>窗口尺寸</p>
					<p className='mt-1 font-mono text-sm font-medium'>
						{capture && capture?.width === 1280 ? `${capture?.width} × ${capture?.height}` : capture?.width > 0 ? '必须为 1280x720' : '—'}
					</p>
				</Card>
			</div>

			{/* {showReelingMeta && reelingBarDebug != null && (
				<Card color='app-teal' className='max-w-md p-3'>
					<p className='text-xs font-medium tracking-wider uppercase opacity-90'>溜鱼子模板匹配</p>
					<p className='mt-1 font-mono text-xs opacity-90'>匹配时间：{reelingBarDebug.match_ms.toFixed(2)} ms</p>
					<p className='mt-1 font-mono text-xs opacity-90'>
						匹配率：
						{reelingBarDebug.items
							.map(it => `${it.label} ${it.similarity != null && Number.isFinite(it.similarity) ? it.similarity.toFixed(4) : '—'}`)
							.join(' · ')}
					</p>
				</Card>
			)} */}

			<Divider type='line-brown' />

			<MsgTerminalPanel />
		</div>
	)
}
