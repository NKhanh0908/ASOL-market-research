/* Manual Dashboard flow. Loading this asset never starts an AI request. */
(() => {
  "use strict";
  const create = document.getElementById("ai-create");
  const dialog = document.getElementById("ai-confirm");
  if (!create || !dialog || create.disabled) return;
  const element = id => document.getElementById(id);
  const submit = element("ai-submit");
  const consent = element("ai-unknown");
  const warning = element("ai-warning");
  const feedback = element("ai-feedback");
  const history = element("ai-inspect-history");
  let quote = null;
  let busy = false;
  let generation = 0;
  let needsConsent = true;

  function updateControls() {
    create.disabled = busy;
    submit.disabled = busy || !quote || (needsConsent && !consent.checked);
    consent.disabled = busy || !quote;
  }

  async function post(url, payload) {
    const response = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": create.dataset.csrf },
      body: JSON.stringify(payload)
    });
    const data = await response.json();
    if (!response.ok) {
      const detail = typeof data.detail === "string" ? data.detail : "Không thể xử lý yêu cầu.";
      throw new Error(detail);
    }
    return data;
  }

  function visitRun(data) {
    if (typeof data.run_id !== "string" || !data.run_id) throw new Error("Không nhận được mã lượt chạy. Kiểm tra lịch sử gợi ý AI.");
    window.location.assign("/recommendations/" + encodeURIComponent(data.run_id));
  }

  function showQuote(data) {
    if (data.state !== "ready" || typeof data.quote !== "string" || !data.quote ||
        !data.scope || !Array.isArray(data.scope.markets) || !data.scope.markets.length ||
        typeof data.provider_id !== "string" || !data.provider_id || typeof data.model_id !== "string" || !data.model_id ||
        !Number.isInteger(data.max_output_tokens) || data.max_output_tokens < 1 ||
        (data.cost_mode === "free_tier" && data.max_output_tokens > 2000) ||
        !Number.isFinite(data.timeout_seconds) || data.timeout_seconds <= 0 ||
        !["free_tier", "metered"].includes(data.cost_mode) ||
        (data.cost_mode === "metered" && (!Number.isFinite(Number(data.max_cost_per_run_usd)) || Number(data.max_cost_per_run_usd) <= 0)) ||
        (data.cost_mode === "free_tier" && (data.free_tier_confirmed !== true ||
          !Number.isInteger(data.attempts_remaining) || data.attempts_remaining < 1))) {
      throw new Error("Không nhận được xác nhận hợp lệ. Hãy mở lại phạm vi để kiểm tra.");
    }
    quote = data.quote;
    needsConsent = true;
    element("ai-scope").textContent = `${data.scope.analysis_date} · ${data.scope.markets.join(", ").toUpperCase()}`;
    element("ai-provider").textContent = `${data.provider_id} / ${data.model_id}`;
    element("ai-limits").textContent = `${data.max_output_tokens ?? "Chưa xác định"} token đầu ra tối đa · ${data.timeout_seconds ?? "Chưa xác định"} giây`;
    const mode = data.cost_mode === "free_tier"
      ? (data.free_tier_confirmed ? "Free Tier (chủ tài khoản xác nhận; chưa được API kiểm chứng)" : "Free Tier chưa được chủ tài khoản xác nhận")
      : `Giới hạn ${data.max_cost_per_run_usd ?? "chưa xác định"} USD / lượt`;
    const estimate = data.estimated_cost_usd == null ? "chưa xác định" : `${data.estimated_cost_usd} USD`;
    element("ai-cost").textContent = `${mode}. Ước tính: ${estimate}. Chi phí thực tế: chưa xác định; không bảo đảm bằng 0.`;
    element("ai-attempts").textContent = data.attempts_remaining == null ? "Chưa xác định" : String(data.attempts_remaining);
    element("ai-unknown-label").hidden = !needsConsent;
    for (const text of (Array.isArray(data.warnings) ? data.warnings : [])) {
      const item = document.createElement("li");
      item.textContent = String(text);
      element("ai-coverage").append(item);
    }
    warning.textContent = "Kiểm tra phạm vi và giới hạn trước khi tạo gợi ý.";
  }

  create.addEventListener("click", async () => {
    if (busy) return;
    const current = ++generation;
    quote = null;
    consent.checked = false;
    needsConsent = true;
    history.hidden = true;
    feedback.textContent = "";
    element("ai-coverage").replaceChildren();
    for (const id of ["ai-scope", "ai-provider", "ai-limits", "ai-cost", "ai-attempts"]) element(id).textContent = "";
    element("ai-unknown-label").hidden = true;
    warning.textContent = "Đang kiểm tra phạm vi và giới hạn…";
    busy = true;
    updateControls();
    dialog.showModal();
    try {
      const data = await post("/api/recommendations/preflight", { analysis_date: create.dataset.date, market: create.dataset.market });
      if (generation !== current || !dialog.open) return;
      if (data.state === "blocked") visitRun(data);
      else showQuote(data);
    } catch (error) {
      if (generation === current && dialog.open) {
        warning.textContent = `${error.message} Yêu cầu không được tự gửi lại. Kiểm tra lịch sử trước khi mở lượt mới.`;
        history.hidden = false;
      }
    } finally {
      busy = false;
      updateControls();
      if (!dialog.open) create.focus();
    }
  });

  consent.addEventListener("change", updateControls);
  submit.addEventListener("click", async () => {
    if (busy || !quote || (needsConsent && !consent.checked)) return;
    busy = true;
    const current = generation;
    const signedQuote = quote;
    quote = null;
    updateControls();
    warning.textContent = "Đang gửi lượt mới…";
    try {
      const data = await post("/api/recommendations/runs", { quote: signedQuote, confirm_unknown: consent.checked });
      if (generation === current && dialog.open) visitRun(data);
      else feedback.textContent = "Yêu cầu đã được gửi. Kiểm tra lịch sử gợi ý AI để xem lượt chạy.";
    } catch (error) {
      const message = `${error.message} Yêu cầu có thể đã được nhận; kiểm tra lịch sử gợi ý AI trước khi tạo lượt mới. Không tự gửi lại.`;
      feedback.textContent = message;
      if (dialog.open) { warning.textContent = message; history.hidden = false; }
    } finally {
      busy = false;
      updateControls();
      if (!dialog.open) create.focus();
    }
  });

  element("ai-cancel").addEventListener("click", () => dialog.close());
  dialog.addEventListener("cancel", () => {
    // Native Escape closes the dialog; close performs the shared cleanup.
    if (busy) feedback.textContent = "Yêu cầu đang xử lý. Kiểm tra lịch sử gợi ý AI trước khi tạo lượt mới.";
  });
  dialog.addEventListener("close", () => {
    ++generation;
    quote = null;
    consent.checked = false;
    if (busy) feedback.textContent = "Yêu cầu đang xử lý. Kiểm tra lịch sử gợi ý AI trước khi tạo lượt mới.";
    updateControls();
    create.focus();
  });
})();
