document.addEventListener("alpine:init", () => {
  Alpine.data("dropdown", () => ({
    open: false,
    toggle() {
      if (this.$el.hasAttribute("data-disabled")) return;
      this.open = !this.open;
    },
    close() {
      this.open = false;
    },
  }));
  Alpine.data("devPanel", () => ({
    open: false,
    copied: false,
    init() {
      try {
        this.open = sessionStorage.getItem("devPanelOpen") === "1";
      } catch (error) {
        this.open = false;
      }
    },
    toggle() {
      this.open = !this.open;
      try {
        sessionStorage.setItem("devPanelOpen", this.open ? "1" : "0");
      } catch (error) {
        /* sessionStorage unavailable */
      }
    },
    copy() {
      const text = (this.$refs.copyText && this.$refs.copyText.textContent) || "";
      const done = () => {
        this.copied = true;
        window.setTimeout(() => {
          this.copied = false;
        }, 1600);
      };
      const fallback = () => {
        const el = document.createElement("textarea");
        el.value = text;
        el.setAttribute("readonly", "");
        el.style.position = "fixed";
        el.style.left = "-9999px";
        document.body.appendChild(el);
        el.select();
        try {
          document.execCommand("copy");
        } catch (error) {
          /* ignore */
        }
        document.body.removeChild(el);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard
          .writeText(text)
          .then(done)
          .catch(() => {
            fallback();
            done();
          });
        return;
      }
      fallback();
      done();
    },
  }));
});
