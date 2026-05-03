// All requests go through Vite's proxy to the FastAPI backend (see vite.config.js).

async function request(path, options = {}) {
  const r = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  if (!r.ok) {
    let detail
    try { detail = (await r.json()).detail } catch {}
    throw new Error(detail || `${r.status} ${r.statusText}`)
  }
  return r.json()
}

// POST `body` and read newline-delimited JSON events as they arrive.
// onEvent(obj) is invoked once per parsed line.
async function streamPost(path, body, onEvent) {
  const r = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) {
    let detail
    try { detail = (await r.json()).detail } catch {}
    throw new Error(detail || `${r.status} ${r.statusText}`)
  }
  const reader = r.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    let nl
    while ((nl = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, nl).trim()
      buf = buf.slice(nl + 1)
      if (line) onEvent(JSON.parse(line))
    }
  }
  const tail = buf.trim()
  if (tail) onEvent(JSON.parse(tail))
}

export const api = {
  styles: () => request('/api/styles'),
  models: () => request('/api/models'),
  enhanceStream: (body, onEvent) => streamPost('/api/enhance', body, onEvent),
  generateStream: (body, onEvent) => streamPost('/api/generate', body, onEvent),
  pullStream: (model, onEvent) => streamPost('/api/pull', { model }, onEvent),
  list: () => request('/api/images'),
  remove: (id) => request(`/api/images/${id}`, { method: 'DELETE' }),
  fileUrl: (id, download = false) => `/api/images/${id}/file${download ? '?download=true' : ''}`,
  thumbUrl: (id) => `/api/images/${id}/thumb`,
}
