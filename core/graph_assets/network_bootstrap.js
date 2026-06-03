
                  network = new vis.Network(container, data, options);
                  const OSGE_CONFIG = __OSGE_CONFIG__;
                  const OSGE_ALL_NODES = nodes.get();
	                  const OSGE_ALL_EDGES = edges.get();
	                  const OSGE_PAGE_STORAGE_KEY = "osge.pageSettings.v1";
	                  let osgeActiveNodeFilterKey = "";
	                  let osgeActiveDisplayStyleKey = "";
	                  function osgePlatforms() {
	                      if (Array.isArray(OSGE_CONFIG.platforms) && OSGE_CONFIG.platforms.length) {
	                          return OSGE_CONFIG.platforms;
	                      }
	                      return [{
	                          id: OSGE_CONFIG.sourcePlatform || OSGE_CONFIG.defaultPlatform || "platform",
	                          displayName: OSGE_CONFIG.sourcePlatform || "Platform",
	                          shortName: OSGE_CONFIG.sourcePlatform || "平台",
	                          aliases: [],
	                          urlMarkers: [],
	                          idLabel: "平台 ID / Platform ID",
	                          displayIdFieldOrder: ["platform_user_id", "username"],
	                          expandScript: ""
	                      }];
	                  }
	                  function osgeDefaultPlatform() {
	                      return OSGE_CONFIG.defaultPlatform || (osgePlatforms()[0] && osgePlatforms()[0].id) || "platform";
	                  }
	                  function osgePlatformConfig(platform) {
	                      const normalized = String(platform || "").toLowerCase();
	                      return osgePlatforms().find(function (item) {
	                          return item.id === normalized || (Array.isArray(item.aliases) && item.aliases.includes(normalized));
	                      }) || null;
	                  }
	                  function osgePlatformFromAccountId(accountId) {
	                      const value = String(accountId || "").toLowerCase();
	                      for (const platform of osgePlatforms()) {
	                          const prefixes = [platform.id].concat(Array.isArray(platform.aliases) ? platform.aliases : []);
	                          if (prefixes.some(function (prefix) { return value.startsWith(`${prefix}:`); })) {
	                              return platform.id;
	                          }
	                          const markers = Array.isArray(platform.urlMarkers) ? platform.urlMarkers : [];
	                          if (markers.some(function (marker) { return value.includes(String(marker).toLowerCase()); })) {
	                              return platform.id;
	                          }
	                      }
	                      return OSGE_CONFIG.sourcePlatform || osgeDefaultPlatform();
	                  }
	                  function osgeCurrentPlatform() {
	                      return OSGE_CONFIG.sourcePlatform || osgeDefaultPlatform();
	                  }
                  function osgePageSettings() {
                      const searchPanel = document.getElementById("osge-search-panel");
                      const displayPanel = document.getElementById("osge-display-panel");
                      return {
                          searchCollapsed: Boolean(searchPanel && searchPanel.classList.contains("is-collapsed")),
                          displayPanelOpen: Boolean(displayPanel && displayPanel.open)
                      };
                  }
                  function osgeSavePageSettings() {
                      try {
                          window.localStorage.setItem(OSGE_PAGE_STORAGE_KEY, JSON.stringify(osgePageSettings()));
                      } catch (error) {
                          // Ignore storage failures in private browsing or locked-down browsers.
                      }
                  }
                  function osgeLoadPageSettings() {
                      let saved = null;
                      try {
                          saved = JSON.parse(window.localStorage.getItem(OSGE_PAGE_STORAGE_KEY) || "null");
                      } catch (error) {
                          saved = null;
                      }
                      if (!saved) {
                          return;
                      }
                      if (typeof saved.searchCollapsed === "boolean") {
                          osgeSetSearchPanelCollapsed(saved.searchCollapsed, false);
                      }
                      const displayPanel = document.getElementById("osge-display-panel");
                      if (displayPanel && typeof saved.displayPanelOpen === "boolean") {
                          displayPanel.open = saved.displayPanelOpen;
                      }
                  }
                  function osgeGraphUrl(centerId, platform) {
                      const params = new URLSearchParams();
                      params.set("platform", platform || osgePlatformFromAccountId(centerId));
                      if (centerId) {
                          params.set("center", centerId);
                      }
                      params.set("t", String(Date.now()));
                      return `/graph?${params.toString()}`;
                  }
	                  function osgeMarkActivePlatform() {
	                      osgePlatforms().forEach(function (platformItem) {
	                          const platform = platformItem.id;
	                          const link = document.getElementById(`osge-platform-${platform}`);
	                          if (link) {
	                              link.classList.toggle("is-active", platform === osgeCurrentPlatform());
	                          }
	                      });
	                  }
	                  function osgeRenderPlatformSwitch() {
	                      const panel = document.getElementById("osge-platform-panel");
	                      if (!panel) {
	                          return;
	                      }
	                      panel.innerHTML = osgePlatforms().map(function (platform) {
	                          return `<a id="osge-platform-${osgeEscapeHtml(platform.id)}" href="/graph?platform=${encodeURIComponent(platform.id)}">${osgeEscapeHtml(platform.shortName || platform.displayName || platform.id)}</a>`;
	                      }).join("");
	                      osgeMarkActivePlatform();
	                  }
	                  function osgeUpdatePlatformSearchText() {
	                      const crawlInput = document.getElementById("osge-crawl-account-input");
	                      const platformExamples = osgePlatforms().map(function (platform) {
	                          return `${platform.id}:<id>`;
	                      }).join(" / ");
	                      if (crawlInput) {
	                          crawlInput.placeholder = `平台主页/短链 URL、${platformExamples}`;
	                      }
	                      osgeSetSearchStatus("调用 OSGE 平台 adapter 采集。 / Crawls via OSGE platform adapters.");
	                  }
	                  function osgeInitializePlatformUi() {
	                      osgeRenderPlatformSwitch();
	                      osgeUpdatePlatformSearchText();
	                  }
                  function osgeSetSearchPanelCollapsed(collapsed, persist) {
                      const panel = document.getElementById("osge-search-panel");
                      const button = document.getElementById("osge-search-collapse");
                      if (!panel) {
                          return;
                      }
                      panel.classList.toggle("is-collapsed", Boolean(collapsed));
                      if (button) {
                          button.textContent = collapsed ? "展开" : "收起";
                      }
                      if (persist !== false) {
                          osgeSavePageSettings();
                      }
                  }
                  function osgeCollapseAmbientPanels() {
                      osgeSetSearchPanelCollapsed(true);
                      const displayPanel = document.getElementById("osge-display-panel");
                      if (displayPanel) {
                          displayPanel.open = false;
                      }
                      osgeSavePageSettings();
                  }
                  window.osgeToggleSearchPanel = function () {
                      const panel = document.getElementById("osge-search-panel");
                      osgeSetSearchPanelCollapsed(!(panel && panel.classList.contains("is-collapsed")));
                  };
                  function osgeEscapeHtml(value) {
                      return String(value ?? "")
                          .replace(/&/g, "&amp;")
                          .replace(/</g, "&lt;")
                          .replace(/>/g, "&gt;")
                          .replace(/"/g, "&quot;")
                          .replace(/'/g, "&#039;");
                  }
                  function osgeShellQuote(value) {
                      return "'" + String(value ?? "").replace(/'/g, "'\\\\''") + "'";
                  }
                  function osgeField(label, value) {
                      const rendered = value === undefined || value === null || value === "" ? "n/a" : value;
                      const labelHtml = String(label ?? "")
                          .split(" / ")
                          .map(function (part, index) {
                              const className = index === 0 ? "" : " class='osge-label-secondary'";
                              return `<span${className}>${osgeEscapeHtml(part)}</span>`;
                          })
                          .join("");
                      return `<dt>${labelHtml}</dt><dd>${osgeEscapeHtml(rendered)}</dd>`;
                  }
                  function osgeHtmlField(label, html) {
                      const labelHtml = String(label ?? "")
                          .split(" / ")
                          .map(function (part, index) {
                              const className = index === 0 ? "" : " class='osge-label-secondary'";
                              return `<span${className}>${osgeEscapeHtml(part)}</span>`;
                          })
                          .join("");
                      return `<dt>${labelHtml}</dt><dd>${html || "n/a"}</dd>`;
                  }
	                  function osgePlatformIdLabel(node) {
	                      const platform = osgePlatformConfig(node.platform);
	                      return (platform && platform.idLabel) || "平台 ID / Platform ID";
	                  }
	                  function osgePlatformDisplayId(node) {
	                      const platform = osgePlatformConfig(node.platform);
	                      const order = platform && Array.isArray(platform.displayIdFieldOrder)
	                          ? platform.displayIdFieldOrder
	                          : ["platform_user_id", "username"];
	                      for (const field of order) {
	                          if (node[field]) {
	                              return node[field];
	                          }
	                      }
	                      return node.platform_user_id || node.username || "";
	                  }
	                  function osgeExpandCommand(node) {
	                      const platform = osgePlatformConfig(node.platform);
	                      const platformId = (platform && platform.id) || node.platform || osgeCurrentPlatform();
	                      const script = (platform && platform.expandScript) || "scripts/expand_account.py";
	                      return [
                          ".venv/bin/python",
                          script,
                          "--db",
                          OSGE_CONFIG.dbPath || "data/database/osge_overlay.db",
                          "--platform",
                          osgeShellQuote(platformId),
                          "--account",
                          osgeShellQuote(node.account_id || node.id),
                          "--max-notes",
                          String(osgeReadNumber("osge-max-notes", 5)),
                          "--max-comments",
                          String(osgeReadNumber("osge-max-comments", 10))
                      ].concat(osgeReadChecked("osge-get-sub-comments") ? ["--get-sub-comments"] : [])
                       .concat(osgeReadChecked("osge-force-refresh") ? ["--force"] : [])
                       .join(" ");
                  }
                  function osgeReadNumber(id, fallback) {
                      const field = document.getElementById(id);
                      const value = Number(field && field.value);
                      return Number.isFinite(value) && value > 0 ? value : fallback;
                  }
                  function osgeReadChecked(id) {
                      const field = document.getElementById(id);
                      return Boolean(field && field.checked);
                  }
                  function osgeRangeControlIds() {
                      return [
                          "osge-node-font-size",
                          "osge-edge-label-size",
                          "osge-node-size-scale",
                          "osge-line-width-scale",
                          "osge-line-weight-impact",
                          "osge-weight-distance-impact",
                          "osge-center-spacing",
                          "osge-peer-spacing",
                          "osge-outer-spacing",
                          "osge-min-edge-length",
                          "osge-max-edge-length",
                          "osge-leaf-min-distance",
                          "osge-component-gravity",
                          "osge-repulsion"
                      ];
                  }
                  function osgeSetStatus(message) {
                      const status = document.getElementById("osge-expand-status");
                      if (status) {
                          status.textContent = message;
                      }
                  }
                  function osgeSetSearchStatus(message) {
                      const status = document.getElementById("osge-search-status");
                      if (status) {
                          status.textContent = message;
                      }
                  }
	                  function osgeResultLabel(item) {
	                      const name = item.nickname || item.username || item.platform_user_id || item.account_id;
	                      const displayId = osgePlatformDisplayId(item);
	                      const label = osgePlatformIdLabel(item).split(" / ")[0];
	                      const publicId = displayId && displayId !== name
	                          ? ` · ${label}: ${displayId}`
	                          : "";
	                      return `${name}${publicId}`;
	                  }
                  function osgeResultAvatarHtml(item) {
                      const label = item.nickname || item.username || item.platform_user_id || item.account_id || "?";
                      const fallback = osgeEscapeHtml(String(label).trim().slice(0, 1).toUpperCase() || "?");
                      if (item.avatar_local_url) {
                          return `<span class="osge-result-avatar"><img src="${osgeEscapeHtml(item.avatar_local_url)}" alt="" loading="lazy"></span>`;
                      }
                      return `<span class="osge-result-avatar">${fallback}</span>`;
                  }
                  let osgeAutoCenterCanceled = false;
                  function osgeCancelAutoCenter() {
                      osgeAutoCenterCanceled = true;
                      network.releaseNode();
                  }
                  function osgeCenterAccountNode(accountId, node, options) {
                      const isAutoCenter = Boolean(options && options.auto);
                      if (isAutoCenter && osgeAutoCenterCanceled) {
                          return;
                      }
                      network.releaseNode();
                      network.stopSimulation();
                      network.selectNodes([accountId]);
                      window.requestAnimationFrame(function () {
                          if (isAutoCenter && osgeAutoCenterCanceled) {
                              return;
                          }
                          const position = network.getPositions([accountId])[accountId];
                          if (position) {
                              network.moveTo({
                                  position: position,
                                  scale: 1.05,
                                  animation: {duration: 420, easingFunction: "easeInOutQuad"}
                              });
                              window.setTimeout(function () {
                                  network.releaseNode();
                              }, 460);
                          }
                      });
                      osgeShowNodeDetails(node);
                  }
                  window.osgeFocusAccount = function (accountId) {
                      if (!accountId) {
                          return;
                      }
                      osgeSetSearchStatus(`正在定位节点... / Focusing node...`);
                      const node = nodes.get(accountId);
                      if (node) {
                          osgeCenterAccountNode(accountId, node);
                          const results = document.getElementById("osge-local-search-results");
                          if (results) {
                              results.innerHTML = "";
                          }
                          osgeSetSearchStatus(`已定位 / Focused: ${node.label || accountId}`);
                          return;
                      }
                      osgeSetSearchStatus("当前视图未包含该节点，正在重新载入图谱... / Reloading graph centered on this account...");
                      window.location.href = osgeGraphUrl(accountId, osgePlatformFromAccountId(accountId));
                  };
	                  function osgePlatformName(platform) {
	                      const item = osgePlatformConfig(platform);
	                      if (item) {
	                          return `${item.shortName || item.id} / ${item.displayName || item.id}`;
	                      }
	                      return platform || "unknown";
	                  }
	                  function osgePlatformShortName(platform) {
	                      const item = osgePlatformConfig(platform);
	                      return (item && (item.shortName || item.displayName)) || platform || "unknown";
	                  }
                  function osgeAccountDisplayName(account) {
                      return account.nickname || account.username || account.platform_user_id || account.account_id || "unknown";
                  }
                  function osgeProfileLinkHtml(url) {
                      if (!url) {
                          return "n/a";
                      }
                      return `<a href="${osgeEscapeHtml(url)}" target="_blank" rel="noopener">${osgeEscapeHtml(url)}</a>`;
                  }
                  function osgeAvatarHtml(account) {
                      const label = osgeAccountDisplayName(account);
                      const fallback = osgeEscapeHtml(String(label).trim().slice(0, 1).toUpperCase() || "?");
                      const localUrl = account.avatar_local_url || account.avatar_image_url || "";
                      const remoteUrl = account.avatar_url || "";
                      const accountId = account.account_id || account.id || "";
                      const refreshButton = remoteUrl
                          ? `
                              <button type="button" class="osge-avatar-refresh" data-avatar-account="${osgeEscapeHtml(accountId)}" onclick="osgeRefreshAvatar('${osgeEscapeHtml(accountId)}', this)">
                                  刷新头像 / Refresh avatar
                              </button>
                          `
                          : "";
                      if (localUrl) {
                          return `
                              <span class="osge-avatar-control">
                              <span class="osge-profile-avatar">
                                  <img src="${osgeEscapeHtml(localUrl)}" alt="" loading="lazy"
                                       data-avatar-account="${osgeEscapeHtml(accountId)}"
                                       data-remote-avatar="${osgeEscapeHtml(remoteUrl)}"
                                       onerror="osgeHandleAvatarError(this, '${osgeEscapeHtml(accountId)}')">
                              </span>
                              ${refreshButton}
                              </span>
                          `;
                      }
                      if (remoteUrl) {
                          return `<span class="osge-avatar-control">${refreshButton}</span>`;
                      }
                      return `<span class="osge-profile-avatar osge-avatar-placeholder">${fallback}</span>`;
                  }
                  function osgePlatformAccountFields(account) {
                      return `
                          <dl>
                              ${osgeField("昵称 / Nickname", account.nickname)}
                              ${osgeField("账号 / Account", osgePlatformDisplayId(account))}
                              ${osgeHtmlField("头像 / Avatar", osgeAvatarHtml(account))}
                              ${osgeField("IP属地 / IP location", account.location)}
                              ${osgeField("简介 / Bio", account.bio)}
                              ${osgeField("性别 / Gender", account.gender)}
                              ${osgeHtmlField("主页 / Profile", osgeProfileLinkHtml(account.profile_url))}
                          </dl>
                      `;
                  }
                  function osgeLinkedAccountsHtml(detail, selectedAccountId) {
                      if (!detail || !Array.isArray(detail.linked_accounts)) {
                          return `<p class="osge-muted">正在读取身份关联账号... / Loading linked accounts...</p>`;
                      }
                      if (!detail.linked_accounts.length) {
                          return `<p class="osge-muted">暂无关联账号。 / No linked accounts.</p>`;
                      }
                      return `<div class="osge-linked-accounts">` + detail.linked_accounts.map(function (account) {
                          const selected = account.account_id === selectedAccountId;
                          return `
                              <details class="osge-linked-platform ${selected ? "is-selected" : ""}" ${selected ? "open" : ""}>
                                  <summary onclick="${selected ? "" : `event.preventDefault(); osgeFocusAccount('${osgeEscapeHtml(account.account_id)}');`}">
                                      <strong>${osgeEscapeHtml(osgePlatformShortName(account.platform))} · ${osgeEscapeHtml(osgeAccountDisplayName(account))}</strong>
                                      ${selected ? `<span>当前 / Selected</span>` : ""}
                                  </summary>
                                  ${osgePlatformAccountFields(account)}
                              </details>
                          `;
                      }).join("") + `</div>`;
                  }
                  function osgeIdentityHtml(detail) {
                      if (!detail || !detail.identity) {
                          return `
                              <p class="osge-section-title">身份容器 / Identity container</p>
                              <p class="osge-muted">正在读取身份容器... / Loading identity container...</p>
                          `;
                      }
                      const identity = detail.identity;
                      return `
                          <p class="osge-section-title">身份容器 / Identity container</p>
                          <dl>
                              ${osgeField("姓名 / Name", identity.legal_name || identity.display_name)}
                              ${osgeField("电话 / Phone", identity.phone)}
                              ${osgeField("邮箱 / Email", identity.email)}
                              ${osgeField("OSGE 账号 / OSGE account", identity.osge_account || identity.identity_id)}
                              ${osgeField("身份 ID / Identity ID", identity.identity_id)}
                              ${osgeField("备注 / Notes", identity.notes)}
                          </dl>
                      `;
                  }
                  function osgeEvidenceHtml(items) {
                      if (!Array.isArray(items) || !items.length) {
                          return `<p class="osge-muted">没有可显示的评论内容。 / No captured comment content.</p>`;
                      }
                      const groups = [];
                      const groupIndex = new Map();
                      items.forEach(function (item) {
                          const key = item.post_id || item.post_url || "unknown-post";
                          let group = groupIndex.get(key);
                          if (!group) {
                              group = {
                                  post_id: item.post_id || "",
                                  post_content: item.post_content || "",
                                  post_url: item.post_url || "",
                                  items: []
                              };
                              groupIndex.set(key, group);
                              groups.push(group);
                          }
                          if (!group.post_content && item.post_content) {
                              group.post_content = item.post_content;
                          }
                          if (!group.post_url && item.post_url) {
                              group.post_url = item.post_url;
                          }
                          group.items.push(item);
                      });
                      return `<div class="osge-evidence-list">` + groups.map(function (group) {
                          const postTitle = group.post_id ? `帖子 / Post ${group.post_id}` : "未知帖子 / Unknown post";
                          const postSummary = group.post_content || "没有帖子摘要。 / No captured post summary.";
                          const postLink = group.post_url
                              ? `<a href="${osgeEscapeHtml(group.post_url)}" target="_blank" rel="noopener">${osgeEscapeHtml(group.post_url)}</a>`
                              : `<span class="osge-muted">没有帖子链接。 / No captured post link.</span>`;
                          const evidenceItems = group.items.map(function (item) {
                          const content = item.content || "[空评论 / Empty comment]";
                          const meta = [
                              item.interaction_type || "",
                              item.comment_id ? `comment=${item.comment_id}` : "",
                              item.parent_comment_id && item.parent_comment_id !== "0" ? `parent=${item.parent_comment_id}` : "",
                              item.created_at || "",
                              item.like_count !== undefined && item.like_count !== "" ? `likes=${item.like_count}` : ""
                          ].filter(Boolean).join(" · ");
                          return `
                              <div class="osge-evidence-item">
                                  <p>${osgeEscapeHtml(content)}</p>
                                  <div class="osge-evidence-meta">${osgeEscapeHtml(meta)}</div>
                              </div>
                          `;
                          }).join("");
                          return `
                              <section class="osge-post-evidence-group">
                                  <div class="osge-post-evidence-header">
                                      <strong>${osgeEscapeHtml(postTitle)} · ${group.items.length} 条互动 / interactions</strong>
                                      <div class="osge-post-summary">${osgeEscapeHtml(postSummary)}</div>
                                      <div>${postLink}</div>
                                  </div>
                                  <div class="osge-post-evidence-items">${evidenceItems}</div>
                              </section>
                          `;
                      }).join("") + `</div>`;
                  }
                  function osgeShowEdgeDetails(edge) {
                      const panel = document.getElementById("osge-node-panel");
                      if (!panel || !edge) {
                          return;
                      }
                      panel.classList.remove("osge-hidden");
                      window.osgeSelectedNode = null;
                      window.osgeSelectedIdentityDetail = null;
                      const relationTypes = Array.isArray(edge.relation_types) && edge.relation_types.length
                          ? edge.relation_types.join(", ")
                          : edge.relation_type;
                      panel.innerHTML = `
                          <h2>${osgeEscapeHtml(edge.source_name || edge.from)} ↔ ${osgeEscapeHtml(edge.target_name || edge.to)}</h2>
                          <p class="osge-muted">${osgeEscapeHtml(edge.relation_label || edge.relation_type || "relation")}</p>
                          <p class="osge-section-title">关系摘要 / Relation summary</p>
                          <dl>
                              ${osgeField("互动类型 / Interaction types", relationTypes)}
                              ${osgeField("互动次数 / Interaction count", edge.interaction_count)}
                              ${osgeField("权重 / Weight", edge.edge_weight)}
                              ${osgeField("置信度 / Confidence", edge.confidence)}
                              ${osgeField("首次出现 / First seen", edge.first_seen)}
                              ${osgeField("最近出现 / Last seen", edge.last_seen)}
                          </dl>
                          <p class="osge-section-title">评论/回复内容 / Comment evidence</p>
                          ${osgeEvidenceHtml(edge.evidence_items)}
                      `;
                  }
                  function osgeReadDisplayNumber(id, fallback) {
                      const field = document.getElementById(id);
                      const value = Number(field && field.value);
                      return Number.isFinite(value) ? value : fallback;
                  }
                  function osgeClampDisplayValue(field, value) {
                      let next = Number(value);
                      if (!Number.isFinite(next)) {
                          next = Number(field.value || field.getAttribute("value") || 0);
                      }
                      const min = Number(field.min);
                      const max = Number(field.max);
                      if (Number.isFinite(min)) {
                          next = Math.max(min, next);
                      }
                      if (Number.isFinite(max)) {
                          next = Math.min(max, next);
                      }
                      return next;
                  }
                  function osgeSetDisplayField(id, value) {
                      const range = document.getElementById(id);
                      const number = document.getElementById(`${id}-number`);
                      const source = range || number;
                      if (!source || value === undefined || value === null) {
                          return;
                      }
                      const next = osgeClampDisplayValue(source, value);
                      if (range) {
                          range.value = next;
                      }
                      if (number) {
                          number.value = next;
                      }
                  }
                  function osgeBindRangePair(id) {
                      const range = document.getElementById(id);
                      const number = document.getElementById(`${id}-number`);
                      if (!range || !number) {
                          return;
                      }
                      const syncFrom = function (source, target) {
                          target.value = osgeClampDisplayValue(source, source.value);
                          source.value = target.value;
                          osgeApplyDisplaySettings();
                      };
                      range.addEventListener("input", function () { syncFrom(range, number); });
                      range.addEventListener("change", function () { syncFrom(range, number); });
                      number.addEventListener("input", function () { syncFrom(number, range); });
                      number.addEventListener("change", function () { syncFrom(number, range); });
                  }
                  const OSGE_DISPLAY_STORAGE_KEY = "osge.displaySettings.v7";
                  const OSGE_LEGACY_DISPLAY_STORAGE_KEYS = ["osge.displaySettings.v6", "osge.displaySettings.v5", "osge.displaySettings.v4", "osge.displaySettings.v3"];
                  function osgeDisplaySettings() {
                      return {
                          nodeFontSize: osgeReadDisplayNumber("osge-node-font-size", 18),
                          edgeLabelSize: osgeReadDisplayNumber("osge-edge-label-size", 11),
                          nodeSizeScale: osgeReadDisplayNumber("osge-node-size-scale", 100),
                          lineWidthScale: osgeReadDisplayNumber("osge-line-width-scale", 100),
                          lineWeightImpact: osgeReadDisplayNumber("osge-line-weight-impact", 100),
                          weightDistanceImpact: osgeReadDisplayNumber("osge-weight-distance-impact", 100),
                          hideLowWeightEdges: osgeReadChecked("osge-hide-low-weight-edges"),
                          edgeWeightThreshold: osgeReadDisplayNumber("osge-edge-weight-threshold", 0.1),
                          hideLeafAccounts: osgeReadChecked("osge-hide-leaf-accounts"),
                          hideLowWeightNodes: osgeReadChecked("osge-hide-low-weight-nodes"),
                          nodeWeightThreshold: osgeReadDisplayNumber("osge-node-weight-threshold", 1),
                          centerSpacing: osgeReadDisplayNumber("osge-center-spacing", 280),
                          peerSpacing: osgeReadDisplayNumber("osge-peer-spacing", 460),
                          outerSpacing: osgeReadDisplayNumber("osge-outer-spacing", 620),
                          minEdgeLength: osgeReadDisplayNumber("osge-min-edge-length", 150),
                          maxEdgeLength: osgeReadDisplayNumber("osge-max-edge-length", 2200),
                          leafMinDistance: osgeReadDisplayNumber("osge-leaf-min-distance", 230),
                          componentGravity: osgeReadDisplayNumber("osge-component-gravity", 0.16),
                          repulsion: osgeReadDisplayNumber("osge-repulsion", 42000),
                          showEdgeLabels: osgeReadChecked("osge-show-edge-labels")
                      };
                  }
                  function osgeSaveDisplaySettings() {
                      try {
                          window.localStorage.setItem(OSGE_DISPLAY_STORAGE_KEY, JSON.stringify(osgeDisplaySettings()));
                      } catch (error) {
                          // Ignore storage failures in private browsing or locked-down browsers.
                      }
                  }
                  function osgeLoadDisplaySettings() {
                      let saved = null;
                      let savedFromLegacy = false;
                      try {
                          saved = JSON.parse(window.localStorage.getItem(OSGE_DISPLAY_STORAGE_KEY) || "null");
                          if (!saved) {
                              for (const key of OSGE_LEGACY_DISPLAY_STORAGE_KEYS) {
                                  const legacy = JSON.parse(window.localStorage.getItem(key) || "null");
                                  if (legacy) {
                                      savedFromLegacy = true;
                                      saved = Object.assign({weightDistanceImpact: 100}, legacy, {
                                          lineWeightImpact: legacy.lineWidthByWeight === false ? 0 : (legacy.lineWeightImpact || 100)
                                      });
                                      break;
                                  }
                              }
                          }
                      } catch (error) {
                          saved = null;
                      }
                      if (!saved) {
                          return;
                      }
                      if (savedFromLegacy) {
                          saved.hideLowWeightEdges = true;
                          saved.edgeWeightThreshold = 0.1;
                          saved.hideLeafAccounts = false;
                      }
                      const rangeFields = {
                          "osge-node-font-size": saved.nodeFontSize,
                          "osge-edge-label-size": saved.edgeLabelSize,
                          "osge-node-size-scale": saved.nodeSizeScale,
                          "osge-line-width-scale": saved.lineWidthScale,
                          "osge-line-weight-impact": saved.lineWeightImpact,
                          "osge-weight-distance-impact": saved.weightDistanceImpact,
                          "osge-center-spacing": saved.centerSpacing,
                          "osge-peer-spacing": saved.peerSpacing,
                          "osge-outer-spacing": saved.outerSpacing,
                          "osge-min-edge-length": saved.minEdgeLength,
                          "osge-max-edge-length": saved.maxEdgeLength,
                          "osge-leaf-min-distance": saved.leafMinDistance,
                          "osge-component-gravity": saved.componentGravity,
                          "osge-repulsion": saved.repulsion
                      };
                      Object.entries(rangeFields).forEach(function ([id, value]) {
                          osgeSetDisplayField(id, value);
                      });
                      const showEdgeLabels = document.getElementById("osge-show-edge-labels");
                      if (showEdgeLabels && typeof saved.showEdgeLabels === "boolean") {
                          showEdgeLabels.checked = saved.showEdgeLabels;
                      }
                      const hideLowWeightEdges = document.getElementById("osge-hide-low-weight-edges");
                      if (hideLowWeightEdges && typeof saved.hideLowWeightEdges === "boolean") {
                          hideLowWeightEdges.checked = saved.hideLowWeightEdges;
                      }
                      const edgeWeightThreshold = document.getElementById("osge-edge-weight-threshold");
                      if (edgeWeightThreshold && saved.edgeWeightThreshold !== undefined) {
                          edgeWeightThreshold.value = osgeClampDisplayValue(edgeWeightThreshold, saved.edgeWeightThreshold);
                      }
                      const hideLeafAccounts = document.getElementById("osge-hide-leaf-accounts");
                      if (hideLeafAccounts && typeof saved.hideLeafAccounts === "boolean") {
                          hideLeafAccounts.checked = saved.hideLeafAccounts;
                      }
                      const hideLowWeightNodes = document.getElementById("osge-hide-low-weight-nodes");
                      if (hideLowWeightNodes && typeof saved.hideLowWeightNodes === "boolean") {
                          hideLowWeightNodes.checked = saved.hideLowWeightNodes;
                      }
                      const nodeWeightThreshold = document.getElementById("osge-node-weight-threshold");
                      if (nodeWeightThreshold && saved.nodeWeightThreshold !== undefined) {
                          nodeWeightThreshold.value = osgeClampDisplayValue(nodeWeightThreshold, saved.nodeWeightThreshold);
                      }
                  }
                  window.osgeResetDisplaySettings = function () {
                      try {
                          window.localStorage.removeItem(OSGE_DISPLAY_STORAGE_KEY);
                          OSGE_LEGACY_DISPLAY_STORAGE_KEYS.forEach(function (key) {
                              window.localStorage.removeItem(key);
                          });
                      } catch (error) {
                          // Ignore storage failures.
                      }
                      const defaults = {
                          "osge-node-font-size": 18,
                          "osge-edge-label-size": 11,
                          "osge-node-size-scale": 100,
                          "osge-line-width-scale": 100,
                          "osge-line-weight-impact": 100,
                          "osge-weight-distance-impact": 100,
                          "osge-center-spacing": 280,
                          "osge-peer-spacing": 460,
                          "osge-outer-spacing": 620,
                          "osge-min-edge-length": 150,
                          "osge-max-edge-length": 2200,
                          "osge-leaf-min-distance": 230,
                          "osge-component-gravity": 0.16,
                          "osge-repulsion": 42000
                      };
                      Object.entries(defaults).forEach(function ([id, value]) {
                          osgeSetDisplayField(id, value);
                      });
                      const showEdgeLabels = document.getElementById("osge-show-edge-labels");
                      if (showEdgeLabels) {
                          showEdgeLabels.checked = true;
                      }
                      const hideLowWeightEdges = document.getElementById("osge-hide-low-weight-edges");
                      if (hideLowWeightEdges) {
                          hideLowWeightEdges.checked = true;
                      }
                      const edgeWeightThreshold = document.getElementById("osge-edge-weight-threshold");
                      if (edgeWeightThreshold) {
                          edgeWeightThreshold.value = 0.1;
                      }
                      const hideLeafAccounts = document.getElementById("osge-hide-leaf-accounts");
                      if (hideLeafAccounts) {
                          hideLeafAccounts.checked = false;
                      }
                      const hideLowWeightNodes = document.getElementById("osge-hide-low-weight-nodes");
                      if (hideLowWeightNodes) {
                          hideLowWeightNodes.checked = false;
                      }
                      const nodeWeightThreshold = document.getElementById("osge-node-weight-threshold");
                      if (nodeWeightThreshold) {
                          nodeWeightThreshold.value = 1;
                      }
                      osgeApplyDisplaySettings();
                  };
                  function osgeApplyGraphFilters(settings) {
                      const nodeThreshold = Math.max(Number(settings.nodeWeightThreshold || 0), 0);
                      const edgeThreshold = Math.max(Number(settings.edgeWeightThreshold || 0), 0);
                      const filterKey = [
                          settings.hideLowWeightNodes ? `node1:${nodeThreshold}` : "node0",
                          settings.hideLowWeightEdges ? `edge1:${edgeThreshold}` : "edge0",
                          settings.hideLeafAccounts ? "leaf1" : "leaf0"
                      ].join(":");
                      if (filterKey === osgeActiveNodeFilterKey) {
                          return false;
                      }
                      osgeActiveNodeFilterKey = filterKey;
                      const edgeFilteredEdges = OSGE_ALL_EDGES.filter(function (edge) {
                          return !settings.hideLowWeightEdges
                              || Number(edge.edge_weight || 0) >= edgeThreshold;
                      });
                      const edgeVisibleIds = new Set();
                      const visibleEdgeDegree = new Map();
                      edgeFilteredEdges.forEach(function (edge) {
                          edgeVisibleIds.add(edge.from);
                          edgeVisibleIds.add(edge.to);
                          visibleEdgeDegree.set(edge.from, (visibleEdgeDegree.get(edge.from) || 0) + 1);
                          visibleEdgeDegree.set(edge.to, (visibleEdgeDegree.get(edge.to) || 0) + 1);
                      });
                      const visibleIds = new Set();
                      OSGE_ALL_NODES.forEach(function (node) {
                          const weightedDegree = Number(node.weighted_degree || 0);
                          const protectedNode = node.id === OSGE_CONFIG.centerId
                              || node.actively_crawled
                              || node.is_target;
                          const keepByNodeWeight = !settings.hideLowWeightNodes
                              || weightedDegree >= nodeThreshold
                              || protectedNode;
                          const keepByEdgeWeight = !settings.hideLowWeightEdges
                              || edgeVisibleIds.has(node.id)
                              || protectedNode;
                          const keepByLeafAccount = !settings.hideLeafAccounts
                              || (visibleEdgeDegree.get(node.id) || 0) > 1
                              || protectedNode;
                          const keep = keepByNodeWeight && keepByEdgeWeight && keepByLeafAccount;
                          if (keep) {
                              visibleIds.add(node.id);
                          }
                      });
                      const visibleEdgeIds = new Set();
                      edgeFilteredEdges.forEach(function (edge) {
                          if (visibleIds.has(edge.from) && visibleIds.has(edge.to)) {
                              visibleEdgeIds.add(edge.id);
                          }
                      });
                      nodes.update(OSGE_ALL_NODES.map(function (node) {
                          return {
                              id: node.id,
                              hidden: !visibleIds.has(node.id)
                          };
                      }));
                      edges.update(OSGE_ALL_EDGES.map(function (edge) {
                          return {
                              id: edge.id,
                              hidden: !visibleEdgeIds.has(edge.id)
                          };
                      }));
                      return true;
                  }
                  function osgeWeightedEdgeLength(edge, baseLength, settings) {
                      const impact = Math.max(settings.weightDistanceImpact || 0, 0) / 100;
                      if (impact <= 0) {
                          return baseLength;
                      }
                      const weight = Math.max(Number(edge.edge_weight || 0), 0);
                      const shrink = Math.log1p(weight) * 0.34 * impact;
                      const lowWeightStretch = Math.max(0, 1 - Math.min(weight, 1)) * 0.75 * impact;
                      const minLength = Math.max(40, Math.min(settings.minEdgeLength || 150, settings.maxEdgeLength || 2200));
                      const maxLength = Math.max(minLength, settings.maxEdgeLength || 2200);
                      return Math.min(maxLength, Math.max(minLength, Math.round(baseLength * (1 + lowWeightStretch) / (1 + shrink))));
                  }
                  let osgeStickyNudgeTimer = null;
                  function osgeStableAngle(value) {
                      let hash = 0;
                      const text = String(value || "");
                      for (let index = 0; index < text.length; index += 1) {
                          hash = ((hash << 5) - hash + text.charCodeAt(index)) | 0;
                      }
                      return (Math.abs(hash) % 360) * Math.PI / 180;
                  }
                  function osgeNudgeStickyLeafNodes() {
                      const currentNodes = nodes.get();
                      const currentEdges = edges.get();
                      if (!currentNodes.length || !currentEdges.length) {
                          return;
                      }
                      const degree = new Map();
                      const neighbor = new Map();
                      currentNodes.forEach(function (node) {
                          degree.set(node.id, 0);
                      });
                      currentEdges.forEach(function (edge) {
                          if (!degree.has(edge.from) || !degree.has(edge.to)) {
                              return;
                          }
                          degree.set(edge.from, degree.get(edge.from) + 1);
                          degree.set(edge.to, degree.get(edge.to) + 1);
                          neighbor.set(edge.from, edge.to);
                          neighbor.set(edge.to, edge.from);
                      });
                      const positions = network.getPositions(currentNodes.map(function (node) { return node.id; }));
                      let moved = 0;
                      const settings = osgeDisplaySettings();
                      const minLeafDistance = Math.max(40, Number(settings.leafMinDistance || 230));
                      currentNodes.forEach(function (node) {
                          if (node.id === OSGE_CONFIG.centerId || degree.get(node.id) !== 1) {
                              return;
                          }
                          const neighborId = neighbor.get(node.id);
                          const nodePos = positions[node.id];
                          const neighborPos = positions[neighborId];
                          if (!nodePos || !neighborPos) {
                              return;
                          }
                          let dx = nodePos.x - neighborPos.x;
                          let dy = nodePos.y - neighborPos.y;
                          let distance = Math.sqrt(dx * dx + dy * dy);
                          if (distance >= minLeafDistance) {
                              return;
                          }
                          if (distance < 1) {
                              const angle = osgeStableAngle(node.id);
                              dx = Math.cos(angle);
                              dy = Math.sin(angle);
                              distance = 1;
                          }
                          const scale = minLeafDistance / distance;
                          network.moveNode(node.id, neighborPos.x + dx * scale, neighborPos.y + dy * scale);
                          moved += 1;
                      });
                      if (moved > 0) {
                          network.startSimulation();
                      }
                  }
                  function osgeScheduleStickyNudge(delay) {
                      if (osgeStickyNudgeTimer) {
                          window.clearTimeout(osgeStickyNudgeTimer);
                      }
                      osgeStickyNudgeTimer = window.setTimeout(osgeNudgeStickyLeafNodes, delay || 180);
                  }
                  function osgeApplyDisplaySettings() {
                      const settings = osgeDisplaySettings();
                      const nodeScale = settings.nodeSizeScale / 100;
                      const lineScale = settings.lineWidthScale / 100;
                      const lineWeightFactor = settings.lineWeightImpact / 100;
                      const averageSpacing = Math.round((settings.centerSpacing + settings.peerSpacing + settings.outerSpacing) / 3);
                      const labelsVisible = settings.showEdgeLabels;
                      const filterChanged = osgeApplyGraphFilters(settings);
                      const styleKey = [
                          settings.nodeFontSize,
                          settings.edgeLabelSize,
                          settings.nodeSizeScale,
                          settings.lineWidthScale,
                          settings.lineWeightImpact,
                          settings.weightDistanceImpact,
                          settings.centerSpacing,
                          settings.peerSpacing,
                          settings.outerSpacing,
                          settings.minEdgeLength,
                          settings.maxEdgeLength,
                          settings.leafMinDistance,
                          settings.componentGravity,
                          settings.repulsion,
                          labelsVisible ? "labels1" : "labels0"
                      ].join(":");
                      const styleChanged = styleKey !== osgeActiveDisplayStyleKey;
                      if (!styleChanged) {
                          osgeSaveDisplaySettings();
                          if (filterChanged) {
                              network.startSimulation();
                              osgeScheduleStickyNudge(320);
                              network.redraw();
                          }
                          return;
                      }
                      osgeActiveDisplayStyleKey = styleKey;
                      network.setOptions({
                          nodes: {
                              font: {
                                  size: settings.nodeFontSize
                              }
                          },
                          edges: {
                              font: {
                                  size: labelsVisible ? settings.edgeLabelSize : 0,
                                  color: labelsVisible ? "#64748b" : "rgba(100, 116, 139, 0)",
                                  strokeWidth: labelsVisible ? 3 : 0,
                                  strokeColor: labelsVisible ? "#f8fafc" : "rgba(248, 250, 252, 0)"
                              },
                              chosen: {
                                  label: labelsVisible
                              }
                          },
                          physics: {
                              barnesHut: {
                                  gravitationalConstant: -settings.repulsion,
                                  centralGravity: settings.componentGravity,
                                  springLength: averageSpacing,
                                  avoidOverlap: 1
                              }
                          }
                      });
                      nodes.update(nodes.get().map(function (node) {
                          return {
                              id: node.id,
                              size: (node.weighted_size || node.base_size || 20) * nodeScale
                          };
                      }));
                      edges.update(edges.get().map(function (edge) {
                          if (!edge.weight_label) {
                              edge.weight_label = edge.label || "";
                          }
                          const baseEdgeLength = edge.spacing_group === "center"
                              ? settings.centerSpacing
                              : edge.spacing_group === "peer"
                                  ? settings.peerSpacing
                                  : settings.outerSpacing;
                          const edgeLength = osgeWeightedEdgeLength(edge, baseEdgeLength, settings);
                          return {
                              id: edge.id,
                              label: labelsVisible ? edge.weight_label : "",
                              width: ((edge.base_width || 1) + ((edge.weighted_width || edge.width || 1) - (edge.base_width || 1)) * lineWeightFactor) * lineScale,
                              length: edgeLength,
                              chosen: {
                                  label: labelsVisible
                              },
                              font: {
                                  size: labelsVisible ? settings.edgeLabelSize : 0,
                                  color: labelsVisible ? "#64748b" : "rgba(100, 116, 139, 0)",
                                  strokeWidth: labelsVisible ? 3 : 0,
                                  strokeColor: labelsVisible ? "#f8fafc" : "rgba(248, 250, 252, 0)"
                              }
                          };
                      }));
                      osgeSaveDisplaySettings();
                      network.startSimulation();
                      osgeScheduleStickyNudge(420);
                      network.redraw();
                  }
                  function osgeBindDisplayControls() {
                      const panel = document.getElementById("osge-display-panel");
                      if (!panel) {
                          return;
                      }
                      osgeLoadDisplaySettings();
                      osgeRangeControlIds().forEach(osgeBindRangePair);
                      [
                          "osge-show-edge-labels",
                          "osge-hide-low-weight-edges",
                          "osge-edge-weight-threshold",
                          "osge-hide-leaf-accounts",
                          "osge-hide-low-weight-nodes",
                          "osge-node-weight-threshold"
                      ].forEach(function (id) {
                          const field = document.getElementById(id);
                          if (field) {
                              field.addEventListener("input", osgeApplyDisplaySettings);
                              field.addEventListener("change", osgeApplyDisplaySettings);
                          }
                      });
                      edges.update(edges.get().map(function (edge) {
                          return {
                              id: edge.id,
                              weight_label: edge.weight_label || edge.label || ""
                          };
                      }));
                      osgeApplyDisplaySettings();
                  }
                  function osgeBindPageSettings() {
                      const displayPanel = document.getElementById("osge-display-panel");
                      if (displayPanel) {
                          displayPanel.addEventListener("toggle", osgeSavePageSettings);
                      }
                      window.addEventListener("beforeunload", function () {
                          osgeSaveDisplaySettings();
                          osgeSavePageSettings();
                      });
                      osgeLoadPageSettings();
                  }
                  function osgeHideNodeDetails() {
                      const panel = document.getElementById("osge-node-panel");
                      if (panel) {
                          panel.classList.add("osge-hidden");
                      }
                      window.osgeSelectedNode = null;
                      window.osgeSelectedIdentityDetail = null;
                  }
                  function osgeRefreshCommand() {
                      const command = document.getElementById("osge-expand-command");
                      if (!command || !window.osgeSelectedNode) {
                          return;
                      }
                      command.textContent = osgeExpandCommand(window.osgeSelectedNode);
                  }
                  function osgeRenderNodeDetails(node, detail) {
                      const panel = document.getElementById("osge-node-panel");
                      if (!panel || !node) {
                          return;
                      }
                      panel.classList.remove("osge-hidden");
                      const selectedAccount = detail && detail.selected_account ? detail.selected_account : node;
                      const profileUrl = selectedAccount.profile_url || node.profile_url || node.url || "";
                      const profileButton = profileUrl
                          ? `<a class="osge-button" href="${osgeEscapeHtml(profileUrl)}" target="_blank" rel="noopener">打开主页 / Open profile</a>`
                          : "";
                      panel.innerHTML = `
                          <h2>${osgeEscapeHtml(osgeAccountDisplayName(selectedAccount))}</h2>
                          <p class="osge-muted">${osgeEscapeHtml(osgePlatformShortName(selectedAccount.platform))} · ${osgeEscapeHtml(osgePlatformDisplayId(selectedAccount))}</p>
                          <p class="osge-section-title">关联平台 / Linked platforms</p>
                          ${osgeLinkedAccountsHtml(detail, node.account_id || node.id)}
                          <p class="osge-section-title">采集状态 / Collection status</p>
                          <dl>
                              ${osgeField("上次采集 / Last collected", selectedAccount.last_crawled_at || node.last_crawled_at)}
                              ${osgeField("采集次数 / Collection count", selectedAccount.crawl_count ?? node.crawl_count)}
                          </dl>
                          <p class="osge-section-title">图谱指标 / Graph metrics</p>
                          <dl>
                              ${osgeField("Weighted degree", selectedAccount.weighted_degree ?? node.weighted_degree)}
                          </dl>
                          <p class="osge-section-title">采集操作 / Collection actions</p>
                          <div class="osge-actions">
                              <button type="button" onclick="osgeRefreshSelectedProfile()">更新信息 / Update info</button>
                              <button type="button" onclick="osgeExpandSelectedNode()">增量更新 / Incremental update</button>
                              ${profileButton}
                          </div>
                          <p id="osge-expand-status" class="osge-status">就绪 / Ready.</p>
                          <p class="osge-section-title">采集设置 / Collection settings</p>
                          <label>作品数量上限 / Max notes <input id="osge-max-notes" type="number" min="1" max="50" value="5" onchange="osgeRefreshCommand()"></label>
                          <label>单作品评论上限 / Comments per note <input id="osge-max-comments" type="number" min="1" max="200" value="10" onchange="osgeRefreshCommand()"></label>
                          <label>采集二级评论 / Collect sub-comments <input id="osge-get-sub-comments" type="checkbox" onchange="osgeRefreshCommand()"></label>
                          <details class="osge-advanced-actions">
                              <summary>高级 / Advanced</summary>
                              <label>强制重新观察 / Force refresh <input id="osge-force-refresh" type="checkbox" onchange="osgeRefreshCommand()"></label>
                              <p class="osge-section-title">后备命令 / Fallback command</p>
                              <code id="osge-expand-command"></code>
                              <div class="osge-actions">
                                  <button type="button" onclick="osgeCopyExpandCommand()">复制命令 / Copy command</button>
                              </div>
                          </details>
                          <p class="osge-section-title">节点管理 / Node management</p>
                          <div class="osge-actions">
                              <button class="osge-secondary-danger" type="button" onclick="osgePruneAdjacentOrphans()">清理节点 / Clean nodes</button>
                              <button class="osge-danger" type="button" onclick="osgeDeleteSelectedAccount()">隐藏账号 / Hide account</button>
                          </div>
                      `;
                      osgeRefreshCommand();
                  }
                  function osgeShowNodeDetails(node) {
                      const panel = document.getElementById("osge-node-panel");
                      if (!panel || !node) {
                          return;
                      }
                      window.osgeSelectedNode = node;
                      window.osgeSelectedIdentityDetail = null;
                      osgeRenderNodeDetails(node, null);
                      if (!OSGE_CONFIG.apiEnabled) {
                          return;
                      }
                      const accountId = node.account_id || node.id;
                      fetch(`${OSGE_CONFIG.apiBase}/api/account-identity/${encodeURIComponent(accountId)}`)
                          .then(async function (response) {
                              const payload = await response.json();
                              if (!response.ok) {
                                  throw new Error(payload.detail || payload.error || `HTTP ${response.status}`);
                              }
                              if (!window.osgeSelectedNode || (window.osgeSelectedNode.account_id || window.osgeSelectedNode.id) !== accountId) {
                                  return;
                              }
                              window.osgeSelectedIdentityDetail = payload;
                              osgeRenderNodeDetails(node, payload);
                          })
                          .catch(function (error) {
                              osgeSetStatus(`身份信息读取失败 / Identity load failed: ${error.message}`);
                          });
                  }
                  function osgeRefreshAfterMutation(centerId) {
                      window.location.href = osgeGraphUrl(centerId || "", centerId ? osgePlatformFromAccountId(centerId) : osgeCurrentPlatform());
                  }
                  window.osgeToggleDangerMenu = function () {
                      const menu = document.getElementById("osge-danger-menu");
                      if (menu) {
                          menu.classList.toggle("is-open");
                      }
                  };
                  function osgeCacheBustedUrl(url) {
                      if (!url) {
                          return "";
                      }
                      const separator = String(url).includes("?") ? "&" : "?";
                      return `${url}${separator}osge_avatar_ts=${Date.now()}`;
                  }
                  function osgeUpdateAvatarInAccount(account, accountId, avatarLocalUrl) {
                      if (!account || (account.account_id || account.id) !== accountId) {
                          return;
                      }
                      account.avatar_local_url = avatarLocalUrl;
                      account.avatar_image_url = avatarLocalUrl;
                  }
                  function osgeApplyAvatarUpdate(accountId, avatarLocalUrl) {
                      if (!accountId || !avatarLocalUrl) {
                          return;
                      }
                      const displayUrl = osgeCacheBustedUrl(avatarLocalUrl);
                      const graphNode = nodes.get(accountId);
                      if (graphNode) {
                          nodes.update({
                              id: accountId,
                              image: displayUrl,
                              shape: "circularImage",
                              avatar_local_url: avatarLocalUrl,
                              avatar_image_url: avatarLocalUrl
                          });
                      }
                      if (window.osgeSelectedNode) {
                          osgeUpdateAvatarInAccount(window.osgeSelectedNode, accountId, avatarLocalUrl);
                      }
                      if (window.osgeSelectedIdentityDetail) {
                          osgeUpdateAvatarInAccount(window.osgeSelectedIdentityDetail.selected_account, accountId, avatarLocalUrl);
                          if (Array.isArray(window.osgeSelectedIdentityDetail.linked_accounts)) {
                              window.osgeSelectedIdentityDetail.linked_accounts.forEach(function (account) {
                                  osgeUpdateAvatarInAccount(account, accountId, avatarLocalUrl);
                              });
                          }
                      }
                      document.querySelectorAll("[data-avatar-account]").forEach(function (element) {
                          if (element.getAttribute("data-avatar-account") !== accountId) {
                              return;
                          }
                          if (element.tagName === "IMG") {
                              element.src = displayUrl;
                          }
                          if (element.tagName === "BUTTON") {
                              element.disabled = false;
                              element.textContent = "刷新头像 / Refresh avatar";
                          }
                      });
                      if (window.osgeSelectedNode) {
                          osgeRenderNodeDetails(window.osgeSelectedNode, window.osgeSelectedIdentityDetail);
                      }
                  }
                  window.osgeRefreshAvatar = async function (accountId, trigger) {
                      if (!accountId || !OSGE_CONFIG.apiEnabled) {
                          return;
                      }
                      const previousText = trigger && trigger.textContent;
                      if (trigger) {
                          trigger.textContent = "正在刷新... / Refreshing...";
                          trigger.disabled = true;
                      }
                      try {
                          const response = await fetch(`${OSGE_CONFIG.apiBase}/api/account-avatar-refresh/${encodeURIComponent(accountId)}`, {
                              method: "POST"
                          });
                          const payload = await response.json();
                          if (!response.ok) {
                              throw new Error(payload.detail || payload.error || `HTTP ${response.status}`);
                          }
                          if (payload.avatar_local_url) {
                              osgeApplyAvatarUpdate(accountId, payload.avatar_local_url);
                              osgeSetStatus("头像缓存已刷新。 / Avatar cache refreshed.");
                              return;
                          }
                          throw new Error(payload.error || "avatar cache failed");
                      } catch (error) {
                          osgeSetStatus(`头像刷新失败 / Avatar refresh failed: ${error.message}`);
                          if (trigger) {
                              trigger.textContent = previousText || "刷新头像 / Refresh avatar";
                              trigger.disabled = false;
                          }
                      }
                  };
                  window.osgeHandleAvatarError = async function (image, accountId) {
                      if (!image) {
                          return;
                      }
                      image.onerror = null;
                      const remoteUrl = image.getAttribute("data-remote-avatar") || "";
                      if (accountId && OSGE_CONFIG.apiEnabled) {
                          try {
                              const response = await fetch(`${OSGE_CONFIG.apiBase}/api/account-avatar-refresh/${encodeURIComponent(accountId)}`, {
                                  method: "POST"
                              });
                              const payload = await response.json();
                              if (response.ok && payload.avatar_local_url) {
                                  osgeApplyAvatarUpdate(accountId, payload.avatar_local_url);
                                  return;
                              }
                          } catch (error) {
                              // Fall through to selected-account remote fallback.
                          }
                      }
                      if (remoteUrl) {
                          image.src = remoteUrl;
                      }
                  };
                  window.osgeRefreshSelectedProfile = async function () {
                      const node = window.osgeSelectedNode;
                      if (!node) {
                          osgeSetStatus("请先选择一个节点。 / Select a node first.");
                          return;
                      }
                      if (!OSGE_CONFIG.apiEnabled) {
                          osgeSetStatus("该 HTML 未启用后台 API，无法更新信息。 / Backend API is not enabled.");
                          return;
                      }
                      const accountId = node.account_id || node.id;
                      osgeSetStatus("正在更新个人主页信息... / Updating profile info...");
                      try {
                          const response = await fetch(`${OSGE_CONFIG.apiBase}/api/account-profile-refresh/${encodeURIComponent(accountId)}`, {
                              method: "POST"
                          });
                          const payload = await response.json();
                          if (!response.ok) {
                              throw new Error(payload.detail || payload.error || `HTTP ${response.status}`);
                          }
                          osgeSetStatus("个人信息已更新，正在刷新图谱... / Profile updated; refreshing...");
                          osgeRefreshAfterMutation(payload.target_id || accountId);
                      } catch (error) {
                          osgeSetStatus(`更新信息失败 / Profile update failed: ${error.message}`);
                      }
                  };
                  window.osgePruneAdjacentOrphans = function () {
                      const node = window.osgeSelectedNode;
                      if (!node) {
                          osgeSetStatus("请先选择一个节点。 / Select a node first.");
                          return;
                      }
                      if (!OSGE_CONFIG.apiEnabled) {
                          osgeSetStatus("该 HTML 未启用后台 API，无法清理。 / Backend API is not enabled.");
                          return;
                      }
                      const label = node.label || node.nickname || node.username || node.id;
                      const accountId = node.account_id || node.id;
                      const confirmed = window.confirm(
                          `保留当前账号：${label}\\n\\n` +
                          "只隐藏当前账号相连的孤立叶子节点；当前账号和非孤立关系会保留。\\n\\n" +
                          "Continue hiding adjacent orphan nodes?"
                      );
                      if (!confirmed) {
                          return;
                      }
                      osgeSetStatus("正在清理相邻孤立节点... / Cleaning adjacent orphan nodes...");
                      fetch(`${OSGE_CONFIG.apiBase}/api/account-orphans/${encodeURIComponent(accountId)}/prune`, {
                          method: "POST"
                      })
                          .then(async function (response) {
                              const payload = await response.json();
                              if (!response.ok) {
                                  throw new Error(payload.detail || payload.error || `HTTP ${response.status}`);
                              }
                              const pruned = payload.pruned || {};
                              const hidden = pruned.hidden_accounts || pruned.deleted_accounts || [];
                              osgeSetStatus(`已清理 ${hidden.length} 个孤立节点，正在刷新... / Cleaned; refreshing...`);
                              osgeRefreshAfterMutation(accountId);
                          })
                          .catch(function (error) {
                              osgeSetStatus(`清理失败 / Prune failed: ${error.message}`);
                          });
                  };
                  window.osgeDeleteSelectedAccount = function () {
                      const node = window.osgeSelectedNode;
                      if (!node) {
                          osgeSetStatus("请先选择一个节点。 / Select a node first.");
                          return;
                      }
                      if (!OSGE_CONFIG.apiEnabled) {
                          osgeSetStatus("该 HTML 未启用后台 API，无法隐藏。 / Backend API is not enabled.");
                          return;
                      }
                      const label = node.label || node.nickname || node.username || node.id;
                      const accountId = node.account_id || node.id;
                      const confirmed = window.confirm(
                          `隐藏平台账号节点：${label}\\n\\n` +
                          "这会将该账号标记为隐藏；数据库记录会保留，但图谱、搜索和前端视图不再展示它。" +
                          "隐藏后变成孤立且未被保护的相邻节点也会被隐藏。\\n\\n" +
                          "同一身份下的其他平台账号不会被隐藏。\\n\\n" +
                          "Hide this platform account node?"
                      );
                      if (!confirmed) {
                          return;
                      }
                      osgeSetStatus("正在隐藏节点... / Hiding node...");
                      fetch(`${OSGE_CONFIG.apiBase}/api/accounts/${encodeURIComponent(accountId)}`, {
                          method: "DELETE"
                      })
                          .then(async function (response) {
                              const payload = await response.json();
                              if (!response.ok) {
                                  throw new Error(payload.detail || payload.error || `HTTP ${response.status}`);
                              }
                              const hiddenResult = payload.deleted || {};
                              const hidden = hiddenResult.hidden_accounts || hiddenResult.deleted_accounts || [];
                              osgeSetStatus(`已隐藏 ${hidden.length || 1} 个节点，正在刷新... / Hidden; refreshing...`);
                              osgeRefreshAfterMutation("");
                          })
                          .catch(function (error) {
                              osgeSetStatus(`隐藏失败 / Hide failed: ${error.message}`);
                          });
                  };
                  window.osgeCopyExpandCommand = function () {
                      const command = document.getElementById("osge-expand-command");
                      if (!command) {
                          return;
                      }
                      navigator.clipboard.writeText(command.textContent || "");
                  };
                  window.osgeExpandSelectedNode = async function () {
                      const node = window.osgeSelectedNode;
                      if (!node) {
                          osgeSetStatus("请先选择一个节点。 / Select a node first.");
                          return;
                      }
                      if (!OSGE_CONFIG.apiEnabled) {
                          osgeSetStatus("该 HTML 未启用后台 API，请使用后备命令。 / Backend API is not enabled; use the fallback command.");
                          return;
                      }
                      osgeSetStatus("正在提交增量更新任务... / Submitting incremental update job...");
                      try {
                          const response = await fetch(`${OSGE_CONFIG.apiBase}/api/expand`, {
                              method: "POST",
                              headers: {"Content-Type": "application/json"},
                              body: JSON.stringify({
                                  account_id: node.account_id || node.id,
                                  platform: node.platform || "",
                                  max_notes: osgeReadNumber("osge-max-notes", 5),
                                  max_comments: osgeReadNumber("osge-max-comments", 10),
                                  get_sub_comments: osgeReadChecked("osge-get-sub-comments"),
                                  force: osgeReadChecked("osge-force-refresh")
                              })
                          });
                          const payload = await response.json();
                          if (!response.ok) {
                              throw new Error(payload.detail || payload.error || `HTTP ${response.status}`);
                          }
                          if (payload.skipped) {
                              osgeSetStatus(`已跳过 / Skipped: ${payload.reason || "already crawled"}`);
                              return;
                          }
                          osgeSetStatus(`任务已提交 / Job submitted: ${payload.job_id}. 正在启动增量采集...`);
                          osgePollJob(payload.job_id, node.account_id || node.id);
                      } catch (error) {
                          osgeSetStatus(`无法启动任务 / Could not start job: ${error.message}.`);
                      }
                  };
                  window.osgeCrawlPlatformProfile = async function (event) {
                      if (event) {
                          event.preventDefault();
                      }
	                      const input = document.getElementById("osge-crawl-account-input");
	                      const value = String((input && input.value) || "").trim();
	                      if (!value) {
	                          const prefixes = osgePlatforms().map(function (platform) {
	                              return `${platform.id}:`;
	                          }).join(" / ");
	                          osgeSetSearchStatus(`请输入平台主页/短链 URL，或使用 ${prefixes} 前缀。 / Enter a profile/share URL or prefixed platform id.`);
	                          return;
	                      }
                      if (!OSGE_CONFIG.apiEnabled) {
                          osgeSetSearchStatus("该 HTML 未启用后台 API。 / Backend API is not enabled.");
                          return;
                      }
                          osgeSetSearchStatus("正在提交抓取任务... / Submitting crawl job...");
                      try {
                          const response = await fetch(`${OSGE_CONFIG.apiBase}/api/expand`, {
                              method: "POST",
                              headers: {"Content-Type": "application/json"},
                              body: JSON.stringify({
                                  account_id: value,
                                  platform: osgeCurrentPlatform(),
                                  max_notes: 5,
                                  max_comments: 10,
                                  get_sub_comments: false,
                                  force: false
                              })
                          });
                          const payload = await response.json();
                          if (!response.ok) {
                              throw new Error(payload.detail || payload.error || `HTTP ${response.status}`);
                          }
                          if (payload.skipped) {
                              osgeSetSearchStatus(`已跳过 / Skipped: ${payload.reason || "already crawled"}`);
                              window.location.href = osgeGraphUrl(payload.target_id, osgePlatformFromAccountId(payload.target_id));
                              return;
                          }
                          osgeSetSearchStatus(`任务已提交 / Job submitted: ${payload.job_id}.`);
                          osgePollJob(payload.job_id, payload.target_id);
                      } catch (error) {
                          osgeSetSearchStatus(`无法启动任务 / Could not start job: ${error.message}`);
                      }
                  };
                  window.osgeSearchLocalAccounts = async function (event) {
                      if (event) {
                          event.preventDefault();
                      }
                      const input = document.getElementById("osge-local-search-input");
                      const results = document.getElementById("osge-local-search-results");
                      const value = String((input && input.value) || "").trim();
                      if (!results) {
                          return;
                      }
                      if (!value) {
                          results.innerHTML = "";
                          return;
                      }
                      results.innerHTML = `<span class="osge-result-meta">正在搜索... / Searching...</span>`;
                      try {
                          const response = await fetch(`${OSGE_CONFIG.apiBase}/api/accounts/search?q=${encodeURIComponent(value)}`);
                          const payload = await response.json();
                          if (!response.ok) {
                              throw new Error(payload.detail || payload.error || `HTTP ${response.status}`);
                          }
                          const matches = payload.results || [];
                          if (!matches.length) {
                              results.innerHTML = `<span class="osge-result-meta">没有匹配结果 / No local matches.</span>`;
                              return;
                          }
                          results.innerHTML = matches.map(function (item) {
                              const meta = [
                                  item.account_id,
                                  osgePlatformName(item.platform),
                                  item.location || ""
                              ].filter(Boolean).join(" · ");
                              const accountId = JSON.stringify(item.account_id || "");
                              return `
                                  <button type="button" onclick='osgeFocusAccount(${accountId})'>
                                      ${osgeResultAvatarHtml(item)}
                                      <span class="osge-result-body">
                                          ${osgeEscapeHtml(osgeResultLabel(item))}
                                          <span class="osge-result-meta">${osgeEscapeHtml(meta)}</span>
                                      </span>
                                  </button>
                              `;
                          }).join("");
                      } catch (error) {
                          results.innerHTML = `<span class="osge-result-meta">搜索失败 / Search failed: ${osgeEscapeHtml(error.message)}</span>`;
                      }
                  };
                  async function osgePollJob(jobId, centerId) {
                      try {
                          const response = await fetch(`${OSGE_CONFIG.apiBase}/api/jobs/${encodeURIComponent(jobId)}`);
                          const payload = await response.json();
                          if (!response.ok) {
                              throw new Error(payload.detail || payload.error || `HTTP ${response.status}`);
                          }
                          const suffix = payload.error ? ` (${payload.error})` : "";
                          const detail = payload.detail || `任务状态 / Job ${payload.status}${suffix}`;
                          osgeSetStatus(detail);
                          if (payload.status === "completed") {
                              window.location.href = osgeGraphUrl(centerId, osgePlatformFromAccountId(centerId));
                              return;
                          }
                          if (payload.status === "failed") {
                              return;
                          }
                          window.setTimeout(function () { osgePollJob(jobId, centerId); }, 2500);
                      } catch (error) {
                          osgeSetStatus(`无法读取任务状态 / Could not read job status: ${error.message}`);
                      }
                  }
                  network.on("click", function (params) {
                      if (params.nodes.length === 1) {
                          osgeShowNodeDetails(nodes.get(params.nodes[0]));
                      } else if (params.edges.length === 1) {
                          osgeShowEdgeDetails(edges.get(params.edges[0]));
                      } else {
                          osgeHideNodeDetails();
                          osgeCollapseAmbientPanels();
                      }
                  });
                  network.on("doubleClick", function (params) {
                      if (params.nodes.length === 1) {
                          const node = nodes.get(params.nodes[0]);
                          if (node && node.url) {
                              window.open(node.url, "_blank", "noopener");
                          }
                      }
                  });
                  network.on("dragStart", osgeCancelAutoCenter);
                  network.on("zoom", osgeCancelAutoCenter);
	                  osgeInitializePlatformUi();
                  network.once("stabilized", function () {
                      osgeScheduleStickyNudge(120);
                  });
                  if (OSGE_CONFIG.centerId) {
                      let osgeInitialCenterDone = false;
                      const clearCenterUrl = function () {
                          if (window.location.search.includes("center=")) {
                              window.history.replaceState(null, "", `/graph?platform=${encodeURIComponent(osgeCurrentPlatform())}`);
                          }
                      };
                      const osgeTryInitialCenter = function () {
                          if (osgeInitialCenterDone || osgeAutoCenterCanceled) {
                              return;
                          }
                          const node = nodes.get(OSGE_CONFIG.centerId);
                          if (node) {
                              osgeInitialCenterDone = true;
                              osgeCenterAccountNode(OSGE_CONFIG.centerId, node, {auto: true});
                              clearCenterUrl();
                          }
                      };
                      network.once("stabilized", osgeTryInitialCenter);
                      window.setTimeout(function () {
                          osgeTryInitialCenter();
                      }, 1200);
                  } else {
                      network.once("stabilized", function () {
                          window.setTimeout(function () {
                              const position = network.getViewPosition();
                              network.moveTo({
                                  position: position,
                                  scale: 0.72,
                                  animation: {duration: 260, easingFunction: "easeInOutQuad"}
                              });
                          }, 80);
                      });
                  }
                  osgeBindDisplayControls();
                  osgeBindPageSettings();
