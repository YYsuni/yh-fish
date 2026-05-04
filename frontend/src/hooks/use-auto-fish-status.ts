import { useCallback, useEffect, useState } from 'react'
import { getAutoFishStatus, type AutoFishStatusResponse } from '../lib/api-client'

export function useAutoFishStatus(pollMs = 1500) {
	const [status, setStatus] = useState<AutoFishStatusResponse | null>(null)
	const [err, setErr] = useState<string | null>(null)

	const refresh = useCallback(async () => {
		try {
			const s = await getAutoFishStatus()
			setStatus(s)
			setErr(null)
		} catch (e) {
			setErr(e instanceof Error ? e.message : String(e))
		}
	}, [])

	useEffect(() => {
		void refresh()
		const id = window.setInterval(() => void refresh(), pollMs)
		return () => window.clearInterval(id)
	}, [refresh, pollMs])

	return { status, err, refresh }
}
