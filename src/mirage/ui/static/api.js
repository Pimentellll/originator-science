async function handle(r) {
  let body = null;
  try { body = await r.json(); } catch { /* non-JSON */ }
  if (!r.ok) throw new Error((body && body.error) || `${r.status} ${r.statusText}`);
  return body;
}
export const api = {
  get: (path) => fetch(path, { cache: "no-store" }).then(handle),
  post: (path, body = {}) =>
    fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then(handle),
};
