import { useCallback, useEffect, useState } from 'react'
import { getPianoScore, postPianoScoreCreate, putPianoScoreUpdate } from '../../lib/api-client'
import type { PianoNotePayload } from '../../lib/api-client'
import { Modal } from '../ui/modal'

type Pitch = 'low' | 'mid' | 'high'

type Tone = {
	degree: number
	pitch: Pitch
}

type EditorCard = {
	key: string
	degree: number
	pitch: Pitch
	chordTones: Tone[]
	beatNum: number
	beatDen: number
}

const BEAT_DENOMS = [2, 4, 8, 12] as const
const DEFAULT_BEAT_NUM = 1
const DEFAULT_BEAT_DEN = 2
const KEY_NOTE_MAP: Record<string, { degree: number; pitch: Pitch }> = {
	...Object.fromEntries('zxcvbnm'.split('').map((key, i) => [key, { degree: i + 1, pitch: 'low' as const }])),
	...Object.fromEntries('asdfghj'.split('').map((key, i) => [key, { degree: i + 1, pitch: 'mid' as const }])),
	...Object.fromEntries('qwertyu'.split('').map((key, i) => [key, { degree: i + 1, pitch: 'high' as const }]))
}

const DEFAULT_RAW_HINT = `{
\t"title": "示例",
\t"beatSeconds": 0.5,
\t"notes": [
\t\t{ "num": "3", "beat": 1, "pitch": "mid" },
\t\t{ "keys": [{ "num": "1", "pitch": "mid" }, { "num": "5", "pitch": "mid" }], "beat": 1 }
\t]
}`

const SCORE_JSON_PROMPT = `请根据我提供的乐谱图片或简谱内容，生成一个可直接粘贴到钢琴曲谱编辑器里的 JSON。

输出要求：
1. 只输出 JSON，不要 Markdown，不要解释。
2. JSON 根字段必须包含：
   - "title": 曲谱标题，字符串
   - "beatSeconds": 一拍持续秒数，数字，默认可用 0.5
   - "notes": 音符数组
3. notes 里的每个音符格式为：
   { "num": "1", "beat": 1, "pitch": "mid" }
4. 如果同一拍需要同时按多个音，用 keys 表示和弦：
   { "keys": [{ "num": "1", "pitch": "mid" }, { "num": "3", "pitch": "mid" }], "beat": 1 }
5. num 使用字符串 "0"~"7"，其中 "0" 表示休止符。
6. pitch 只能使用 "low"、"mid"、"high"，分别代表低音、中音、高音；如果乐谱没标明音高，默认用 "mid"。
7. beat 表示该音符/和弦占几拍，可以是 0.25、0.5、1、1.5、2、4 等数字。

示例：
{
	"title": "示例曲谱",
	"beatSeconds": 0.5,
	"notes": [
		{ "num": "3", "beat": 1, "pitch": "mid" },
		{ "num": "0", "beat": 0.5, "pitch": "mid" },
		{ "keys": [{ "num": "1", "pitch": "mid" }, { "num": "5", "pitch": "mid" }], "beat": 2 }
	]
}`

function newCard(patch: Partial<Omit<EditorCard, 'key'>> = {}): EditorCard {
	return {
		key: crypto.randomUUID(),
		degree: 1,
		pitch: 'mid',
		chordTones: [],
		beatNum: DEFAULT_BEAT_NUM,
		beatDen: DEFAULT_BEAT_DEN,
		...patch
	}
}

function isEditableTarget(target: EventTarget | null): boolean {
	if (!(target instanceof HTMLElement)) return false
	const tag = target.tagName.toLowerCase()
	return tag === 'input' || tag === 'textarea' || tag === 'select' || target.isContentEditable
}

function normalizePitch(raw: unknown): Pitch {
	return raw === 'low' || raw === 'mid' || raw === 'high' ? raw : 'mid'
}

function beatToFraction(raw: unknown): { beatNum: number; beatDen: number } {
	const beat = typeof raw === 'number' && Number.isFinite(raw) && raw > 0 ? raw : 1
	const preferred = [2, 4, 8, 12] as const
	for (const den of preferred) {
		const num = Math.round(beat * den)
		if (num >= 1 && num <= 12 && Math.abs(num / den - beat) < 0.0001) {
			return { beatNum: num, beatDen: den }
		}
	}
	return { beatNum: Math.min(12, Math.max(1, Math.round(beat * 4))), beatDen: 4 }
}

