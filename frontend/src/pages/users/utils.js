export function isWindowExpired(updatedAt) {
  if (!updatedAt) return false
  const ts = typeof updatedAt === 'number' && updatedAt < 100000000000
    ? updatedAt
    : typeof updatedAt === 'number' ? updatedAt : new Date(updatedAt).getTime() / 1000
  return Date.now() / 1000 - ts > 86400
}

export function safeFormatDate(dateVal) {
  if (!dateVal) return ''
  try {
    const parsedObj = typeof dateVal === 'number' && dateVal < 100000000000
      ? new Date(dateVal * 1000)
      : new Date(dateVal)
    return parsedObj.toLocaleString("en-IN", { timeZone: "Asia/Kolkata", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", hour12: true })
  } catch (e) {
    return String(dateVal).split('T')[0]
  }
}
