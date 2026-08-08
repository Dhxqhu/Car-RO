"""Phone / Shortcuts upload tokens (persisted; no bearer token on the iPhone)."""

from __future__ import annotations

import json
import os
import secrets
import time
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class UploadSession:
    token: str
    ro_id: str
    tag: str
    expires: float
    uploads: int = 0
    kind: str = "web"  # web | shortcut


class UploadTokenStore:
    """In-memory + JSON persistence under the data dir (survives server restarts)."""

    def __init__(self, path: Path | None = None) -> None:
        self._sessions: dict[str, UploadSession] = {}
        self.path = path or self._default_path()
        self._load()

    @staticmethod
    def _default_path() -> Path:
        root = os.environ.get("CARRO_DATA_DIR", "").strip()
        if root:
            return Path(root) / "upload_sessions.json"
        return Path.home() / "carro-data" / "upload_sessions.json"

    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        for item in raw.get("sessions") or []:
            try:
                sess = UploadSession(
                    token=str(item["token"]),
                    ro_id=str(item["ro_id"]),
                    tag=str(item.get("tag") or "intake"),
                    expires=float(item["expires"]),
                    uploads=int(item.get("uploads") or 0),
                    kind=str(item.get("kind") or "web"),
                )
            except (KeyError, TypeError, ValueError):
                continue
            self._sessions[sess.token] = sess
        self.purge()

    def _save(self) -> None:
        self.purge()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "sessions": [asdict(s) for s in self._sessions.values()],
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def create(
        self,
        ro_id: str,
        tag: str = "intake",
        ttl_sec: int = 3600,
        *,
        kind: str = "web",
    ) -> UploadSession:
        self.purge()
        token = secrets.token_urlsafe(18)
        sess = UploadSession(
            token=token,
            ro_id=ro_id,
            tag=tag or "intake",
            expires=time.time() + max(60, ttl_sec),
            kind=kind or "web",
        )
        self._sessions[token] = sess
        self._save()
        return sess

    def get(self, token: str) -> UploadSession | None:
        self.purge()
        return self._sessions.get(token)

    def bump(self, token: str) -> None:
        sess = self._sessions.get(token)
        if sess:
            sess.uploads += 1
            self._save()

    def purge(self) -> None:
        now = time.time()
        dead = [k for k, v in self._sessions.items() if now > v.expires]
        for k in dead:
            del self._sessions[k]
        if dead and self.path.parent.is_dir():
            try:
                self._save()
            except OSError:
                pass


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
  select, input[type=file], textarea, button {
    width: 100%; box-sizing: border-box; font-size: 1rem; padding: .75rem;
    border-radius: .5rem; border: 1px solid #555;
  }
  textarea { min-height: 4.5rem; resize: vertical; }
  .pick { display: grid; gap: .5rem; margin-top: .25rem; }
  .pick input[type=file] {
    position: absolute; width: 1px; height: 1px; opacity: 0; overflow: hidden;
  }
  .filebtn {
    display: block; text-align: center; font-weight: 700; font-size: 1rem;
    padding: .85rem; border-radius: .5rem; border: 1px solid #0a7;
    background: #0a7; color: #fff; cursor: pointer;
  }
  .filebtn.secondary { background: transparent; color: inherit; border-color: #555; }
  .hint { color: #888; font-size: .85rem; margin: .5rem 0 0; }
  button {
    margin-top: 1rem; background: #0a7; color: #fff; border: none; font-weight: 700;
  }
  button:disabled { opacity: .5; }
  #status { margin-top: 1rem; min-height: 1.5rem; }
  .ok { color: #0a7; }
  .err { color: #c33; }
  a { color: #0a7; }
</style>
</head>
<body>
  <h1>Upload photos</h1>
  <div class="meta">RO <strong>__RO_ID__</strong> · tag default <strong>__TAG__</strong><br/>
  Session expires in about __TTL__ min · Tailscale required<br/>
  <a href="/u/__TOKEN__/shortcut">iPhone Shortcuts setup</a></div>
  <form id="f">
    <label for="tag">Tag</label>
    <select id="tag" name="tag">
      <option value="intake">intake</option>
      <option value="diag">diag</option>
      <option value="other">other</option>
    </select>
    <label for="notes">Notes (optional)</label>
    <textarea id="notes" name="notes" placeholder="What this photo shows…"></textarea>
    <label>Photos</label>
    <div class="pick">
      <!-- No capture= on library input — iOS otherwise skips Photo Library -->
      <label class="filebtn" for="file">Choose from library</label>
      <input id="file" name="file" type="file" accept="image/*" multiple/>
      <label class="filebtn secondary" for="camera">Take photo</label>
      <input id="camera" type="file" accept="image/*" capture="environment"/>
    </div>
    <p class="hint">Library supports multiple. Camera adds one shot at a time — tap Upload after each, or pick several from the library.</p>
    <button type="submit" id="go">Upload</button>
  </form>
  <div id="status"></div>
<script>
const tagSel = document.getElementById('tag');
tagSel.value = "__TAG__";
const notesEl = document.getElementById('notes');
const status = document.getElementById('status');
const fileInput = document.getElementById('file');
const cameraInput = document.getElementById('camera');

function mergeCameraShot() {
  const shot = cameraInput.files && cameraInput.files[0];
  if (!shot) return;
  const dt = new DataTransfer();
  for (const f of fileInput.files) dt.items.add(f);
  dt.items.add(shot);
  fileInput.files = dt.files;
  cameraInput.value = '';
  status.innerHTML = `<div class="meta">${fileInput.files.length} photo(s) selected — tap Upload when ready.</div>`;
}
cameraInput.addEventListener('change', mergeCameraShot);
fileInput.addEventListener('change', () => {
  const n = fileInput.files.length;
  status.innerHTML = n
    ? `<div class="meta">${n} photo(s) selected — tap Upload when ready.</div>`
    : '';
});

document.getElementById('f').addEventListener('submit', async (e) => {
  e.preventDefault();
  mergeCameraShot();
  const files = fileInput.files;
  if (!files.length) {
    status.innerHTML = '<div class="err">Pick or take a photo first.</div>';
    return;
  }
  const btn = document.getElementById('go');
  btn.disabled = true;
  status.innerHTML = '';
  const notes = notesEl.value.trim();
  let ok = 0, fail = 0;
  for (const file of files) {
    const fd = new FormData();
    fd.append('file', file, file.name);
    fd.append('tag', tagSel.value);
    fd.append('notes', notes);
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
  fileInput.value = '';
});
</script>
</body>
</html>
"""

SHORTCUT_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1"/>
<title>Car-RO · iPhone Shortcut</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: system-ui, sans-serif; margin: 0; padding: 1.25rem; max-width: 36rem; line-height: 1.45; }
  h1 { font-size: 1.25rem; margin: 0 0 .5rem; }
  h2 { font-size: 1.05rem; margin: 1.25rem 0 .4rem; }
  .meta { color: #888; font-size: .9rem; margin-bottom: 1rem; }
  code, .url {
    display: block; word-break: break-all; font-family: ui-monospace, monospace;
    font-size: .85rem; padding: .75rem; border-radius: .5rem;
    border: 1px solid #555; background: rgba(127,127,127,.12); margin: .5rem 0 1rem;
  }
  ol { padding-left: 1.2rem; }
  li { margin: .45rem 0; }
  a { color: #0a7; }
  .box { border: 1px solid #555; border-radius: .5rem; padding: .75rem 1rem; margin: 1rem 0; }
  .tip { font-size: .9rem; color: #888; margin: .25rem 0 .75rem; }
</style>
</head>
<body>
  <h1>iPhone Shortcuts → Car-RO</h1>
  <div class="meta">
    RO <strong>__RO_ID__</strong> · default tag <strong>__TAG__</strong><br/>
    Expires in about __TTL__ · Tailscale must be on
  </div>

  <div class="box">
    <strong>Upload URL</strong> — paste this into <em>Get Contents of URL</em>
    <div class="url" id="url">__UPLOAD_URL__</div>
  </div>

  <h2>Build the Shortcut</h2>
  <p class="tip">On current iOS you do <strong>not</strong> name it first. Tap <strong>+</strong>, then <strong>Add Action</strong>, and search for the action. Rename at the end.</p>
  <ol>
    <li>Open <strong>Shortcuts</strong> → tap <strong>+</strong>.</li>
    <li>Tap <strong>Add Action</strong>.</li>
    <li>Search for <strong>Get Contents of URL</strong> and add it (category <em>Web</em>).</li>
    <li>Configure that action:
      <ul>
        <li><strong>URL</strong> → paste the upload URL from the box above</li>
        <li>Tap <strong>Show More</strong> if you only see the URL field</li>
        <li><strong>Method</strong> → <strong>POST</strong></li>
        <li><strong>Request Body</strong> → <strong>Form</strong></li>
      </ul>
    </li>
    <li>Under Form, tap <strong>Add new field</strong> three times:
      <ul>
        <li><code>file</code> → field type <strong>File</strong> (not Text). Value comes later (Shortcut Input).</li>
        <li><code>tag</code> → <strong>Text</strong> → type <code>__TAG__</code></li>
        <li><code>notes</code> → <strong>Text</strong> → leave blank, or tap and choose <em>Ask Each Time</em></li>
      </ul>
    </li>
    <li>Tap the title at the <strong>top</strong> of the screen (or the ⓘ / dropdown) to open shortcut details.</li>
    <li>Enable <strong>Show in Share Sheet</strong>. Allow <strong>Images</strong> / Photos when asked. Done/Save.</li>
    <li>Back in the shortcut: Form field <code>file</code> → set value to <strong>Shortcut Input</strong>
        (the shared photo). If you only see text options, make sure the field type is <strong>File</strong>.</li>
    <li>In details again, rename to <strong>Car-RO Upload</strong>.</li>
  </ol>

  <h2>Several photos in one share</h2>
  <ol>
    <li>Add action <strong>Repeat with Each</strong> (search “Repeat”).</li>
    <li>Drag <strong>Get Contents of URL</strong> <em>inside</em> the loop.</li>
    <li>Set Form <code>file</code> to <strong>Repeat Item</strong> instead of Shortcut Input.</li>
  </ol>

  <h2>Use it</h2>
  <ol>
    <li>Laptop: <code>carro photo shortcut --id __RO_ID__</code> when you start the job.</li>
    <li>Phone: Photos → select → <strong>Share</strong> → <strong>Car-RO Upload</strong>.</li>
    <li>Laptop: press Enter to refresh the RO.</li>
  </ol>

  <p class="meta">Prefer the web form? <a href="/u/__TOKEN__">Open Safari upload page</a>.</p>
</body>
</html>
"""
