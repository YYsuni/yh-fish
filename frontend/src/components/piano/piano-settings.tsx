import { useCallback, useEffect, useState } from 'react'
import { deletePianoScore, getPianoScores, postPianoScoreSelect, type PianoScoreSummary } from '../../lib/api-client'
import { PianoControls } from './piano-controls'
import type { PianoRemote } from './piano-controls'
import { PianoScoreCreateModal } from './piano-score-create-modal'
import { Modal } from '../ui/modal'

export function PianoSettings({ piano }: { piano: PianoRemote }) {
	const beat = piano.status?.beat_seconds ?? 1
	const title = piano.status?.score_title ?? ''
	const idx = piano.status?.note_index ?? 0
	const cnt = piano.status?.note_count ?? 0
	const running = piano.status?.running ?? false
	const locked = running

	const [scores, setScores] = useState<PianoScoreSummary[]>([])
	const [selectedId, setSelectedId] = useState('')
	const [scoresErr, setScoresErr] = useState<string | null>(null)
	const [selectBusy, setSelectBusy] = useState(false)
	const [deleteBusy, setDeleteBusy] = useState(false)
	const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false)
	const [createOpen, setCreateOpen] = useState(false)
	const [editScoreId, setEditScoreId] = useState<string | null>(null)

	const loadScores = useCallback(async () => {
		try {
			const r = await getPianoScores()
			setScores(r.scores)
			setSelectedId(typeof r.selected_id === 'string' ? r.selected_id : '')
			setScoresErr(null)
		} catch (e) {
			setScoresErr(e instanceof Error ? e.message : String(e))
		}
	}, [])

	useEffect(() => {
		void loadScores()
	}, [loadScores])

	useEffect(() => {
		const sid = piano.status?.score_id
		if (typeof sid === 'string' && sid !== '') {
			setSelectedId(sid)
		}
	}, [piano.status?.score_id])

	const onPickScore = async (id: string) => {
		if (locked || selectBusy || id === selectedId) return
		setSelectBusy(true)
		try {
			await postPianoScoreSelect(id)
			setSelectedId(id)
			await piano.refresh()
			await loadScores()
		} catch (e) {
			console.error(e)
			setScoresErr(e instanceof Error ? e.message : String(e))
		} finally {
			setSelectBusy(false)
		}
	}

	const openEdit = (id: string) => {
		if (locked || id === '') return
		setEditScoreId(id)
	}

	const requestDeleteSelected = () => {
		if (locked || deleteBusy || selectedId === '') return
		setDeleteConfirmOpen(true)
	}

	const onDeleteSelected = async () => {
		if (locked || deleteBusy || selectedId === '') return
		setDeleteBusy(true)
		try {
			await deletePianoScore(selectedId)
			setEditScoreId(null)
			setDeleteConfirmOpen(false)
			await piano.refresh()
			await loadScores()
		} catch (e) {
			console.error(e)
			setScoresErr(e instanceof Error ? e.message : String(e))
		} finally {
			setDeleteBusy(false)
		}
	}

	const selectedScore = scores.find(s => s.id === selectedId)
	const selectedScoreTitle = selectedScore?.title || '当前曲谱'

	return (
		<>
			<div className='mt-2 space-y-1.5'>
				<div className='flex items-center justify-between gap-2'>
					<span className='shrink-0 font-semibold text-black/45'>曲谱</span>
					<div className='flex shrink-0 items-center gap-1'>
						<button
							type='button'
							className='rounded-lg border border-black/25 bg-white/25 px-2 py-1 text-[10px] font-bold hover:bg-white/35 disabled:opacity-40'
							disabled={locked}
							title={locked ? '运行中不可新建，请先停止' : undefined}
							onClick={() => setCreateOpen(true)}>
							新增
						</button>
						{selectedId !== '' ? (
							<>
								<button
									type='button'
									className='rounded-lg border border-black/25 bg-white/25 px-2 py-1 text-[10px] font-bold hover:bg-white/35 disabled:opacity-40'
									disabled={locked}
									title={locked ? '运行中不可编辑，请先停止' : undefined}
									onClick={() => openEdit(selectedId)}>
									编辑
								</button>
								<button
									type='button'
									className='rounded-lg border border-black/25 bg-white/25 px-2 py-1 text-[10px] font-bold text-red-700 hover:bg-white/35 disabled:opacity-40'
									disabled={locked || deleteBusy}
									title={locked ? '运行中不可删除，请先停止' : undefined}
									onClick={requestDeleteSelected}>
									删除
								</button>
							</>
						) : null}
					</div>
				</div>
				{scoresErr ? <p className='text-[10px] font-semibold text-red-700'>{scoresErr}</p> : null}
				<div className='scrollbar-thin-transparent max-h-36 space-y-1 overflow-y-auto pr-0.5' role='radiogroup' aria-label='选择曲谱'>
					{scores.length === 0 ? (
						<p className='text-[10px] text-black/45'>暂无曲谱，请先新增或检查服务端 scores 目录。</p>
					) : (
						scores.map(s => (
							<label
								key={s.id}
								className={`flex cursor-pointer items-center gap-2 rounded-lg px-1 py-1 hover:bg-black/4 ${locked ? 'cursor-not-allowed opacity-60' : ''}`}
								title={locked ? '运行中不可切换曲谱' : s.updateAt}>
								<input
									type='radio'
									className='mt-0.5 accent-[#725d42]'
									name='piano-score'
									checked={selectedId === s.id}
									disabled={locked || selectBusy}
									onChange={() => void onPickScore(s.id)}
								/>
								<span className='min-w-0 flex-1'>
									<span className='block truncate font-semibold text-[#725d42]' title={s.title}>
										{s.title}
									</span>
									<span className='block truncate text-[9px] text-black/40'>{s.note_count} 音</span>
								</span>
							</label>
						))
					)}
				</div>
			</div>

			<PianoControls piano={piano} />

			<PianoScoreCreateModal
				open={createOpen}
				onClose={() => setCreateOpen(false)}
				onSaved={async () => {
					await loadScores()
					await piano.refresh()
				}}
			/>
			<PianoScoreCreateModal
				open={editScoreId != null}
				scoreId={editScoreId}
				onClose={() => setEditScoreId(null)}
				onSaved={async () => {
					await loadScores()
					await piano.refresh()
				}}
			/>
			<Modal open={deleteConfirmOpen} title='删除曲谱' onClose={() => setDeleteConfirmOpen(false)} maxWidthClassName='max-w-sm'>
				<div className='space-y-4 text-xs font-medium text-[#725d42]'>
					<p>
						确认删除「<span className='font-bold text-red-700'>{selectedScoreTitle}</span>」吗？此操作不可恢复。
					</p>
					<div className='flex justify-end gap-2'>
						<button
							type='button'
							className='rounded-xl border-2 border-black/25 bg-white/25 px-4 py-2 text-xs font-bold hover:bg-white/35'
							onClick={() => setDeleteConfirmOpen(false)}
							disabled={deleteBusy}>
							取消
						</button>
						<button
							type='button'
							className='rounded-xl border-2 border-red-900/30 bg-red-700 px-4 py-2 text-xs font-bold text-white hover:bg-red-800 disabled:opacity-40'
							onClick={() => void onDeleteSelected()}
							disabled={deleteBusy}>
							{deleteBusy ? '删除中…' : '确认删除'}
						</button>
					</div>
				</div>
			</Modal>
		</>
	)
}
