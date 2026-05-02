import type { PipelineMsPayload } from '../lib/api-client'
import { PIPELINE_KEYS, PIPELINE_LABELS } from '../lib/capture-pipeline-debug'

export type CapturePipelineDebugPanelProps = {
	pipelineMs: PipelineMsPayload | null
}

export function CapturePipelineDebugPanel({ pipelineMs }: CapturePipelineDebugPanelProps) {
	const barScaleMs = pipelineMs != null ? Math.max(1, ...PIPELINE_KEYS.map(k => pipelineMs[k] ?? 0)) : 1

	return (
		<div className='mt-5 rounded-xl bg-amber-50/90 p-3 ring-1 ring-amber-100'>
			<p className='text-xs font-semibold tracking-wider text-amber-900 uppercase'>捕获管线耗时（ms）</p>
			{pipelineMs == null ? (
				<p className='mt-1 text-xs text-amber-900/70'>等待预览帧…</p>
			) : (
				<ul className='mt-2 space-y-1.5'>
					{PIPELINE_KEYS.map(key => {
						const ms = pipelineMs[key] ?? 0
						const wPct = Math.min(100, (ms / barScaleMs) * 100)
						return (
							<li key={key} className='grid grid-cols-[7.5rem_3.5rem_1fr] items-center gap-2 text-xs'>
								<span className='text-amber-900/85'>{PIPELINE_LABELS[key]}</span>
								<span className='text-right font-mono text-amber-950 tabular-nums'>{ms.toFixed(1)}</span>
								<span className='h-1.5 min-w-0 overflow-hidden rounded-full bg-amber-200/80'>
									<span className='block h-full rounded-full bg-amber-500/90' style={{ width: `${wPct}%` }} />
								</span>
							</li>
						)
					})}
				</ul>
			)}
		</div>
	)
}
