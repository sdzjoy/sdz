(() => {
  "use strict";

  const script = document.currentScript;
  const previewUrl = script?.dataset.editorialMathPreviewUrl;

  const ready = (callback) => {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", callback, { once: true });
    } else {
      callback();
    }
  };

  ready(() => {
    const form = document.querySelector("#page-edit-form");
    const isArticleEditor = Boolean(
      form && document.querySelector("#id_cover_image") && document.querySelector("#id_body")
    );
    if (!isArticleEditor) return;

    document.body.classList.add("editorial-article-editor");

    const status = document.createElement("div");
    status.className = "editorial-save-status";
    status.dataset.state = "saved";
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    status.textContent = "已载入最新保存版本";
    form.prepend(status);

    const setStatus = (state, label) => {
      status.dataset.state = state;
      status.textContent = label;
    };

    if (form.querySelector('[aria-invalid="true"], .w-field--error, .error-message')) {
      setStatus("error", "保存失败，请检查标红字段");
    } else if (document.querySelector(".messages li.success")) {
      setStatus("saved", "保存成功，已载入最新版本");
    }

    let changed = false;
    const markChanged = (event) => {
      if (event.target.closest(".editorial-equation-preview")) return;
      if (!changed) {
        changed = true;
        setStatus("dirty", "有未保存修改");
      }
    };
    form.addEventListener("input", markChanged);
    form.addEventListener("change", markChanged);
    form.addEventListener("submit", () => setStatus("saving", "正在保存…"));
    document.addEventListener("w-unsaved:add", () => setStatus("dirty", "有未保存修改"));
    document.addEventListener("w-unsaved:clear", () => {
      changed = false;
      setStatus("saved", "已保存");
    });

    if (!previewUrl) return;
    const csrfToken = form.querySelector('[name="csrfmiddlewaretoken"]')?.value || "";

    const bindEquationPreview = (block) => {
      if (block.dataset.editorialPreviewBound === "true") return;
      const input = block.querySelector('textarea[name$="-latex"]');
      if (!input) return;
      block.dataset.editorialPreviewBound = "true";

      const preview = document.createElement("div");
      preview.className = "editorial-equation-preview";
      preview.innerHTML = '<span class="editorial-equation-preview__label">公式预览</span><span>输入 LaTeX 后将在这里预览。</span>';
      (input.closest(".w-field__wrapper") || input.parentElement).append(preview);

      let timer;
      let controller;
      const updatePreview = () => {
        window.clearTimeout(timer);
        const source = input.value.trim();
        if (!source) {
          preview.innerHTML = '<span class="editorial-equation-preview__label">公式预览</span><span>输入 LaTeX 后将在这里预览。</span>';
          return;
        }
        preview.innerHTML = '<span class="editorial-equation-preview__label">公式预览</span><span>正在生成预览…</span>';
        timer = window.setTimeout(async () => {
          controller?.abort();
          controller = new AbortController();
          try {
            const response = await fetch(previewUrl, {
              method: "POST",
              credentials: "same-origin",
              headers: {
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "X-CSRFToken": csrfToken,
              },
              body: new URLSearchParams({ latex: source }),
              signal: controller.signal,
            });
            const payload = await response.json();
            preview.innerHTML = '<span class="editorial-equation-preview__label">公式预览</span>' + payload.html;
            preview.dataset.state = payload.ok ? "ready" : "error";
          } catch (error) {
            if (error.name === "AbortError") return;
            preview.dataset.state = "error";
            preview.innerHTML = '<span class="editorial-equation-preview__label">公式预览</span><span class="equation-error">预览服务暂时不可用；LaTeX 源码仍会正常保存。</span>';
          }
        }, 350);
      };

      input.addEventListener("input", updatePreview);
      if (input.value.trim()) updatePreview();
    };

    const scan = (root = document) => {
      root.querySelectorAll?.(".editorial-equation-block").forEach(bindEquationPreview);
    };
    scan();
    new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        mutation.addedNodes.forEach((node) => {
          if (node.nodeType === Node.ELEMENT_NODE) scan(node);
        });
      });
    }).observe(form, { childList: true, subtree: true });
  });
})();
