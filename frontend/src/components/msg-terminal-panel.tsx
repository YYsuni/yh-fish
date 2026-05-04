import { useEffect, useRef, useState } from 'react'
import { type MsgLogLine, getMsgLog } from '../lib/api-client'

function formatLineTime(t: number): string {
	const d = new Date(t * 1000)
	const pad = (n: number) => String(n).padStart(2, '0')
	const ms = Math.floor((t % 1) * 1000)
	return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${String(ms).padStart(3, '0')}`
}

export function MsgTerminalPanel() {
	const [lines, setLines] = useState<MsgLogLine[]>([])
	const preRef = useRef<HTMLPreElement>(null)

	useEffect(() => {
		let cancelled = false
		const tick = async () => {
			try {
				const { lines: next } = await getMsgLog()
				if (!cancelled) setLines(next)
			} catch {
				if (!cancelled) setLines([])
			}
		}
		void tick()
		const id = window.setInterval(() => void tick(), 400)
		return () => {
			cancelled = true
			window.clearInterval(id)
		}
	}, [])

	useEffect(() => {
		const el = preRef.current
		if (el) el.scrollTop = el.scrollHeight
	}, [lines])

	return (
		<section className='flex min-h-0 flex-1 flex-col'>
			<pre
				ref={preRef}
				className='max-h-36 min-h-28 flex-1 overflow-auto rounded-md bg-[#2c2824] px-2 py-1.5 font-mono text-[11px] leading-relaxed text-[#e8e4d4]'>
				{lines.length === 0 ? (
					<span className='text-[#9a9088]'>暂无输出</span>
				) : (
					lines.map((row, i) => (
						<span key={`${row.t}-${i}`} className='block whitespace-pre-wrap break-all'>
							<span className='text-[#8ac68a]'>{formatLineTime(row.t)}</span> {row.m}
						</span>
					))
				)}
			</pre>
		</section>
	)
}
