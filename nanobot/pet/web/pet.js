(function () {
  const params = new URLSearchParams(window.location.search);
  const wsUrl = params.get("ws") || "ws://127.0.0.1:18791";
  const shell = document.querySelector(".pet-shell");
  const pet = document.getElementById("pet");
  const avatar = document.querySelector(".pet-avatar");
  const bubble = document.getElementById("bubble");
  const bubbleText = document.getElementById("bubble-text");
  const dot = document.getElementById("dot");
  const avatarAssetVersion = "20260514-state-v1";
  const versionedAsset = (path) => `${path}?v=${avatarAssetVersion}`;
  const fallbackAvatarSrc = versionedAsset("./assets/spark-idle.png");
  const avatarByStatus = {
    "idle": versionedAsset("./assets/spark-idle.png"),
    "working": versionedAsset("./assets/spark-working.png"),
    "warning": versionedAsset("./assets/spark-warning.png"),
    "dragging": versionedAsset("./assets/spark-dragging.png"),
  };
  const bubbleMaxChars = 50;
  let bubbleTimer = null;
  let reconnectTimer = null;
  let dragPointer = null;
  let statusBeforeDrag = "idle";

  function setAvatarForStatus(status) {
    const src = avatarByStatus[status] || avatarByStatus.idle;
    if (avatar.getAttribute("src") !== src) {
      avatar.setAttribute("src", src);
    }
  }

  function applyVisualStatus(status) {
    const nextStatus = status || "idle";
    shell.dataset.status = nextStatus;
    setAvatarForStatus(nextStatus);
  }

  function setStatus(status) {
    const nextStatus = status || "idle";
    applyVisualStatus(nextStatus);
    if (dragPointer === null) {
      statusBeforeDrag = nextStatus;
    }
  }

  function formatBubbleText(text) {
    const chars = Array.from(String(text || "").trim());
    if (chars.length <= bubbleMaxChars) {
      return chars.join("");
    }
    return `${chars.slice(0, bubbleMaxChars).join("")}…`;
  }

  function showBubble(text) {
    const displayText = formatBubbleText(text);
    if (!displayText) return;
    bubbleText.textContent = displayText;
    bubble.hidden = false;
    window.clearTimeout(bubbleTimer);
    bubbleTimer = window.setTimeout(() => {
      bubble.hidden = true;
    }, 7000);
  }

  function connect() {
    const ws = new WebSocket(wsUrl);
    dot.dataset.connected = "connecting";

    ws.addEventListener("open", () => {
      dot.dataset.connected = "true";
    });

    ws.addEventListener("message", (event) => {
      const payload = JSON.parse(event.data);
      if (payload.status) {
        setStatus(payload.status);
      }
      if (payload.type === "pet.bubble" || payload.type === "pet.error") {
        showBubble(payload.text);
      }
    });

    ws.addEventListener("close", () => {
      dot.dataset.connected = "false";
      window.clearTimeout(reconnectTimer);
      reconnectTimer = window.setTimeout(connect, 1200);
    });

    ws.addEventListener("error", () => {
      dot.dataset.connected = "false";
      ws.close();
    });
  }

  avatar.addEventListener("error", () => {
    if (avatar.getAttribute("src") !== fallbackAvatarSrc) {
      avatar.setAttribute("src", fallbackAvatarSrc);
    }
  });

  function getDragApi() {
    return window.pywebview && window.pywebview.api ? window.pywebview.api : null;
  }

  async function startDrag(event) {
    if (event.button !== undefined && event.button !== 0) return;
    const api = getDragApi();
    if (!api || !window.pywebview.api.start_drag) return;

    event.preventDefault();
    dragPointer = event.pointerId;
    statusBeforeDrag = shell.dataset.status || "idle";
    pet.setPointerCapture(event.pointerId);
    applyVisualStatus("dragging");
    try {
      await window.pywebview.api.start_drag(event.screenX, event.screenY);
    } catch (_error) {
      dragPointer = null;
      applyVisualStatus(statusBeforeDrag);
    }
  }

  async function dragTo(event) {
    if (dragPointer !== event.pointerId) return;
    event.preventDefault();
    try {
      await window.pywebview.api.drag_to(event.screenX, event.screenY);
    } catch (_error) {
      // Ignore transient native-window failures; the next pointer event may recover.
    }
  }

  async function endDrag(event) {
    if (dragPointer !== event.pointerId) return;
    dragPointer = null;
    try {
      pet.releasePointerCapture(event.pointerId);
    } catch (_error) {
      // Pointer capture may already be released by the WebView.
    }
    try {
      await window.pywebview.api.end_drag();
    } catch (_error) {
      // The visual state should still recover even if the native bridge is gone.
    }
    applyVisualStatus(statusBeforeDrag || "idle");
  }

  pet.addEventListener("pointerdown", startDrag);
  pet.addEventListener("pointermove", dragTo);
  pet.addEventListener("pointerup", endDrag);
  pet.addEventListener("pointercancel", endDrag);

  setStatus("idle");
  connect();
})();
