import { Editor } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import { Markdown } from "@tiptap/markdown";
import { attachDictation, detachDictation, stopDictation } from "./dictation.js";

var CMD_ACTIVE = {
  toggleBold: "bold",
  toggleItalic: "italic",
  toggleBulletList: "bulletList",
  toggleOrderedList: "orderedList",
  toggleCodeBlock: "codeBlock",
  toggleBlockquote: "blockquote",
  setLink: "link",
};

function parseHttpUrl(url, defaultProtocol) {
  try {
    var raw = String(url || "").trim();
    if (!raw) return null;
    if (!/^[a-z][a-z0-9+.-]*:/i.test(raw)) raw = (defaultProtocol || "https") + "://" + raw;
    var parsed = new URL(raw);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return null;
    return parsed.href;
  } catch (_e) {
    return null;
  }
}

function closeLinkPop(root) {
  var pop = root && root.querySelector("[data-rich-link-pop]");
  if (!pop) return;
  pop.hidden = true;
  if (root._richLinkDoc) {
    document.removeEventListener("mousedown", root._richLinkDoc, true);
    document.removeEventListener("keydown", root._richLinkDoc, true);
    root._richLinkDoc = null;
  }
}

function openLinkPop(root, editor) {
  var pop = root.querySelector("[data-rich-link-pop]");
  var input = root.querySelector("[data-rich-link-input]");
  if (!pop || !input) return;
  closeLinkPop(root);
  input.value = editor.getAttributes("link").href || "";
  pop.hidden = false;
  root._richLinkDoc = function (ev) {
    if (ev.type === "keydown") {
      if (ev.key !== "Escape") return;
      ev.preventDefault();
    } else if (pop.contains(ev.target) || (ev.target.closest && ev.target.closest('[data-rich-cmd="setLink"]'))) {
      return;
    }
    closeLinkPop(root);
    editor.chain().focus().run();
  };
  document.addEventListener("mousedown", root._richLinkDoc, true);
  document.addEventListener("keydown", root._richLinkDoc, true);
  setTimeout(function () {
    input.focus();
    input.select();
  }, 0);
}

function commitLinkPop(root, editor) {
  var input = root.querySelector("[data-rich-link-input]");
  var href = parseHttpUrl(input && input.value, "https");
  closeLinkPop(root);
  var chain = editor.chain().focus().extendMarkRange("link");
  if (href) chain.setLink({ href: href }).run();
  else chain.unsetLink().run();
}

function applyLinkCommand(root, editor) {
  var pop = root.querySelector("[data-rich-link-pop]");
  if (pop && !pop.hidden) {
    closeLinkPop(root);
    editor.chain().focus().run();
    return;
  }
  openLinkPop(root, editor);
}

function i18n(key, vars) {
  var dict = window.__i18n || {};
  var msg = dict[key] || "";
  if (!vars) return msg;
  return String(msg).replace(/\{(\w+)\}/g, function (_, name) {
    return vars[name] != null ? String(vars[name]) : "";
  });
}

function syncMarkdown(editor, input) {
  if (!input) return;
  input.value = trimMarkdownEdges(editor.getMarkdown() || "");
}

function trimMarkdownEdges(md) {
  var lines = String(md || "")
    .replace(/\r\n?/g, "\n")
    .split("\n");
  var blank = /^(?:&nbsp;|\u00a0|\s)*$/;
  while (lines.length && blank.test(lines[0])) lines.shift();
  while (lines.length && blank.test(lines[lines.length - 1])) lines.pop();
  return lines.join("\n").replace(/^\s+|\s+$/g, "");
}

function updateToolbar(root, editor) {
  root.querySelectorAll("[data-rich-cmd]").forEach(function (btn) {
    var mark = CMD_ACTIVE[btn.getAttribute("data-rich-cmd")];
    var active = !!(mark && editor.isActive(mark));
    btn.classList.toggle("is-active", active);
    btn.setAttribute("aria-pressed", active ? "true" : "false");
  });
}

function maxLenFromInput(input) {
  if (!input) return null;
  var n = parseInt(input.getAttribute("maxlength") || "", 10);
  return Number.isFinite(n) && n > 0 ? n : null;
}

function measureContent(editor, input) {
  syncMarkdown(editor, input);
  var text = (editor.getText() || "").replace(/\u00a0/g, " ").trim();
  var mdLen = (input && input.value ? input.value : "").length;
  return { text: text, used: Math.max(text.length, mdLen) };
}

function formatCharCount(used, max) {
  return used.toLocaleString() + " / " + max.toLocaleString();
}

