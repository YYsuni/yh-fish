import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useId } from 'react'
import { createPortal } from 'react-dom'

export function Modal({
	open,
	title,
	onClose,
	children,
	maxWidthClassName = 'max-w-lg',
	layout = 'dialog'
}: {
	open: boolean
	title: string
	onClose: () => void
	children: React.ReactNode
	maxWidthClassName?: string
	layout?: 'dialog' | 'fullscreen'
}) {
	const titleId = useId()
	const descriptionId = useId()

	useEffect(() => {
		if (!open) return
		const onKeyDown = (e: KeyboardEvent) => {
			if (e.key === 'Escape') onClose()
		}
		window.addEventListener('keydown', onKeyDown)
		return () => window.removeEventListener('keydown', onKeyDown)
	}, [open, onClose])

	if (typeof document === 'undefined') return null

	return createPortal(
		<AnimatePresence>
			{open ? (
				<motion.div
					className={layout === 'fullscreen' ? 'fixed inset-0 z-50 flex flex-col p-0' : 'fixed inset-0 z-50 flex items-center justify-center p-4'}
					initial={{ opacity: 0 }}
					animate={{ opacity: 1 }}
					exit={{ opacity: 0 }}
					transition={{ duration: 0.14 }}>
					<motion.button
						type='button'
						aria-label='Close dialog overlay'
						className='absolute inset-0 bg-black/55'
						initial={{ opacity: 0 }}
						animate={{ opacity: 1 }}
						exit={{ opacity: 0 }}
						onClick={onClose}
					/>

					<motion.div
						role='dialog'
						aria-modal='true'
						aria-labelledby={titleId}
						aria-describedby={descriptionId}
						className={
							layout === 'fullscreen'
								? 'relative flex h-dvh max-h-dvh w-full flex-col rounded-none border-0 bg-[#E1DED9] text-[#080502] shadow-[0_20px_60px_rgba(0,0,0,0.45)]'
								: `relative w-full ${maxWidthClassName} rounded-2xl border-2 border-black bg-[#E1DED9] text-[#080502] shadow-[0_20px_60px_rgba(0,0,0,0.45)]`
						}
						initial={{ opacity: 0, scale: layout === 'fullscreen' ? 1 : 0.98, y: layout === 'fullscreen' ? 0 : 8 }}
						animate={{ opacity: 1, scale: 1, y: 0 }}
						exit={{ opacity: 0, scale: layout === 'fullscreen' ? 1 : 0.98, y: layout === 'fullscreen' ? 0 : 8 }}
						transition={{ type: 'spring', stiffness: 520, damping: 38 }}>
						<div
							className={
								layout === 'fullscreen'
									? 'flex shrink-0 items-center justify-between border-b-2 border-black/40 px-4 py-3 sm:px-6'
									: 'flex items-center justify-between border-b-2 border-black/40 px-5 py-3'
							}>
							<h3 id={titleId} className='text-sm font-bold text-[#725d42]'>
								{title}
							</h3>
							<button
								type='button'
								className='h-8 w-8 rounded-full border-2 border-black/20 bg-black/40 font-bold text-white/40 ring-2 ring-white/5 transition-colors hover:bg-black/80 hover:text-white'
								style={{ boxShadow: '0 0 2px 0 rgba(255, 255, 255, 0.5) inset' }}
								aria-label='关闭'
								onClick={onClose}>
								<span className='text-base leading-none'>×</span>
							</button>
						</div>
						<div
							id={descriptionId}
							className={layout === 'fullscreen' ? 'scrollbar-thin-transparent min-h-0 flex-1 overflow-auto px-4 py-4 sm:px-6 sm:py-5' : 'px-5 py-4'}>
							{children}
						</div>
					</motion.div>
				</motion.div>
			) : null}
		</AnimatePresence>,
		document.body
	)
}
