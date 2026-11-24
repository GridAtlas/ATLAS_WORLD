(function () {
  "use strict";

  var TAXONOMY = null;
  var WORKS = [];
  var form = null;
  var qInput = null;
  var sortSel = null;
  var countEl = null;
  var listEl = null;
  var emptyEl = null;
  var writingUrl = false;

  var DEFAULT_ROLES = ["本編", "付録"];
  var DECADE_ORDER = [
    "古代",
    "伝説・年代不詳",
    "17世紀以前",
    "18世紀",
    "19世紀",
    "1910年代",
    "1920年代",
    "1930年代",
    "1940年代",
    "1950年代",
    "1960年代",
    "1970年代",
    "1980年代",
    "1990年代",
    "2000年代",
    "2010年代",
    "2020年代"
  ];
  var VOLUME_ORDER = [
    "virtual-reality",
    "spacetime",
    "management-society",
    "post-apocalypse",
    "end-of-the-world",
    "ai"
  ];

  function fold(s) {
    s = (s || "").normalize("NFKC").toLowerCase();
    var out = "";
    for (var i = 0; i < s.length; i++) {
      var ch = s.charAt(i);
      var o = ch.charCodeAt(0);
      if (o >= 0x30a1 && o <= 0x30f6) ch = String.fromCharCode(o - 0x60);
      if ("ーｰ‐―—–-−‾~〜…‥⋯".indexOf(ch) !== -1) continue;
      if (/[\s\u3000・、。,.，．/／\\()（）[\]「」『』【】〈〉《》“”"'`!！?？:：;；&＆+＋=＝*＊#＃]/.test(ch)) continue;
      out += ch;
    }
    return out;
  }

  function haystack(w) {
    var parts = [w.title, w.orig, w.byline, w.snippet, w.yearLabel, String(w.year), w.decade];
    if (w.bylines) parts = parts.concat(w.bylines);
    if (w.media) parts = parts.concat(w.media);
    if (w.regions) parts = parts.concat(w.regions);
    if (w.themes) parts = parts.concat(w.themes);
    if (w.yomi) parts = parts.concat(w.yomi);
    (w.appearances || []).forEach(function (a) {
      parts.push(a.volumeLabel, a.role, a.titleInVolume);
    });
    return fold(parts.filter(Boolean).join(" "));
  }

  function uniqueSorted(arr, order) {
    var seen = {};
    var out = [];
    arr.forEach(function (v) {
      if (v && !seen[v]) {
        seen[v] = true;
        out.push(v);
      }
    });
    if (order) {
      out.sort(function (a, b) {
        var ia = order.indexOf(a);
        var ib = order.indexOf(b);
        if (ia === -1 && ib === -1) return a.localeCompare(b, "ja");
        if (ia === -1) return 1;
        if (ib === -1) return -1;
        return ia - ib;
      });
    } else {
      out.sort(function (a, b) {
        return a.localeCompare(b, "ja");
      });
    }
    return out;
  }

  function checkedValues(name) {
    return Array.prototype.slice
      .call(form.querySelectorAll('input[name="' + name + '"]:checked'))
      .map(function (el) {
        return el.value;
      });
  }

  function setChecked(name, values) {
    var set = {};
    (values || []).forEach(function (v) {
      set[v] = true;
    });
    Array.prototype.slice.call(form.querySelectorAll('input[name="' + name + '"]')).forEach(function (el) {
      el.checked = !!set[el.value];
    });
  }

  function currentState() {
    var roles = checkedValues("role");
    if (!roles.length) roles = DEFAULT_ROLES.slice();
    return {
      q: (qInput.value || "").trim(),
      vol: checkedValues("vol"),
      role: roles,
      media: checkedValues("media"),
      decade: checkedValues("decade"),
      region: checkedValues("region"),
      theme: checkedValues("theme"),
      sort: sortSel.value || "year",
      roleTouched: checkedValues("role").length > 0
    };
  }

  function applyState(state) {
    qInput.value = state.q || "";
    setChecked("vol", state.vol || []);
    setChecked(
      "role",
      state.roleTouched === false && (!state.role || !state.role.length) ? DEFAULT_ROLES : state.role || DEFAULT_ROLES
    );
    setChecked("media", state.media || []);
    setChecked("decade", state.decade || []);
    setChecked("region", state.region || []);
    setChecked("theme", state.theme || []);
    sortSel.value = state.sort || "year";
  }

  function parseQuery() {
    var p = new URLSearchParams(location.search);
    function csv(key) {
      var v = p.get(key);
      if (!v) return [];
      return v.split(",").map(function (s) {
        return s.trim();
      }).filter(Boolean);
    }
    var state = {
      q: p.get("q") || "",
      vol: csv("vol"),
      role: csv("role"),
      media: csv("media"),
      decade: csv("decade"),
      region: csv("region"),
      theme: csv("theme"),
      sort: p.get("sort") || "year",
      roleTouched: p.has("role")
    };
    if (!state.role.length && !state.roleTouched) state.role = DEFAULT_ROLES.slice();
    return state;
  }

  function writeQuery(state) {
    var p = new URLSearchParams();
    if (state.q) p.set("q", state.q);
    function put(key, arr, skip) {
      if (arr && arr.length && !skip) p.set(key, arr.join(","));
    }
    put("vol", state.vol);
    var roleIsDefault =
      state.role.length === DEFAULT_ROLES.length &&
      DEFAULT_ROLES.every(function (r) {
        return state.role.indexOf(r) !== -1;
      });
    if (state.roleTouched && !roleIsDefault) put("role", state.role);
    put("media", state.media);
    put("decade", state.decade);
    put("region", state.region);
    put("theme", state.theme);
    if (state.sort && state.sort !== "year") p.set("sort", state.sort);
    var qs = p.toString();
    var url = location.pathname + (qs ? "?" + qs : "") + location.hash;
    writingUrl = true;
    history.replaceState(state, "", url);
    writingUrl = false;
  }

  function matchingApps(work, state) {
    return (work.appearances || []).filter(function (a) {
      if (state.role.length && state.role.indexOf(a.role) === -1) return false;
      if (state.vol.length && state.vol.indexOf(a.volume) === -1) return false;
      return true;
    });
  }

  function matches(work, state, qfold) {
    var apps = matchingApps(work, state);
    if (!apps.length) return false;
    if (qfold && (work._hay || (work._hay = haystack(work))).indexOf(qfold) === -1) return false;
    if (state.media.length && !state.media.some(function (m) { return (work.media || []).indexOf(m) !== -1; })) return false;
    if (state.decade.length && state.decade.indexOf(work.decade) === -1) return false;
    if (state.region.length && !state.region.some(function (r) { return (work.regions || []).indexOf(r) !== -1; })) return false;
    if (state.theme.length && !state.theme.every(function (t) { return (work.themes || []).indexOf(t) !== -1; })) return false;
    return true;
  }

  function volumeRank(work, state) {
    var apps = matchingApps(work, state);
    var best = 99;
    apps.forEach(function (a) {
      var i = VOLUME_ORDER.indexOf(a.volume);
      if (i === -1) i = 98;
      if (i < best) best = i;
    });
    return best;
  }

  function compare(a, b, state) {
    var sort = state.sort || "year";
    if (sort === "-year") {
      var dy = (b.year == null ? -99999 : b.year) - (a.year == null ? -99999 : a.year);
      if (dy) return dy;
      return a.title.localeCompare(b.title, "ja");
    }
    if (sort === "title") {
      return a.title.localeCompare(b.title, "ja");
    }
    if (sort === "volume") {
      var dv = volumeRank(a, state) - volumeRank(b, state);
      if (dv) return dv;
      var y = (a.year == null ? 99999 : a.year) - (b.year == null ? 99999 : b.year);
      if (y) return y;
      return a.title.localeCompare(b.title, "ja");
    }
    var y2 = (a.year == null ? 99999 : a.year) - (b.year == null ? 99999 : b.year);
    if (y2) return y2;
    return a.title.localeCompare(b.title, "ja");
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function yearText(w) {
    if (w.year == null) return w.yearLabel || "年代不詳";
    if (w.year < 0) return w.yearLabel || "紀元前";
    if (w.year < 1000) return w.yearLabel || String(w.year);
    return String(w.year);
  }

  function cardHtml(w, state) {
    var apps = matchingApps(w, state);
    if (!apps.length) apps = w.appearances || [];
    var href = apps[0] && apps[0].href ? apps[0].href : "#";
    var orig = w.orig ? '<span class="orig">' + escapeHtml(w.orig) + "</span>" : "";
    var appHtml = apps
      .map(function (a) {
        return (
          '<a href="' +
          escapeHtml(a.href) +
          '">' +
          escapeHtml(a.volumeLabel.replace(/アトラス$/, "")) +
          "・" +
          escapeHtml(a.role) +
          "</a>"
        );
      })
      .join('<span class="sep">/</span>');
    var tags = []
      .concat(w.media || [])
      .concat(w.regions || [])
      .concat(w.themes || []);
    var tagHtml = tags
      .map(function (t) {
        return "<li>" + escapeHtml(t) + "</li>";
      })
      .join("");
    var snippet = w.snippet ? '<p class="snippet">' + escapeHtml(w.snippet) + "</p>" : "";
    return (
      '<article class="work-card">' +
      '<div class="year">' +
      escapeHtml(yearText(w)) +
      "</div>" +
      "<div>" +
      "<h2><a href=\"" +
      escapeHtml(href) +
      '">' +
      escapeHtml(w.title) +
      "</a>" +
      orig +
      "</h2>" +
      (w.byline ? '<p class="byline">' + escapeHtml(w.byline) + "</p>" : "") +
      '<p class="apps">' +
      appHtml +
      "</p>" +
      snippet +
      (tagHtml ? '<ul class="tags">' + tagHtml + "</ul>" : "") +
      "</div></article>"
    );
  }

  function isDefaultState(state) {
    return (
      !state.q &&
      !state.vol.length &&
      !state.media.length &&
      !state.decade.length &&
      !state.region.length &&
      !state.theme.length &&
      (state.sort || "year") === "year" &&
      state.role.length === DEFAULT_ROLES.length &&
      DEFAULT_ROLES.every(function (r) {
        return state.role.indexOf(r) !== -1;
      })
    );
  }

  function render() {
    var state = currentState();
    writeQuery(state);
    var qfold = fold(state.q);
    var found = WORKS.filter(function (w) {
      return matches(w, state, qfold);
    }).sort(function (a, b) {
      return compare(a, b, state);
    });

    var counts = TAXONOMY && TAXONOMY.counts ? TAXONOMY.counts : {};
    var text;
    if (isDefaultState(state)) {
      text =
        found.length +
        "作を表示（公式の延べ収録は" +
        (counts.officialEntries || 224) +
        "件。複数のアトラスに載る" +
        (counts.multiVolumeOfficial || 10) +
        "作は1枚にまとめています）";
    } else {
      text = found.length + "作を表示";
    }
    countEl.textContent = text;

    if (!found.length) {
      listEl.innerHTML = "";
      emptyEl.hidden = false;
    } else {
      emptyEl.hidden = true;
      listEl.innerHTML = found.map(function (w) { return cardHtml(w, state); }).join("");
    }
  }

  function chip(name, value, label) {
    return (
      '<label class="chip"><input type="checkbox" name="' +
      name +
      '" value="' +
      escapeHtml(value) +
      '"><span>' +
      escapeHtml(label) +
      "</span></label>"
    );
  }

  function fillFilters(data) {
    var vols = data.taxonomy.volumes || [];
    var volOrder = VOLUME_ORDER.slice();
    vols.sort(function (a, b) {
      return volOrder.indexOf(a.id) - volOrder.indexOf(b.id);
    });
    document.getElementById("fg-vol").innerHTML = vols
      .map(function (v) {
        return chip("vol", v.id, v.label.replace(/アトラス$/, ""));
      })
      .join("");

    document.getElementById("fg-role").innerHTML = ["本編", "付録", "読み物"]
      .map(function (r) {
        return chip("role", r, r);
      })
      .join("");

    document.getElementById("fg-media").innerHTML = (data.taxonomy.media || [])
      .map(function (m) {
        return chip("media", m, m);
      })
      .join("");

    var decades = uniqueSorted(
      WORKS.map(function (w) {
        return w.decade;
      }),
      DECADE_ORDER
    );
    document.getElementById("fg-decade").innerHTML = decades
      .map(function (d) {
        return chip("decade", d, d);
      })
      .join("");

    var regions = uniqueSorted(
      WORKS.reduce(function (acc, w) {
        return acc.concat(w.regions || []);
      }, [])
    );
    document.getElementById("fg-region").innerHTML = regions
      .map(function (r) {
        return chip("region", r, r);
      })
      .join("");

    document.getElementById("fg-theme").innerHTML = (data.taxonomy.themes || [])
      .map(function (t) {
        return chip("theme", t, t);
      })
      .join("");
  }

  function clearFilters() {
    qInput.value = "";
    sortSel.value = "year";
    Array.prototype.slice.call(form.querySelectorAll('input[type="checkbox"]')).forEach(function (el) {
      el.checked = false;
    });
    setChecked("role", DEFAULT_ROLES);
    render();
    qInput.focus();
  }

  function init(data) {
    TAXONOMY = data;
    WORKS = data.works || [];
    form = document.getElementById("works-form");
    qInput = document.getElementById("q");
    sortSel = document.getElementById("sort");
    countEl = document.getElementById("count");
    listEl = document.getElementById("work-list");
    emptyEl = document.getElementById("empty");

    fillFilters(data);
    applyState(parseQuery());

    var timer = null;
    qInput.addEventListener("input", function () {
      clearTimeout(timer);
      timer = setTimeout(render, 80);
    });
    form.addEventListener("change", render);
    document.getElementById("clear").addEventListener("click", clearFilters);
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      render();
    });
    window.addEventListener("popstate", function () {
      if (writingUrl) return;
      applyState(parseQuery());
      render();
    });
    render();
  }

  fetch("works.json", { cache: "no-cache" })
    .then(function (res) {
      if (!res.ok) throw new Error("works.json " + res.status);
      return res.json();
    })
    .then(init)
    .catch(function (err) {
      document.getElementById("count").textContent = "作品データを読み込めませんでした。";
      document.getElementById("empty").hidden = false;
      console.error(err);
    });
})();
