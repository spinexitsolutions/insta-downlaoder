(function () {
  var form = document.getElementById("form");
  var input = document.getElementById("url");
  var goBtn = document.getElementById("go");
  var pasteBtn = document.getElementById("paste");
  var statusEl = document.getElementById("status");
  var errorEl = document.getElementById("error");
  var resultsEl = document.getElementById("results");
  var grid = document.getElementById("r-grid");
  var resultAdShown = false;

  var LOOKS_VALID = /instagram\.com\/|instagr\.am\/|^@?[A-Za-z0-9_.]{1,30}$/i;

  var ICON_IMAGE = '<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="9" cy="9" r="2"/><path d="m21 15-5-5L5 21"/></svg>';
  var ICON_VIDEO = '<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="4" width="20" height="16" rx="3"/><path d="m10 9 5 3-5 3z"/></svg>';
  var ICON_DL = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v11"/><path d="m7 10 5 5 5-5"/><path d="M5 20h14"/></svg>';

  function setLoading(on) {
    goBtn.disabled = on;
    goBtn.innerHTML = on ? '<span class="spinner"></span> Fetching…' : "Download";
    statusEl.textContent = on ? "Getting media from Instagram…" : "";
  }

  function showError(msg) {
    resultsEl.hidden = true;
    errorEl.textContent = msg;
    errorEl.hidden = false;
  }

  function fmtDuration(sec) {
    if (!sec) return "";
    sec = Math.round(sec);
    return Math.floor(sec / 60) + ":" + String(sec % 60).padStart(2, "0");
  }

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text) node.textContent = text;
    return node;
  }

  function render(data) {
    errorEl.hidden = true;
    grid.innerHTML = "";
    var user = data.username ? "@" + data.username : "Instagram";
    document.getElementById("r-user").textContent = user;
    document.getElementById("r-avatar").textContent = (data.username || "I").charAt(0).toUpperCase();
    var count = data.items.length;
    var summary = count > 1 ? count + " items" : (data.items[0].type === "video" ? "1 video" : "1 photo");
    document.getElementById("r-title").textContent = summary + (data.title ? " · " + data.title : "");

    data.items.forEach(function (item, i) {
      var card = el("div", "result-card");
      var thumb = el("div", "thumb");
      thumb.appendChild(Object.assign(el("div", "ph"), { innerHTML: item.type === "video" ? ICON_VIDEO : ICON_IMAGE }));
      if (item.thumbnail) {
        var img = new Image();
        img.alt = item.type === "video" ? "Video preview" : "Photo preview";
        img.loading = "lazy";
        img.onload = function () { thumb.querySelector(".ph").remove(); };
        img.onerror = function () { img.remove(); };
        img.src = item.thumbnail;
        thumb.appendChild(img);
      }
      var label = item.type === "video" ? "Video" : "Photo";
      var dur = fmtDuration(item.duration);
      thumb.appendChild(el("span", "badge", dur ? label + " · " + dur : label));
      if (item.height) thumb.appendChild(el("span", "badge q", item.height >= 1080 ? "HD" : item.height + "p"));
      card.appendChild(thumb);

      var a = el("a", "btn btn-primary btn-sm");
      a.href = item.download;
      a.rel = "nofollow";
      a.innerHTML = ICON_DL;
      a.appendChild(document.createTextNode(count > 1 ? " Download " + (i + 1) : " Download " + label));
      card.appendChild(a);
      grid.appendChild(card);
    });

    resultsEl.hidden = false;
    insertResultAd();
    resultsEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function insertResultAd() {
    var tpl = document.getElementById("result-ad");
    if (resultAdShown || !tpl || !tpl.content.querySelector("ins")) return;
    resultAdShown = true;
    var slot = tpl.content.cloneNode(true);
    // Scripts inside <template> don't run, so request the ad here.
    slot.querySelectorAll("script").forEach(function (s) { s.remove(); });
    resultsEl.appendChild(slot);
    try { (window.adsbygoogle = window.adsbygoogle || []).push({}); } catch (e) {}
  }

  var inFlight = false;
  function fetchInfo() {
    var value = input.value.trim();
    if (!value || inFlight) return;
    if (!LOOKS_VALID.test(value)) {
      showError("That doesn't look like an Instagram link. Copy it from the Share menu in Instagram.");
      return;
    }
    inFlight = true;
    errorEl.hidden = true;
    setLoading(true);
    fetch("/api/info", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: value })
    })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (data) {
          if (!res.ok) throw new Error(data.error || "Something went wrong. Please try again.");
          return data;
        });
      })
      .then(render)
      .catch(function (err) {
        showError(err.message === "Failed to fetch" ? "Network error. Check your connection and try again." : err.message);
      })
      .finally(function () {
        inFlight = false;
        setLoading(false);
      });
  }

  form.addEventListener("submit", function (e) { e.preventDefault(); fetchInfo(); });
  input.addEventListener("paste", function () { setTimeout(fetchInfo, 0); });

  pasteBtn.addEventListener("click", function () {
    if (!navigator.clipboard || !navigator.clipboard.readText) {
      input.focus();
      statusEl.textContent = "Long-press the box and choose Paste.";
      return;
    }
    navigator.clipboard.readText().then(function (text) {
      if (text) { input.value = text.trim(); fetchInfo(); }
    }).catch(function () {
      input.focus();
      statusEl.textContent = "Clipboard access was blocked. Long-press the box and choose Paste.";
    });
  });
})();
