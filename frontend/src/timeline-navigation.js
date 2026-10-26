// Preserve the time under the pointer, excluding the fixed-width track label column.
export function anchoredTimelineScroll(oldWidth, newWidth, scrollLeft, anchorX) {
  const time = (scrollLeft + anchorX - 190) / Math.max(1, oldWidth - 202);
  return Math.max(0, 190 + time * Math.max(1, newWidth - 202) - anchorX);
}
export function timelineShortcut(event) {
  if (event.ctrlKey || event.metaKey || event.altKey) return null;
  const key = event.key.toLowerCase();
  if (['w', '+', '='].includes(key)) return 'in';
  if (['s', '-', '_'].includes(key)) return 'out';
  if (['a', 'arrowleft'].includes(key)) return 'left';
  if (['d', 'arrowright'].includes(key)) return 'right';
  if (key === '0') return 'reset';
  if (key === 'home') return 'start';
  if (key === 'end') return 'end';
  return null;
}