function noteToCard(note: PianoNotePayload): EditorCard {
	const keys = Array.isArray(note.keys) && note.keys.length > 0 ? note.keys : [{ num: note.num ?? '0', pitch: note.pitch ?? 'mid' }]
	const primary = keys[0] ?? { num: '0', pitch: 'mid' }
	const degree = Number.parseInt(String(primary.num ?? '0'), 10)
	return newCard({
		degree: Number.isFinite(degree) && degree >= 0 && degree <= 7 ? degree : 0,
		pitch: normalizePitch(primary.pitch),
		chordTones: keys.slice(1).map(tone => {
			const n = Number.parseInt(String(tone.num ?? '0'), 10)
			return {
				degree: Number.isFinite(n) && n >= 0 && n <= 7 ? n : 0,
				pitch: normalizePitch(tone.pitch)
			}
		}),
		...beatToFraction(note.beat)
	})
}

export function PianoScoreCreateModal({
	open,
	scoreId,
	onClose,
	onSaved
}: {
	open: boolean
	scoreId?: string | null
	onClose: () => void
	onSaved: () => void | Promise<void>
}) {
	const [tab, setTab] = useState<'friendly' | 'raw'>('friendly')
	const [title, setTitle] = useState('')
	const [beatSeconds, setBeatSeconds] = useState('0.5')
	const [cards, setCards] = useState<EditorCard[]>(() => [])
	const [rawText, setRawText] = useState(DEFAULT_RAW_HINT)
	const [promptCopied, setPromptCopied] = useState(false)
	const [busy, setBusy] = useState(false)
	const [err, setErr] = useState<string | null>(null)
	const activeScoreId = typeof scoreId === 'string' && scoreId !== '' ? scoreId : null
	const editing = activeScoreId != null

	useEffect(() => {
		if (!open) return
		setTab('friendly')
		setTitle('')
		setBeatSeconds('0.5')
		setCards([])
		setRawText(DEFAULT_RAW_HINT)
		setPromptCopied(false)
		setErr(null)
		setBusy(false)
		if (activeScoreId == null) return
		let cancelled = false
		setBusy(true)
		void (async () => {
			try {
				const score = await getPianoScore(activeScoreId)
				if (cancelled) return
				const bs = score.beatSeconds ?? score.beat_seconds ?? 1
				setTitle(score.title ?? '')
				setBeatSeconds(String(bs))
				const nextCards = Array.isArray(score.notes) && score.notes.length > 0 ? score.notes.map(noteToCard) : []
				setCards(nextCards)
				setRawText(JSON.stringify({ title: score.title, beatSeconds: bs, notes: score.notes, createAt: score.createAt, updateAt: score.updateAt }, null, '\t'))
			} catch (e) {
				if (!cancelled) setErr(e instanceof Error ? e.message : String(e))
			} finally {
				if (!cancelled) setBusy(false)
			}
		})()
		return () => {
			cancelled = true
		}
	}, [activeScoreId, open])

	const updateCard = useCallback((key: string, patch: Partial<EditorCard>) => {
		setCards(prev => prev.map(c => (c.key === key ? { ...c, ...patch } : c)))
	}, [])

	const updateChordTone = useCallback((key: string, index: number, patch: Partial<Tone>) => {
		setCards(prev =>
			prev.map(c =>
				c.key === key
					? {
							...c,
							chordTones: c.chordTones.map((tone, i) => (i === index ? { ...tone, ...patch } : tone))
						}
					: c
			)
		)
	}, [])

	const addChordTone = useCallback((key: string) => {
		setCards(prev => prev.map(c => (c.key === key ? { ...c, chordTones: [...c.chordTones, { degree: 1, pitch: c.pitch }] } : c)))
	}, [])

	const removeChordTone = useCallback((key: string, index: number) => {
		setCards(prev => prev.map(c => (c.key === key ? { ...c, chordTones: c.chordTones.filter((_, i) => i !== index) } : c)))
	}, [])

	const removeCard = useCallback((key: string) => {
		setCards(prev => prev.filter(c => c.key !== key))
	}, [])

	const insertCardBefore = useCallback(
		(key: string) => {
			setCards(prev => {
				const index = prev.findIndex(c => c.key === key)
				if (index < 0) return prev
				const cur = prev[index]
				const next = prev.slice()
				next.splice(index, 0, newCard({ degree: cur?.degree ?? 1, pitch: cur?.pitch ?? 'mid' }))
				return next
			})
		},
		[setCards]
	)

	const insertCardAfter = useCallback(
		(key: string) => {
			setCards(prev => {
				const index = prev.findIndex(c => c.key === key)
				if (index < 0) return prev
				const cur = prev[index]
				const next = prev.slice()
				next.splice(index + 1, 0, newCard({ degree: cur?.degree ?? 1, pitch: cur?.pitch ?? 'mid' }))
				return next
			})
		},
		[setCards]
	)

	const removeLastCard = useCallback(() => {
		setCards(prev => prev.slice(0, -1))
	}, [])

	const appendCard = useCallback((degree: number, pitch?: Pitch) => {
		setCards(prev => {
			const last = prev[prev.length - 1]
			return [...prev, newCard({ degree, pitch: pitch ?? last?.pitch ?? 'mid' })]
		})
	}, [])

	useEffect(() => {
		if (!open || tab !== 'friendly') return
		const onKeyDown = (e: KeyboardEvent) => {
			if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey || e.isComposing || isEditableTarget(e.target)) return
			const key = e.key.toLowerCase()
			if (key === 'backspace' || key === 'backup') {
				e.preventDefault()
				removeLastCard()
				return
			}
			if (/^[0-7]$/.test(key)) {
				e.preventDefault()
				appendCard(Number(key))
				return
			}
			const mapped = KEY_NOTE_MAP[key]
			if (mapped) {
				e.preventDefault()
				appendCard(mapped.degree, mapped.pitch)
			}
		}
		window.addEventListener('keydown', onKeyDown)
		return () => window.removeEventListener('keydown', onKeyDown)
	}, [appendCard, open, removeLastCard, tab])

	const onSubmit = async () => {
		setErr(null)
		setBusy(true)
		try {
			if (tab === 'raw') {
				if (activeScoreId != null) {
					await putPianoScoreUpdate(activeScoreId, { mode: 'raw', raw_json: rawText })
				} else {
					await postPianoScoreCreate({ mode: 'raw', raw_json: rawText })
				}
			} else {
				const bs = Number.parseFloat(beatSeconds)
				if (!Number.isFinite(bs) || bs < 0.05 || bs > 120) {
					throw new Error('beatSeconds 须在 0.05 ~ 120 之间')
				}
				const notes = cards.map(c => {
					const beat = c.beatNum / c.beatDen
					const primary = { num: c.degree === 0 ? '0' : String(c.degree), pitch: c.pitch }
					if (c.chordTones.length === 0) return { ...primary, beat }
					return {
						keys: [
							primary,
							...c.chordTones.map(tone => ({
								num: tone.degree === 0 ? '0' : String(tone.degree),
								pitch: tone.pitch
							}))
						],
						beat
					}
				})
				const payload = {
					mode: 'friendly' as const,
					title: title.trim() || '未命名',
					beatSeconds: bs,
					notes
				}
				if (activeScoreId != null) {
					await putPianoScoreUpdate(activeScoreId, payload)
				} else {
					await postPianoScoreCreate(payload)
				}
			}
			await onSaved()
			onClose()
		} catch (e) {
			setErr(e instanceof Error ? e.message : String(e))
		} finally {
			setBusy(false)
		}
	}

	const onCopyPrompt = async () => {
		try {
			await navigator.clipboard.writeText(SCORE_JSON_PROMPT)
			setPromptCopied(true)
			window.setTimeout(() => setPromptCopied(false), 1800)
		} catch (e) {
			setErr(e instanceof Error ? e.message : String(e))
		}
	}

	return (
		<Modal open={open} title={editing ? '编辑曲谱' : '新增曲谱'} onClose={onClose} layout='fullscreen'>
			<div className='mx-auto flex max-w-4xl flex-col gap-4'>
				<div className='flex flex-wrap gap-2'>
					<button
						type='button'
						className={`rounded-xl px-4 py-2 text-xs font-bold transition-colors ${
							tab === 'friendly' ? 'bg-[#725d42] text-white' : 'bg-white/25 text-black/70 hover:bg-white/35'
						}`}
						onClick={() => setTab('friendly')}>
						卡片交互
					</button>
					<button
						type='button'
						className={`rounded-xl px-4 py-2 text-xs font-bold transition-colors ${
							tab === 'raw' ? 'bg-[#725d42] text-white' : 'bg-white/25 text-black/70 hover:bg-white/35'
						}`}
						onClick={() => setTab('raw')}>
						粘贴 JSON
					</button>
				</div>

				{tab === 'friendly' ? (
					<>
						<div className='grid gap-3 sm:grid-cols-2'>
							<label className='flex flex-col gap-1 text-xs font-bold text-black/55'>
								<span>标题</span>
								<input
									className='rounded-xl border-2 border-black/25 bg-white/35 px-3 py-2 text-sm font-semibold text-black/80 outline-none focus:ring-2 focus:ring-black/15'
									value={title}
									onChange={e => setTitle(e.target.value)}
									placeholder='曲名'
								/>
							</label>
							<label className='flex flex-col gap-1 text-xs font-bold text-black/55'>
								<span>beatSeconds（一拍秒数）</span>
								<input
									className='rounded-xl border-2 border-black/25 bg-white/35 px-3 py-2 font-mono text-sm font-semibold text-black/80 outline-none focus:ring-2 focus:ring-black/15'
									inputMode='decimal'
									value={beatSeconds}
									onChange={e => setBeatSeconds(e.target.value)}
								/>
							</label>
						</div>
						<p className='text-[10px] font-semibold text-black/45'>
							快捷输入：按 0~7 追加音符；按 zxcvbnm / asdfghj / qwertyu 会按低音 / 中音 / 高音自动追加对应音符；按 Backspace 删除最后一个音。卡片内可添加和音。
						</p>

						<div className='grid grid-cols-[repeat(auto-fill,minmax(96px,1fr))] items-start gap-x-2 gap-y-6'>
							{cards.map(c => (
								<div key={c.key} className='group relative rounded-2xl border-2 border-black/30 bg-white/25 p-2 shadow-sm'>
									<button
										type='button'
										className='absolute top-14 left-0 z-10 flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-full border border-black/25 bg-black/30 text-[10px] font-bold text-white opacity-0 transition-opacity group-hover:opacity-100 hover:bg-black/70'
										title='向左新增'
										onClick={e => {
											e.stopPropagation()
											insertCardBefore(c.key)
										}}>
										←
									</button>
									<button
										type='button'
										className='absolute top-14 right-0 z-10 flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-full border border-black/25 bg-black/30 text-[10px] font-bold text-white opacity-0 transition-opacity group-hover:opacity-100 hover:bg-black/70'
										title='向右新增'
										onClick={e => {
											e.stopPropagation()
											insertCardAfter(c.key)
										}}>
										→
									</button>
									<button
										type='button'
										className='absolute top-1 right-1 flex h-6 w-6 items-center justify-center rounded-full border border-black/25 bg-black/50 text-xs font-bold text-white opacity-0 transition-opacity group-hover:opacity-100 hover:bg-black/70'
										title='删除此音符'
										onClick={e => {
											e.stopPropagation()
											removeCard(c.key)
										}}>
										×
									</button>
									<button
										type='button'
										title='添加和音'
										className='absolute top-1 left-1 flex h-6 w-6 items-center justify-center rounded-full border border-black/25 bg-black/50 text-xs text-white opacity-0 transition-opacity group-hover:opacity-100 hover:bg-black/70'
										onClick={() => addChordTone(c.key)}>
										和
									</button>
									<button
										type='button'
										className='mb-2 flex h-14 w-full items-center justify-center rounded-xl border border-black/20 bg-white/40 text-2xl font-bold text-[#725d42] hover:bg-white/55'
										onClick={() => updateCard(c.key, { degree: (c.degree + 1) % 8 })}>
										{c.degree === 0 ? <span className='text-base'>休</span> : c.degree}
									</button>
									<div className='mb-2 flex gap-0.5'>
										{(
											[
												['低', 'low'],
												['中', 'mid'],
												['高', 'high']
											] as const
										).map(([label, pitch]) => (
											<button
												key={pitch}
												type='button'
												className={`flex-1 rounded-lg py-1 text-[10px] font-bold ${
													c.pitch === pitch ? 'bg-[#725d42] text-white' : 'bg-black/10 text-black/65 hover:bg-black/15'
												}`}
												onClick={() => updateCard(c.key, { pitch })}>
												{label}
											</button>
										))}
									</div>
									{c.chordTones.length > 0 ? (
										<div className='mb-2 space-y-2 rounded-xl'>
											{c.chordTones.map((tone, i) => (
												<div key={i}>
													<div className='flex items-center gap-1'>
														<button
															type='button'
															className='h-7 flex-1 shrink-0 rounded-lg bg-white/45 text-xs font-bold text-[#725d42] hover:bg-white/60'
															onClick={() => updateChordTone(c.key, i, { degree: (tone.degree + 1) % 8 })}>
															{tone.degree === 0 ? '休' : tone.degree}
														</button>
														<button
															type='button'
															className='h-6 w-6 shrink-0 rounded-full bg-black/20 text-xs font-bold text-white hover:bg-black/40'
															title='删除和音'
															onClick={() => removeChordTone(c.key, i)}>
															×
														</button>
													</div>
													<div className='mt-2 flex min-w-0 gap-0.5'>
														{(
															[
																['低', 'low'],
																['中', 'mid'],
																['高', 'high']
															] as const
														).map(([label, pitch]) => (
															<button
																key={pitch}
																type='button'
																className={`flex-1 rounded-md py-1 text-[9px] font-bold ${
																	tone.pitch === pitch ? 'bg-[#725d42] text-white' : 'bg-black/10 text-black/65 hover:bg-black/15'
																}`}
																onClick={() => updateChordTone(c.key, i, { pitch })}>
																{label}
															</button>
														))}
													</div>
												</div>
											))}
										</div>
									) : null}

									<div className='flex items-center gap-1 text-[10px] font-bold text-black/50'>
										<select
											className='min-w-0 flex-1 rounded-lg border border-black/20 bg-white/45 py-1 text-center text-[11px] font-semibold text-black/75'
											value={c.beatNum}
											onChange={e => updateCard(c.key, { beatNum: Number(e.target.value) })}>
											{Array.from({ length: 12 }, (_, i) => i + 1).map(n => (
												<option key={n} value={n}>
													{n}
												</option>
											))}
										</select>
										<span className='shrink-0'>/</span>
										<select
											className='min-w-0 flex-1 rounded-lg border border-black/20 bg-white/45 py-1 text-center text-[11px] font-semibold text-black/75'
											value={c.beatDen}
											onChange={e => updateCard(c.key, { beatDen: Number(e.target.value) })}>
											{BEAT_DENOMS.map(d => (
												<option key={d} value={d}>
													{d}
												</option>
											))}
										</select>
									</div>
								</div>
							))}
							<button
								type='button'
								className='flex min-h-[140px] items-center justify-center rounded-2xl border-2 border-dashed border-black/35 bg-white/10 text-sm font-bold text-black/45 hover:bg-white/20 hover:text-black/65'
								onClick={() => setCards(prev => [...prev, newCard({ pitch: prev[prev.length - 1]?.pitch ?? 'mid' })])}>
								＋ 新增
							</button>
						</div>
					</>
				) : (
					<div className='flex flex-col gap-2'>
						<p className='text-xs leading-relaxed text-black/60'>
							请粘贴完整 JSON，字段包含 <code className='font-mono text-[11px] text-black/75'>title</code>、
							<code className='font-mono text-[11px] text-black/75'>beatSeconds</code>、<code className='font-mono text-[11px] text-black/75'>notes</code>
							；每条音符形如 <code className='font-mono text-[11px] text-black/75'>{'{ "num": "3", "beat": 1, "pitch": "mid" }'}</code>
							；同一拍多个音用 <code className='font-mono text-[11px] text-black/75'>keys</code> 数组。可将纸质 / 截图谱交给 AI，请其按此结构生成 JSON。
						</p>
						<div>
							<button
								type='button'
								className='rounded-xl border-2 border-black/25 bg-white/25 px-3 py-2 text-xs font-bold text-[#725d42] hover:bg-white/35'
								onClick={() => void onCopyPrompt()}>
								{promptCopied ? '已复制' : '复制提示词'}
							</button>
						</div>
						<textarea
							className='min-h-[280px] w-full rounded-2xl border-2 border-black/25 bg-white/35 p-3 font-mono text-xs leading-relaxed text-black/80 outline-none focus:ring-2 focus:ring-black/15'
							spellCheck={false}
							value={rawText}
							onChange={e => setRawText(e.target.value)}
						/>
					</div>
				)}

				{err ? <p className='text-xs font-semibold text-red-700'>{err}</p> : null}

				<div className='flex justify-end gap-2 pb-2'>
					<button
						type='button'
						className='rounded-xl border-2 border-black/25 bg-white/25 px-4 py-2 text-xs font-bold hover:bg-white/35'
						onClick={onClose}
						disabled={busy}>
						取消
					</button>
					<button type='button' className='brand-btn px-5 py-2 text-xs font-bold' onClick={() => void onSubmit()} disabled={busy}>
						{busy ? '保存中…' : editing ? '保存修改' : '保存曲谱'}
					</button>
				</div>
			</div>
		</Modal>
	)
}
