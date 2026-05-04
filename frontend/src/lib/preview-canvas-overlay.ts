import type { CSSProperties } from 'react'

/** 将裁剪坐标系下的矩形映射到 `canvas` 的 `object-contain` 显示区域（与页面匹配框算法一致）。 */
export function cropRectToCanvasOverlayCss(
	el: HTMLCanvasElement,
	cropW: number,
	cropH: number,
	x: number,
	y: number,
	w: number,
	h: number
): CSSProperties | null {
	if (w <= 0 || h <= 0 || cropW <= 0 || cropH <= 0) return null
	const clientW = el.clientWidth
	const clientH = el.clientHeight
	const bmpW = el.width
	const bmpH = el.height
	if (bmpW <= 0 || bmpH <= 0 || clientW <= 0 || clientH <= 0) return null
	const bx = (x * bmpW) / cropW
	const by = (y * bmpH) / cropH
	const bwR = (w * bmpW) / cropW
	const bhR = (h * bmpH) / cropH
	const uiScale = Math.min(clientW / bmpW, clientH / bmpH)
	const dw = bmpW * uiScale
	const dh = bmpH * uiScale
	const ox = (clientW - dw) / 2
	const oy = (clientH - dh) / 2
	return {
		left: ox + bx * uiScale,
		top: oy + by * uiScale,
		width: bwR * uiScale,
		height: bhR * uiScale
	}
}
