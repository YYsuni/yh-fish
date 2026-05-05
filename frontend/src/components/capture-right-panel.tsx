import { formatLiveFpsLabel, parsePageMatch, useCaptureSession } from './capture-session-context'
import { MsgTerminalPanel } from './msg-terminal-panel'

export function CaptureRightPanel() {
	const { capture, error, preview, canvasRef, matchBoxCss, reelingBarOverlayBoxes, previewDebug } = useCaptureSession()
	const { liveFps, pageMatch, cropDims } = preview
	const summaryMatch = pageMatch ?? parsePageMatch(capture?.page_match ?? null)
	return (
		<div className='card col-span-3'>
			<h2 className='card-title'>实时预览</h2>

			<div className='card-content'>
				<div className='rounded-md bg-[#F1F1F3] p-3 shadow'>
					<div className='relative'>
						<canvas ref={canvasRef} className='block w-full rounded-md bg-[#e8e4d4] object-contain' />
						{previewDebug && (
							<>
								<div
									className='pointer-events-none absolute top-2 left-2 z-10 rounded border-2 border-white/10 bg-black/40 px-2.5 py-1 text-xs leading-none font-medium tracking-tight text-white shadow-sm backdrop-blur-sm'
									aria-live='polite'>
									{formatLiveFpsLabel(liveFps)}
								</div>
								{summaryMatch?.page_label && (
									<div
										className='pointer-events-none absolute top-2 right-2 z-10 rounded border-2 border-white/10 bg-black/40 px-2 py-1 text-xs leading-none font-medium tracking-tight text-white shadow-sm backdrop-blur-sm'
										aria-live='polite'>
										{summaryMatch?.page_label} ({summaryMatch?.similarity.toFixed(2)})
									</div>
								)}
								{cropDims && (
									<div
										className='pointer-events-none absolute bottom-1 left-2 z-10 text-[10px] leading-none font-medium tracking-tight text-white/40 shadow-sm backdrop-blur-sm'
										aria-live='polite'>
										{cropDims?.w}x{cropDims?.h}
									</div>
								)}
								{matchBoxCss && <div className='pointer-events-none absolute z-9 rounded-sm ring-2 ring-[#fc736d]' style={matchBoxCss} aria-hidden />}
								{reelingBarOverlayBoxes?.map(b => (
									<div key={b.key} className={`pointer-events-none absolute z-11 rounded-sm ring-2 ring-[#fc736d]`} style={b.style} aria-hidden />
								))}
							</>
						)}
					</div>
				</div>

				<MsgTerminalPanel />
			</div>
		</div>
	)
}
