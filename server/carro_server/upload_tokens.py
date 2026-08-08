"""Short-lived phone upload tokens (no bearer token on the iPhone)."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass


@dataclass
class UploadSession:
    token: str
    ro_id: str
    tag: str
    expires: float
    uploads: int = 0


class UploadTokenStore:
    def __init__(self) -> None:
        self._sessions: dict[str, UploadSession] = {}

    def create(self, ro_id: str, tag: str = "intake", ttl_sec: int = 3600) -> UploadSession:
        self.purge()
        token = secrets.token_urlsafe(18)
        sess = UploadSession(
            token=token,
            ro_id=ro_id,
            tag=tag or "intake",
            expires=time.time() + max(60, ttl_sec),
        )
        self._sessions[token] = sess
        return sess

    def get(self, token: str) -> UploadSession | None:
        self.purge()
        sess = self._sessions.get(token)
        if not sess:
            return None
        if time.time() > sess.expires:
            self._sessions.pop(token, None)
            return None
        return sess

    def bump(self, token: str) -> None:
        sess = self._sessions.get(token)
        if sess:
            sess.uploads += 1

    def purge(self) -> None:
        now = time.time()
        dead = [k for k, v in self._sessions.items() if now > v.expires]
        for k in dead:
            del self._sessions[k]


UPLOAD_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1"/>
<title>Car-RO photo upload</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: system-ui, sans-serif; margin: 0; padding: 1.25rem; max-width: 28rem; }
  h1 { font-size: 1.25rem; margin: 0 0 .5rem; }
  .meta { color: #888; font-size: .9rem; margin-bottom: 1rem; }
  label { display: block; margin: .75rem 0 .25rem; font-weight: 600; }
  select, input[type=file], button {
    width: 100%; box-sizing: border-box; font-size: 1rem; padding: .75rem;
    border-radius: .5rem; border: 1px solid #555;
  }
  button {
    margin-top: 1rem; background: #0a7; color: #fff; border: none; font-weight: 700;
  }
  button:disabled { opacity: .5; }
  #status { margin-top: 1rem; min-height: 1.5rem; }
  .ok { color: #0a7; }
  .err { color: #c33; }
</style>
</head>
<body>
  <h1>Upload photos</h1>
  <div class="meta">RO <strong>__RO_ID__</strong> · tag default <strong>__TAG__</strong><br/>
  Session expires in about __TTL__ min · Tailscale required</div>
  <form id="f">
    <label for="tag">Tag</label>
    <select id="tag" name="tag">
      <option value="intake">intake</option>
      <option value="diag">diag</option>
      <option value="other">other</option>
    </select>
    <label for="file">Photos (camera or library)</label>
    <input id="file" name="file" type="file" accept="image/*" capture="environment" multiple required/>
    <button type="submit" id="go">Upload</button>
  </form>
  <div id="status"></div>
<script>
const tagSel = document.getElementById('tag');
tagSel.value = "__TAG__";
const status = document.getElementById('status');
document.getElementById('f').addEventListener('submit', async (e) => {
  e.preventDefault();
  const files = document.getElementById('file').files;
  if (!files.length) return;
  const btn = document.getElementById('go');
  btn.disabled = true;
  status.innerHTML = '';
  let ok = 0, fail = 0;
  for (const file of files) {
    const fd = new FormData();
    fd.append('file', file, file.name);
    fd.append('tag', tagSel.value);
    try {
      const r = await fetch(location.pathname, { method: 'POST', body: fd });
      if (!r.ok) throw new Error(await r.text());
      ok++;
      status.innerHTML += `<div class="ok">✓ ${file.name}</div>`;
    } catch (err) {
      fail++;
      status.innerHTML += `<div class="err">✗ ${file.name}: ${err}</div>`;
    }
  }
  status.innerHTML += `<div class="meta">${ok} uploaded, ${fail} failed. You can add more or close this page.</div>`;
  btn.disabled = false;
  document.getElementById('file').value = '';
});
</script>
</body>
</html>
"""
