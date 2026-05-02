import { Card, Divider, Icon } from 'animal-island-ui'
import { CapturePipelineDebugPanel } from './capture-pipeline-debug-panel'
import { formatLiveFpsLabel, parsePageMatch, useCaptureSession } from './capture-session-context'
import { MsgTerminalPanel } from './msg-terminal-panel'

export function CaptureRightPanel() {
	const { capture, error, preview, canvasRef, matchBoxCss } = useCaptureSession()
	const { liveFps, pageMatch, pipelineMs } = preview
	const summaryMatch = pageMatch ?? parsePageMatch(capture?.page_match ?? null)

	return (
		<div className='flex min-h-0 min-w-0 flex-1 flex-col gap-3 overflow-y-auto'>
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
				<div
					className='pointer-events-none absolute top-3 right-2 z-10 rounded-lg bg-[#fc736d]/95 p-2 px-2.5 py-1 text-xs leading-none font-medium tracking-tight text-white shadow-sm'
					aria-live='polite'>
					{summaryMatch?.page_label}
				</div>
				{matchBoxCss && <div className='pointer-events-none absolute z-9 rounded-sm ring-2 ring-[#fc736d]' style={matchBoxCss} aria-hidden />}
			</div>

			{error != null && error !== '' && (
				<Card color='app-red' className='p-3'>
					<p className='text-sm'>{error}</p>
				</Card>
			)}

			<div className='grid max-w-md grid-cols-2 gap-3'>
				<Card color='app-teal' className='p-3'>
					<p className='text-xs font-medium tracking-wider uppercase opacity-90'>页面识别</p>
					<p className='mt-1 font-mono text-xs opacity-90'>
						{summaryMatch && summaryMatch.w > 0 ? `${summaryMatch.x},${summaryMatch.y},${summaryMatch.w},${summaryMatch.h}` : '—'}
					</p>
					<p className='mt-1 font-mono text-xs opacity-90'>相似度：{summaryMatch?.similarity.toFixed(4)}</p>
				</Card>
				<Card color='app-blue' className='p-3'>
					<p className='text-xs font-medium tracking-wider uppercase opacity-90'>窗口尺寸</p>
					<p className='mt-1 font-mono text-sm font-medium'>{capture && capture.width > 0 ? `${capture.width} × ${capture.height}` : '—'}</p>
				</Card>
			</div>

			{/* <CapturePipelineDebugPanel pipelineMs={pipelineMs} /> */}

			<Divider type='line-brown' />

			<MsgTerminalPanel />
		</div>
	)
}
