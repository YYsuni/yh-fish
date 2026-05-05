import { useEffect, useRef, useState } from 'react'
import { type MsgLogLine, getMsgLog } from '../lib/api-client'

function formatLineTime(t: number): string {
	const d = new Date(t * 1000)
	const pad = (n: number) => String(n).padStart(2, '0')
	return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

/** 距底部小于此像素视为「在底部」，新日志才自动滚到底 */
const STICK_BOTTOM_PX = 32

export function MsgTerminalPanel() {
	const [lines, setLines] = useState<MsgLogLine[]>([])
	const preRef = useRef<HTMLPreElement>(null)
	const stickToBottomRef = useRef(true)

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
		if (!el) return
		const onScroll = () => {
			const gap = el.scrollHeight - el.scrollTop - el.clientHeight
			stickToBottomRef.current = gap <= STICK_BOTTOM_PX
		}
		el.addEventListener('scroll', onScroll, { passive: true })
		return () => el.removeEventListener('scroll', onScroll)
	}, [])

	useEffect(() => {
		const el = preRef.current
		if (!el || !stickToBottomRef.current) return
		el.scrollTop = el.scrollHeight
	}, [lines])

	return (
		<section>
			<pre
				ref={preRef}
				className='scrollbar-thin-transparent mt-4 h-40 min-h-28 w-full flex-1 overflow-auto rounded-sm bg-[#D9D9D9] px-2 py-1.5 font-mono text-[11px] leading-relaxed text-[#333] shadow-inner'>
				{lines.length === 0 ? (
					<span className='text-[#9a9088]'>暂无输出</span>
				) : (
					lines.map((row, i) => (
						<span key={`${row.t}-${i}`} className='block break-all whitespace-pre-wrap'>
							<span className='text-[#178917]'>[{formatLineTime(row.t)}]</span> {row.m}
						</span>
					))
				)}
			</pre>
		</section>
	)
}
