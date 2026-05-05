import type { ButtonHTMLAttributes } from 'react'

export type SwitchProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'onChange' | 'role'> & {
	checked: boolean
	onChange: (checked: boolean) => void
	loading?: boolean
	size?: 'small' | 'default'
}

const sizeClass: Record<NonNullable<SwitchProps['size']>, { track: string; thumb: string; translate: string }> = {
	small: {
		track: 'h-[18px] w-9 min-w-9',
		thumb: 'h-3.5 w-3.5',
		translate: 'translate-x-[18px]'
	},
	default: {
		track: 'h-6 w-11 min-w-11',
		thumb: 'h-5 w-5',
		translate: 'translate-x-5'
	}
}

export function Switch({
	checked,
	onChange,
	disabled,
	loading,
	size = 'default',
	className,
	...rest
}: SwitchProps) {
	const s = sizeClass[size]
	const isBusy = Boolean(disabled || loading)

	return (
		<button
			type='button'
			role='switch'
			aria-checked={checked}
			aria-busy={loading || undefined}
			disabled={isBusy}
			className={`relative inline-flex shrink-0 items-center overflow-hidden rounded-full p-0.5 transition-colors focus-visible:ring-2 focus-visible:ring-[#c9a882] focus-visible:ring-offset-2 focus-visible:ring-offset-[#E1DED9] focus-visible:outline-none disabled:cursor-not-allowed ${
				checked ? 'bg-brand' : 'bg-[#c4bba8]'
			} ${isBusy ? 'opacity-60' : ''} ${s.track} ${className ?? ''}`}
			onClick={() => {
				if (isBusy) return
				onChange(!checked)
			}}
			{...rest}>
			<span
				className={`pointer-events-none block rounded-full bg-white shadow-[0_1px_2px_rgba(0,0,0,0.15)] transition-transform duration-200 ease-out will-change-transform ${s.thumb} ${checked ? s.translate : 'translate-x-0'}`}
			/>
			{loading ? (
				<span className='pointer-events-none absolute inset-0 flex items-center justify-center'>
					<span className='h-3 w-3 animate-spin rounded-full border-2 border-white/30 border-t-white' />
				</span>
			) : null}
		</button>
	)
}
