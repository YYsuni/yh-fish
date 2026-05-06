import { IconFish } from '../icons/icon-fish'

export default function BgPattern() {
	return (
		<>
			<div className='absolute -left-40 h-full w-[160%] -rotate-20 opacity-5'>
				<div className='absolute -top-40 left-0 flex w-full flex-wrap gap-x-30 gap-y-60'>
					{new Array(15).fill(0).map((_, index) => (
						<div key={index} className='flex items-center gap-10 text-4xl font-bold text-white'>
							<IconFish className='w-20' />
							FISHING
						</div>
					))}
				</div>
				<div className='absolute -top-6 -left-60 flex w-full flex-wrap gap-x-30 gap-y-60'>
					{new Array(15).fill(0).map((_, index) => (
						<div key={index} className='flex items-center gap-10 text-4xl font-bold text-white'>
							<IconFish className='w-20' />
							FISHING
						</div>
					))}
				</div>
			</div>
		</>
	)
}
