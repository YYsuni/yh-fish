import { useCallback, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type PointerEvent as ReactPointerEvent } from 'react'

function clamp(n: number, min: number, max: number) {
	return Math.min(max, Math.max(min, n))
}

function decimalsIn(n: number): number {
	const s = String(n)
	const i = s.indexOf('.')
	return i === -1 ? 0 : s.length - i - 1
}

function snapToStep(value: number, min: number, max: number, step: number): number {
	if (!(step > 0)) return clamp(value, min, max)
	const snapped = min + Math.round((value - min) / step) * step
	const c = clamp(snapped, min, max)
	const dec = Math.max(decimalsIn(step), decimalsIn(min))
	return dec > 0 ? Number(c.toFixed(dec)) : c
}

export type RangeSliderProps = {
	min: number
	max: number
	step?: number
	value: number
	onChange: (value: number) => void
	disabled?: boolean
	className?: string
}

export function RangeSlider({ min, max, step = 1, value, onChange, disabled, className }: RangeSliderProps) {
	const trackRef = useRef<HTMLDivElement>(null)
	const draggingRef = useRef(false)
	const [focused, setFocused] = useState(false)

	const safe = clamp(value, min, max)
	const pct = max === min ? 0 : ((safe - min) / (max - min)) * 100

	const setFromClientX = useCallback(
		(clientX: number) => {
			const el = trackRef.current
			if (!el || disabled) return
			const rect = el.getBoundingClientRect()
			const x = clamp(clientX - rect.left, 0, rect.width)
			const ratio = rect.width > 0 ? x / rect.width : 0
			const raw = min + ratio * (max - min)
			onChange(snapToStep(raw, min, max, step))
		},
		[disabled, max, min, onChange, step]
	)

	const onPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
		if (disabled) return
		draggingRef.current = true
		setFromClientX(e.clientX)
		e.currentTarget.focus({ preventScroll: true })
		try {
			e.currentTarget.setPointerCapture(e.pointerId)
		} catch {
			/* ignore */
		}
	}

	const onPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
		if (!draggingRef.current || disabled) return
		setFromClientX(e.clientX)
	}

	const onPointerUp = (e: ReactPointerEvent<HTMLDivElement>) => {
		draggingRef.current = false
		try {
			e.currentTarget.releasePointerCapture(e.pointerId)
		} catch {
			/* ignore */
		}
	}

	const bump = (deltaSteps: number) => {
		if (disabled) return
		const next = snapToStep(safe + deltaSteps * step, min, max, step)
		onChange(next)
	}

	const onKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>) => {
		if (disabled) return
		switch (e.key) {
			case 'ArrowRight':
			case 'ArrowUp':
				e.preventDefault()
				bump(1)
				break
			case 'ArrowLeft':
			case 'ArrowDown':
				e.preventDefault()
				bump(-1)
				break
			case 'Home':
				e.preventDefault()
				onChange(min)
				break
			case 'End':
				e.preventDefault()
				onChange(max)
				break
			default:
				break
		}
	}

	return (
		<div className={`flex w-full items-center py-1 ${className ?? ''}`}>
			<div
				ref={trackRef}
				role='slider'
				aria-orientation='horizontal'
				tabIndex={disabled ? -1 : 0}
				aria-valuemin={min}
				aria-valuemax={max}
				aria-valuenow={safe}
				aria-disabled={disabled || undefined}
				className={`relative h-1 w-full shrink-0 touch-none rounded-full bg-white/80 select-none ${
					disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'
				}`}
				onPointerDown={onPointerDown}
				onPointerMove={onPointerMove}
				onPointerUp={onPointerUp}
				onPointerCancel={onPointerUp}
				onKeyDown={onKeyDown}
				onFocus={() => setFocused(true)}
				onBlur={() => setFocused(false)}>
				<div className='bg-brand pointer-events-none absolute inset-y-0 -top-0.5 left-0 h-2 rounded-full' style={{ width: `${pct}%` }} />
				<div
					className='pointer-events-none absolute top-1/2 h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-[#E4AE55] bg-white shadow-[0_1px_2px_rgba(0,0,0,0.12)]'
					style={{ left: `${pct}%` }}
				/>
			</div>
		</div>
	)
}
