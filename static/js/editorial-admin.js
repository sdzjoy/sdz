(() => {
  "use strict";

  const script = document.currentScript;
  const previewUrl = script?.dataset.editorialMathPreviewUrl;
  const ALLOWED_PASTE_TAGS = new Set([
    "A",
    "BLOCKQUOTE",
    "BR",
    "CODE",
    "EM",
    "H2",
    "H3",
    "H4",
    "HR",
    "LI",
    "OL",
    "P",
    "S",
    "STRONG",
    "SUB",
    "SUP",
    "TABLE",
    "TBODY",
    "TD",
    "TFOOT",
    "TH",
    "THEAD",
    "TR",
    "UL",
  ]);
  const DROP_PASTE_TAGS = new Set([
    "AUDIO",
    "BUTTON",
    "CANVAS",
    "FORM",
    "IFRAME",
    "INPUT",
    "LINK",
    "META",
    "NOSCRIPT",
    "OBJECT",
    "OPTION",
    "PICTURE",
    "SCRIPT",
    "SELECT",
    "SOURCE",
    "STYLE",
    "SVG",
    "TEXTAREA",
    "VIDEO",
  ]);
  const BLOCK_PASTE_TAGS = new Set([
    "BLOCKQUOTE",
    "H2",
    "H3",
    "H4",
    "HR",
    "LI",
    "OL",
    "P",
    "TABLE",
    "UL",
  ]);

  const safePasteLink = (value) => {
    const href = (value || "").trim();
    const lowered = href.toLowerCase().replace(/[\u0000-\u0020]+/g, "");
    if (!href || lowered.startsWith("javascript:") || lowered.startsWith("data:")) {
      return "";
    }
    if (/^(#|\/|\.\/|\.\.\/)/.test(href)) return href;
    try {
      const url = new URL(href, window.location.origin);
      return ["http:", "https:", "mailto:", "tel:"].includes(url.protocol) ? href : "";
    } catch (_error) {
      return "";
    }
  };

  const replacePasteTag = (element, tagName) => {
    const replacement = element.ownerDocument.createElement(tagName);
    while (element.firstChild) replacement.append(element.firstChild);
    element.replaceWith(replacement);
    return replacement;
  };

  const unwrapPasteElement = (element) => {
    const fragment = element.ownerDocument.createDocumentFragment();
    while (element.firstChild) fragment.append(element.firstChild);
    element.replaceWith(fragment);
  };

  const sanitizePastedHtml = (source, plainText = "") => {
    const parsed = new DOMParser().parseFromString(source || "", "text/html");
    const result = {
      html: "",
      text: plainText,
      changed: false,
      hadExternalImages: false,
      hadTables: false,
    };

    const comments = parsed.createTreeWalker(parsed.body, NodeFilter.SHOW_COMMENT);
    const commentsToRemove = [];
    while (comments.nextNode()) commentsToRemove.push(comments.currentNode);
    commentsToRemove.forEach((comment) => comment.remove());

    [...parsed.body.querySelectorAll("*")].forEach((originalElement) => {
      if (!originalElement.isConnected) return;
      let element = originalElement;
      const originalTag = element.tagName.toUpperCase();
      const style = (element.getAttribute("style") || "").toLowerCase();
      const isHidden =
        element.hasAttribute("hidden") ||
        element.getAttribute("aria-hidden") === "true" ||
        /(?:display\s*:\s*none|visibility\s*:\s*hidden|mso-hide\s*:\s*all)/.test(style);

      if (isHidden || DROP_PASTE_TAGS.has(originalTag)) {
        element.remove();
        result.changed = true;
        return;
      }
      if (originalTag === "IMG") {
        result.hadExternalImages = true;
        result.changed = true;
        element.remove();
        return;
      }

      const mappedTag =
        originalTag === "H1"
          ? "H2"
          : ["H5", "H6"].includes(originalTag)
            ? "H4"
            : originalTag === "B"
              ? "STRONG"
              : originalTag === "I"
                ? "EM"
                : ["STRIKE", "DEL"].includes(originalTag)
                  ? "S"
                  : originalTag;
      if (mappedTag !== originalTag) {
        element = replacePasteTag(element, mappedTag.toLowerCase());
        result.changed = true;
      }

      if (!ALLOWED_PASTE_TAGS.has(mappedTag)) {
        const hasBlockChildren = [...element.children].some((child) =>
          BLOCK_PASTE_TAGS.has(child.tagName.toUpperCase())
        );
        if (["DIV", "ARTICLE", "SECTION", "MAIN", "HEADER", "FOOTER"].includes(mappedTag) && !hasBlockChildren) {
          element = replacePasteTag(element, "p");
        } else {
          unwrapPasteElement(element);
        }
        result.changed = true;
        return;
      }

      const href = mappedTag === "A" ? safePasteLink(element.getAttribute("href")) : "";
      const title = mappedTag === "A" ? (element.getAttribute("title") || "").trim() : "";
      const colSpan = ["TD", "TH"].includes(mappedTag) ? element.getAttribute("colspan") : "";
      const rowSpan = ["TD", "TH"].includes(mappedTag) ? element.getAttribute("rowspan") : "";
      if (element.attributes.length) result.changed = true;
      [...element.attributes].forEach((attribute) => element.removeAttribute(attribute.name));
      if (href) element.setAttribute("href", href);
      else if (mappedTag === "A") {
        unwrapPasteElement(element);
        result.changed = true;
        return;
      }
      if (title) element.setAttribute("title", title.slice(0, 240));
      if (/^\d{1,2}$/.test(colSpan || "") && Number(colSpan) > 1) {
        element.setAttribute("colspan", String(Math.min(Number(colSpan), 20)));
      }
      if (/^\d{1,2}$/.test(rowSpan || "") && Number(rowSpan) > 1) {
        element.setAttribute("rowspan", String(Math.min(Number(rowSpan), 20)));
      }
    });

    [...parsed.body.querySelectorAll("table")].forEach((table) => {
      const rows = [...table.querySelectorAll("tr")]
        .map((row) => ({
          cells: [...row.querySelectorAll(":scope > th, :scope > td")]
            .map((cell) => cell.textContent.replace(/\u00a0/g, " ").replace(/\s+/g, " ").trim())
            .filter(Boolean),
          isHeading: Boolean(row.querySelector(":scope > th")),
        }))
        .filter((row) => row.cells.length);
      if (!rows.length) {
        table.remove();
        result.changed = true;
        return;
      }

      const replacement = parsed.createElement("blockquote");
      rows.forEach((row) => {
        const paragraph = parsed.createElement("p");
        const content = row.isHeading ? parsed.createElement("strong") : paragraph;
        content.textContent = row.cells.join(" ｜ ");
        if (row.isHeading) paragraph.append(content);
        replacement.append(paragraph);
      });
      table.replaceWith(replacement);
      result.hadTables = true;
      result.changed = true;
    });

    [...parsed.body.querySelectorAll("p, h2, h3, h4, blockquote, li")]
      .reverse()
      .forEach((element) => {
        const meaningfulText = element.textContent.replace(/\u00a0/g, " ").trim();
        if (!meaningfulText && !element.querySelector("br, table")) {
          element.remove();
          result.changed = true;
        }
      });

    result.html = parsed.body.innerHTML.trim();
    if (!result.text) result.text = parsed.body.textContent.replace(/\u00a0/g, " ").trim();
    result.changed = result.changed || result.html !== (source || "").trim();
    return result;
  };

  window.SDZEditorialPaste = Object.freeze({ sanitizePastedHtml });

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
      form &&
        form.querySelector('[data-contentpath="cover_image"]') &&
        form.querySelector('[data-contentpath="body"]')
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

    const pasteNotice = document.createElement("div");
    pasteNotice.className = "editorial-paste-notice";
    pasteNotice.setAttribute("role", "status");
    pasteNotice.setAttribute("aria-live", "polite");
    pasteNotice.hidden = true;
    status.insertAdjacentElement("afterend", pasteNotice);

    let pasteNoticeTimer;
    const notifyPaste = (message, state = "cleaned") => {
      window.clearTimeout(pasteNoticeTimer);
      pasteNotice.dataset.state = state;
      pasteNotice.textContent = message;
      pasteNotice.hidden = false;
      pasteNoticeTimer = window.setTimeout(() => {
        pasteNotice.hidden = true;
      }, 9000);
    };

    let replayingPaste = false;
    const replayPaste = (target, sanitized) => {
      try {
        const transfer = new DataTransfer();
        if (sanitized.html) transfer.setData("text/html", sanitized.html);
        transfer.setData("text/plain", sanitized.text || "");
        const replayedEvent = new ClipboardEvent("paste", {
          bubbles: true,
          cancelable: true,
          clipboardData: transfer,
        });
        replayingPaste = true;
        target.dispatchEvent(replayedEvent);
        return replayedEvent.defaultPrevented;
      } catch (_error) {
        return false;
      } finally {
        replayingPaste = false;
      }
    };

    form.addEventListener(
      "paste",
      (event) => {
        if (replayingPaste) return;
        const editor = event.target.closest(
          '.DraftEditor-root [contenteditable="true"], [data-draftail-input] [contenteditable="true"]'
        );
        if (!editor || !event.clipboardData) return;
        const html = event.clipboardData.getData("text/html");
        if (!html) return;

        let sanitized;
        try {
          sanitized = sanitizePastedHtml(html, event.clipboardData.getData("text/plain"));
        } catch (_error) {
          return;
        }
        if (!sanitized.html && !sanitized.text) return;

        event.preventDefault();
        event.stopImmediatePropagation();
        const handledByEditor = replayPaste(editor, sanitized);
        if (!handledByEditor) {
          editor.focus();
          const command = sanitized.html ? "insertHTML" : "insertText";
          document.execCommand(command, false, sanitized.html || sanitized.text);
        }

        changed = true;
        setStatus("dirty", "有未保存修改");
        window.setTimeout(() => {
          editor.dispatchEvent(new Event("input", { bubbles: true }));
          changed = true;
          setStatus("dirty", "有未保存修改");
        }, 0);

        if (sanitized.hadExternalImages || sanitized.hadTables) {
          const details = [];
          if (sanitized.hadExternalImages) {
            details.push("外部图片未粘贴，请使用图片与图注块重新上传");
          }
          if (sanitized.hadTables) {
            details.push("表格内容已保留为可编辑行；正式表格请使用数据表格块");
          }
          notifyPaste(`已清理来源格式；${details.join("；")}。`, sanitized.hadExternalImages ? "warning" : "cleaned");
        } else if (sanitized.changed) {
          notifyPaste("已清理 Word、网页或微信格式，只保留安全的正文结构。", "cleaned");
        }
      },
      true
    );

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
