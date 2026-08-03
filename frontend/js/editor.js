import { Editor } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import { Markdown } from "@tiptap/markdown";

var CMD_ACTIVE = {
  toggleBold: "bold",
  toggleItalic: "italic",
  toggleBulletList: "bulletList",
  toggleOrderedList: "orderedList",
  toggleCode: "code",
  toggleCodeBlock: "codeBlock",
  toggleBlockquote: "blockquote",
};

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
  input.value = String(editor.getMarkdown() || "").trimEnd();
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

function setMarkdownContent(editor, markdown) {
  editor.commands.setContent(markdown || "", { contentType: "markdown" });
}

function initEditor(root) {
  if (!root || root._richEditor) return;
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
        link: false,
        underline: false,
      }),
      Markdown,
    ],
    content: initial,
    contentType: "markdown",
    editorProps: { attributes: attrs },
    onCreate: function ({ editor: ed }) {
      syncMarkdown(ed, input);
      updateToolbar(root, ed);
    },
    onUpdate: function ({ editor: ed }) {
      syncMarkdown(ed, input);
      updateToolbar(root, ed);
    },
    onSelectionUpdate: function ({ editor: ed }) {
      updateToolbar(root, ed);
    },
  });

  root.querySelectorAll("[data-rich-cmd]").forEach(function (btn) {
    btn.addEventListener("click", function (ev) {
      ev.preventDefault();
      var cmd = btn.getAttribute("data-rich-cmd");
      var chain = editor.chain().focus();
      if (!cmd || typeof chain[cmd] !== "function") return;
      chain[cmd]().run();
    });
  });

  root._richEditor = editor;
  root._richInput = input;
  root._richInitial = initial;
}

function scan(scope) {
  (scope || document).querySelectorAll("[data-rich-editor]").forEach(initEditor);
}

function destroyIn(scope) {
  (scope || document).querySelectorAll("[data-rich-editor]").forEach(function (root) {
    if (!root._richEditor) return;
    try {
      root._richEditor.destroy();
    } catch (_e) {}
    root._richEditor = null;
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
  syncMarkdown(editor, input);
  var text = (editor.getText() || "").replace(/\u00a0/g, " ").trim();
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
  if (maxLen != null && (text.length > maxLen || (input.value || "").length > maxLen)) {
    if (typeof window.showFieldError === "function") {
      window.showFieldError(form, name, i18n("errors.content_too_long", { max: maxLen }) || "");
    }
    return false;
  }
  return true;
};

window.richEditorReset = function (formOrRoot) {
  var root = findEditorRoot(formOrRoot);
  if (!root || !root._richEditor) return;
  setMarkdownContent(root._richEditor, root._richInitial || "");
  syncMarkdown(root._richEditor, root._richInput);
  updateToolbar(root, root._richEditor);
};

window.richEditorFocus = function (formOrRoot) {
  var root = findEditorRoot(formOrRoot);
  if (!root || !root._richEditor) {
    scan(formOrRoot || document);
    root = findEditorRoot(formOrRoot);
  }
  if (root && root._richEditor) root._richEditor.commands.focus("end");
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
