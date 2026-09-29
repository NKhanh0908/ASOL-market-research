(() => {
  "use strict";
  const status = document.getElementById("ai-run-status");
  if (!status || !["queued", "running"].includes(status.dataset.status)) return;
  const warning = document.getElementById("ai-poll-warning");
  const refresh = document.getElementById("ai-refresh");
  let stopped = false;
  let timer;
  let reloaded = false;
  const controller = new AbortController();
  const stop = () => { stopped = true; clearTimeout(timer); controller.abort(); };
  window.addEventListener("pagehide", stop, { once: true });
  window.addEventListener("beforeunload", stop, { once: true });
  refresh.addEventListener("click", () => window.location.reload());
  const poll = async () => {
    if (stopped) return;
    try {
      const response = await fetch(`/api/recommendations/${encodeURIComponent(status.dataset.runId)}`, {
        method: "GET", cache: "no-store", signal: controller.signal, headers: { "Accept": "application/json" }
      });
      if (!response.ok) throw new Error("status-unavailable");
      const run = await response.json();
      if (stopped) return;
      if (!["queued", "running", "succeeded", "partial", "failed", "blocked"].includes(run.status)) throw new Error("invalid-status");
      status.textContent = `Trạng thái: ${run.status}`;
      if (!["queued", "running"].includes(run.status)) {
        stop();
        if (!reloaded) { reloaded = true; window.location.reload(); }
        return;
      }
      timer = window.setTimeout(poll, 2000);
    } catch (error) {
      if (stopped) return;
      stop();
      warning.textContent = "Không thể cập nhật trạng thái. Làm mới trang để kiểm tra lượt đã lưu.";
      warning.hidden = false;
      refresh.hidden = false;
    }
  };
  timer = window.setTimeout(poll, 2000);
})();
