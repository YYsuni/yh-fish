import { useEffect, useRef, useState } from 'react'
import type { PipelineMsPayload } from '../lib/api-client'
import { PIPELINE_KEYS, PIPELINE_LABELS } from '../lib/capture-pipeline-debug'

/** 预览帧可能高频上报；面板 UI 最多按此间隔刷新，减轻重渲染 */
const DISPLAY_THROTTLE_MS = 500

export type CapturePipelineDebugPanelProps = {
	pipelineMs: PipelineMsPayload | null
}

export function CapturePipelineDebugPanel({ pipelineMs }: CapturePipelineDebugPanelProps) {
	const [displayed, setDisplayed] = useState<PipelineMsPayload | null>(pipelineMs)
	const latestRef = useRef(pipelineMs)
	const lastFlushRef = useRef(0)
	const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

	latestRef.current = pipelineMs

	useEffect(() => {
		const now = Date.now()
		const flush = () => {
			lastFlushRef.current = Date.now()
			setDisplayed(latestRef.current)
			timeoutRef.current = null
		}

		if (now - lastFlushRef.current >= DISPLAY_THROTTLE_MS) {
			flush()
			return
		}

		if (timeoutRef.current == null) {
			const delay = Math.max(0, DISPLAY_THROTTLE_MS - (now - lastFlushRef.current))
			timeoutRef.current = setTimeout(flush, delay)
		}
	}, [pipelineMs])

	useEffect(() => {
		return () => {
			if (timeoutRef.current != null) {
				clearTimeout(timeoutRef.current)
				timeoutRef.current = null
			}
		}
	}, [])

	const barScaleMs = displayed != null ? Math.max(1, ...PIPELINE_KEYS.map(k => displayed[k] ?? 0)) : 1

	return (
		<div className='mt-4 p-3'>
			<p className='text-xs font-semibold tracking-wider text-[#725d42] uppercase'>捕获管线耗时（ms）</p>
			{displayed == null ? (
				<p className='mt-1 text-xs text-[#725d42]/80'>等待预览帧…</p>
			) : (
				<ul className='mt-2 space-y-1.5'>
					{PIPELINE_KEYS.map(key => {
						const ms = displayed[key] ?? 0
						const wPct = Math.min(100, (ms / barScaleMs) * 100)
						return (
							<li key={key} className='grid grid-cols-[7.5rem_3.5rem_1fr] items-center gap-2 text-xs text-[#725d42]'>
								<span>{PIPELINE_LABELS[key]}</span>
								<span className='text-right font-mono tabular-nums'>{ms.toFixed(1)}</span>
								<span className='h-1.5 min-w-0 overflow-hidden rounded-full bg-[#f7cd67]/60'>
									<span className='block h-full rounded-full bg-[#e59266]/90' style={{ width: `${wPct}%` }} />
								</span>
							</li>
						)
					})}
				</ul>
			)}
		</div>
	)
}