function updateCharMeter(root, editor, input, measured) {
  var meter = root.querySelector("[data-rich-meter]");
  if (!meter) return;
  var maxLen = maxLenFromInput(input);
  if (maxLen == null) {
    meter.hidden = true;
    return;
  }
  var used = (measured || measureContent(editor, input)).used;
  var pct = maxLen > 0 ? (used / maxLen) * 100 : 0;
  var warn = used >= maxLen * 0.9 && used <= maxLen;
  var over = used > maxLen;
  var fill = meter.querySelector("[data-rich-meter-fill]");
  var track = meter.querySelector("[data-rich-meter-track]");
  var label = meter.querySelector("[data-rich-meter-label]");
  if (fill) fill.style.width = Math.min(100, pct) + "%";
  meter.hidden = false;
  meter.classList.toggle("is-warn", warn);
  meter.classList.toggle("is-over", over);
  if (track) {
    track.setAttribute("aria-valuenow", String(used));
    track.setAttribute("aria-valuemax", String(maxLen));
    track.setAttribute("aria-valuetext", i18n("editor.char_count", { used: used, max: maxLen }) || formatCharCount(used, maxLen));
  }
  if (label) label.textContent = formatCharCount(used, maxLen);
}

function maybeClearRichFieldError(editor, input, measured) {
  if (!input || input.getAttribute("aria-invalid") !== "true") return;
  var state = measured || measureContent(editor, input);
  if (!state.text) return;
  var maxLen = maxLenFromInput(input);
  if (maxLen != null && state.used > maxLen) return;
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

function inClosedDialog(root) {
  var dlg = root && root.closest ? root.closest("dialog") : null;
  return !!(dlg && !dlg.open);
}

function quoteTextFromSelection(root) {
  var sel = window.getSelection();
  if (!sel || sel.isCollapsed) return "";
  var node = sel.anchorNode;
  var el = node && (node.nodeType === 1 ? node : node.parentElement);
  if (!el || !el.closest(".rich-content") || root.contains(el)) return "";
  return String(sel.toString() || "")
    .replace(/\u00a0/g, " ")
    .trim();
}

function insertQuotedText(editor, text) {
  var content = String(text || "")
    .split(/\r\n|\n|\r/)
    .map(function (line) {
      return line ? { type: "paragraph", content: [{ type: "text", text: line }] } : { type: "paragraph" };
    });
  editor
    .chain()
    .focus()
    .insertContent([{ type: "blockquote", content: content }, { type: "paragraph" }])
    .run();
}

function initEditor(root) {
  if (!root || root._richEditor) return;
  if (inClosedDialog(root)) return;
  var surface = root.querySelector("[data-rich-surface]");
  var input = root.querySelector("[data-rich-input]");
  if (!surface || !input) return;

  var initial = input.defaultValue || "";
  var placeholder = root.getAttribute("data-placeholder") || "";
  var attrs = { class: "rich-editor-prose" };
  if (placeholder) attrs["data-placeholder"] = placeholder;

  var editor = new Editor({
    element: surface,
    extensions: [
      StarterKit.configure({
        heading: false,
        horizontalRule: false,
        strike: false,
        dropcursor: false,
        gapcursor: false,
        underline: false,
        link: {
          autolink: true,
          linkOnPaste: true,
          openOnClick: false,
          defaultProtocol: "https",
          HTMLAttributes: {
            target: "_blank",
            rel: "noopener noreferrer",
          },
          isAllowedUri: function (url, ctx) {
            return !!parseHttpUrl(url, ctx.defaultProtocol);
          },
        },
      }),
      Markdown.configure({
        indentation: { style: "space", size: 4 },
      }),
    ],
    content: initial,
    contentType: "markdown",
    editorProps: {
      attributes: attrs,
      handleDOMEvents: {
        paste: function () {
          stopDictation(root);
          return false;
        },
      },
    },
    onCreate: function ({ editor: ed }) {
      var measured = measureContent(ed, input);
      updateToolbar(root, ed);
      updateCharMeter(root, ed, input, measured);
    },
    onUpdate: function ({ editor: ed }) {
      var measured = measureContent(ed, input);
      updateToolbar(root, ed);
      updateCharMeter(root, ed, input, measured);
      maybeClearRichFieldError(ed, input, measured);
    },
    onSelectionUpdate: function ({ editor: ed }) {
      updateToolbar(root, ed);
    },
  });

  attachDictation(root, editor);

  var pendingQuote = "";
  var quoteBtn = root.querySelector('[data-rich-cmd="toggleBlockquote"]');
  if (quoteBtn) {
    quoteBtn.addEventListener("mousedown", function () {
      pendingQuote = quoteTextFromSelection(root);
    });
  }

  root.querySelectorAll("[data-rich-cmd]").forEach(function (btn) {
    btn.addEventListener("click", function (ev) {
      ev.preventDefault();
      stopDictation(root);
      var cmd = btn.getAttribute("data-rich-cmd");
      if (cmd === "toggleBlockquote" && pendingQuote) {
        insertQuotedText(editor, pendingQuote);
        pendingQuote = "";
        return;
      }
      pendingQuote = "";
      if (cmd === "setLink") {
        applyLinkCommand(root, editor);
        return;
      }
      closeLinkPop(root);
      var chain = editor.chain().focus();
      if (!cmd || typeof chain[cmd] !== "function") return;
      chain[cmd]().run();
    });
  });

  var linkApply = root.querySelector("[data-rich-link-apply]");
  var linkCancel = root.querySelector("[data-rich-link-cancel]");
  var linkInput = root.querySelector("[data-rich-link-input]");
  if (linkApply) {
    linkApply.addEventListener("click", function (ev) {
      ev.preventDefault();
      commitLinkPop(root, editor);
    });
  }
  if (linkCancel) {
    linkCancel.addEventListener("click", function (ev) {
      ev.preventDefault();
      closeLinkPop(root);
      editor.chain().focus().run();
    });
  }
  if (linkInput) {
    linkInput.addEventListener("keydown", function (ev) {
      if (ev.key !== "Enter") return;
      ev.preventDefault();
      commitLinkPop(root, editor);
    });
  }

  root._richEditor = editor;
  root._richInput = input;
}

function scan(scope) {
  (scope || document).querySelectorAll("[data-rich-editor]").forEach(initEditor);
}

function destroyIn(scope) {
  (scope || document).querySelectorAll("[data-rich-editor]").forEach(function (root) {
    closeLinkPop(root);
    detachDictation(root);
    if (!root._richEditor) return;
    try {
      root._richEditor.destroy();
    } catch (_e) {}
    root._richEditor = null;
    root._richInput = null;
  });
}

function findEditorRoot(formOrRoot) {
  if (!formOrRoot) return null;
  if (formOrRoot.matches && formOrRoot.matches("[data-rich-editor]")) return formOrRoot;
  return formOrRoot.querySelector ? formOrRoot.querySelector("[data-rich-editor]") : null;
}

window.richEditorValidate = function (formOrRoot) {
  var root = findEditorRoot(formOrRoot);
  if (!root || !root._richEditor) return true;
  var editor = root._richEditor;
  var input = root._richInput;
  var measured = measureContent(editor, input);
  var text = measured.text;
  var name = (input && input.getAttribute("name")) || "content";
  var form = root.closest("form") || formOrRoot;
  if (!text) {
    var emptyMsg =
      name === "content"
        ? i18n("errors.comment_empty")
        : i18n("validation.missing_field", {
            label: i18n("validation.field." + name) || name,
          });
    if (typeof window.showFieldError === "function") {
      window.showFieldError(form, name, emptyMsg || "");
    }
    return false;
  }
  var maxLen = maxLenFromInput(input);
  if (maxLen != null && measured.used > maxLen) {
    if (typeof window.showFieldError === "function") {
      window.showFieldError(form, name, i18n("errors.content_too_long", { max: maxLen }) || "");
    }
    return false;
  }
  return true;
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", function () {
    scan(document);
  });
} else {
  scan(document);
}

document.body.addEventListener(
  "submit",
  function (ev) {
    var form = ev.target;
    if (!form || !form.querySelectorAll) return;
    var roots = form.querySelectorAll("[data-rich-editor]");
    for (var i = 0; i < roots.length; i++) {
      if (!window.richEditorValidate(roots[i])) {
        ev.preventDefault();
        ev.stopPropagation();
        return;
      }
    }
  },
  true
);

document.body.addEventListener("htmx:beforeSwap", function (ev) {
  var target = ev.detail && ev.detail.target ? ev.detail.target : null;
  if (target) destroyIn(target);
});

document.body.addEventListener("htmx:afterSwap", function (ev) {
  scan(ev.detail && ev.detail.target ? ev.detail.target : document);
});

document.body.addEventListener(
  "toggle",
  function (ev) {
    var dlg = ev.target;
    if (!dlg || dlg.tagName !== "DIALOG") return;
    if (dlg.open) scan(dlg);
    else destroyIn(dlg);
  },
  true
);
