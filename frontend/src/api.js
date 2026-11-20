let token = null;
try { token = sessionStorage.getItem("egng_token"); } catch (e) {}
export const setToken = (t) => { token = t; try { t ? sessionStorage.setItem("egng_token", t) : sessionStorage.removeItem("egng_token"); } catch (e) {} };
export const hasToken = () => !!token;

export async function api(path, opts = {}) {
  const res = await fetch("/api/v1" + path, {
    method: opts.method || "GET",
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: "Bearer " + token } : {}) },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (opts.blob && res.ok) return res.blob();
  let data = null;
  try { data = await res.json(); } catch (e) {}
  if (!res.ok) {
    const e = new Error((data && data.error) || res.statusText);
    e.status = res.status;
    throw e;
  }
  return data;
}

export async function download(path, filename) {
  const blob = await api(path, { blob: true });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = filename; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}
