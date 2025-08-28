const $ = (id) => document.getElementById(id);
const statusBox = $("status");
const actionsBox = $("actions");

let pollTimer = null;
let baseURL = window.location.origin;

function log(msg) {
  statusBox.textContent = msg;
}

function setActions(html) {
  actionsBox.innerHTML = html;
}

function resetUI() {
  log("Idle");
  setActions("");
  if (pollTimer) clearInterval(pollTimer);
}

$("reset").addEventListener("click", resetUI);

$("run").addEventListener("click", async () => {
  const fileInput = $("file");
  if (!fileInput.files.length) {
    alert("Please choose a file (.geojson or .kmz)."); return;
  }
  const form = new FormData();
  form.append("file", fileInput.files[0]);
  const sy = $("start_year").value;
  const ey = $("end_year").value;
  const k = $("k").value;
  if (sy) form.append("start_year", sy);
  if (ey) form.append("end_year", ey);
  form.append("k", k);

  log("Uploading & starting…");
  setActions("");

  try {
    const resp = await fetch(`${baseURL}/start`, { method: "POST", body: form });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${resp.status}`);
    }
    const data = await resp.json();
    const jobId = data.job_id;
    log(`Queued: ${jobId}`);

    // Poll status
    pollTimer = setInterval(async () => {
      try {
        const r = await fetch(`${baseURL}/status?job_id=${encodeURIComponent(jobId)}`);
        const s = await r.json();
        log(`${s.state} — ${s.message}`);
        if (s.state === "SUCCEEDED") {
          clearInterval(pollTimer);
          setActions(`<a class="button primary" href="${baseURL}/download-zip?job_id=${encodeURIComponent(jobId)}">Download ZIP</a>`);
        } else if (s.state === "FAILED") {
          clearInterval(pollTimer);
          setActions(`<span style="color:#b91c1c;">Job failed</span>`);
        }
      } catch (e) {
        // keep polling
      }
    }, 3000);
  } catch (e) {
    log(`Error: ${e.message}`);
  }
});
