  // The declared and applied boundary permissions that a fact sheet lists.
  // A part of the Explorer: tools/browser_runtime.py joins the parts of flow/ into one script.
  const boundaryPermissionGroups = new Map();
  let boundaryAuditMarkup = "";

  function boundaryPermissionMarkup(scope = null, related = new Set(), edge = false) {
    const permissions = REPORT_SCENE.boundaryPermissions;
    boundaryPermissionGroups.clear(); boundaryAuditMarkup = "";
    if (!permissions || edge) return "";
    const touches = (row) => scope === null || row.entity_ids?.some((id) => related.has(id))
      || row.component_ids?.includes(scope) || row.routes?.some((route) => route.module_id === scope);
    const inScope = (row) => touches(row) || S.view === "diff" && (row.data
      ? (permissions.declared || []).some((entry) => entry.id === row.declaration_id && touches(entry))
      : (permissions.applied || []).some((entry) => entry.declaration_id === row.id && touches(entry)));
    const kinds = [["declared", "Declared boundary permissions"], ["applied", "Applied boundary permissions"]]
      .filter(([kind]) => kind === "declared" ? S.view !== "diagram" : S.view !== "target");
    const sections = kinds.map(([kind, title]) =>
      boundaryPermissionSection((permissions[kind] || []).filter(inScope), title, kind));
    if (location.hash) queueMicrotask(() => openBoundaryPermissionHash());
    if (scope !== null) return sections.join("");
    const counts = kinds.map(([kind]) => `${(permissions[kind] || []).length} ${kind}`).join(" · ");
    boundaryAuditMarkup = sections.join("");
    return `<section class="boundary-permissions"><h3>Boundary permissions</h3>
      <p class="boundary-permission-counts">${counts}</p>
      <p>Recorded permissions do not establish rule status. Select a scope for relevant records.</p>
      <details data-boundary-audit><summary>Complete boundary permission audit · ${counts}</summary></details></section>`;
  }

  function boundaryPermissionSection(rows, title, kind) {
    if (!rows.length) return "";
    const groups = new Map();
    for (const row of rows) {
      const mapped = row.entity_ids?.length || row.component_ids?.length;
      const rule = row.rule_id || (row.rule_ids || []).join(" · ") || "Rule unavailable";
      const label = mapped ? rule : "Unmapped boundary permission audit";
      if (!groups.has(label)) groups.set(label, []);
      groups.get(label).push(row);
    }
    return `<section class="boundary-permissions"><h3>${title} · ${rows.length}</h3>${[...groups].map(([label, records]) => {
      const key = String(boundaryPermissionGroups.size);
      boundaryPermissionGroups.set(key, { rows: records, applied: kind === "applied" });
      return `<details data-boundary-group="${key}" data-boundary-kind="${kind}"><summary>${esc(label)} · ${REPORT_SCENE.countLabel(records.length, "record")}</summary></details>`;
    }).join("")}</section>`;
  }

  function boundaryPermissionRecordMarkup(row, applied) {
    const selector = applied ? row.data || {} : row;
    return `<details data-boundary-permission="${esc(row.id)}" id="${esc(row.id)}"><summary>${esc(selector.qualified_name || row.title || "Selector unavailable")} · ${esc(selector.position || "Position unavailable")}</summary></details>`;
  }

  function boundaryPermissionDetails(row, applied) {
    const permissions = REPORT_SCENE.boundaryPermissions;
    const routeLink = (route) => {
      const query = new URLSearchParams({component: route.component_id || "unassigned",
        view: S.view, origin: route.origin});
      if (route.module_id) query.set("module", route.module_id);
      if (route.scope_id) query.set("scope", route.scope_id);
      query.set("selected", route.entity_id);
      query.set("return_view", S.view);
      if (atlasLevel().parent_id) query.set("return_scope", atlasLevel().parent_id);
      return `<a href="${esc(`${ATLAS.detail_page || location.pathname}?${query}`)}">${esc(route.label)}</a>`;
    };
    const selector = applied ? row.data || {} : row;
    const declaration = applied && (permissions.declared || []).find((item) => item.id === row.declaration_id);
    const declarationRoute = declaration?.routes?.[0];
    const declarationOwner = declarationRoute?.component_id || declaration?.component_ids?.[0];
    const declarationQuery = new URLSearchParams({component: declarationOwner || "unassigned", origin: "declared", view: "target"});
    if (declarationRoute?.module_id) declarationQuery.set("module", declarationRoute.module_id);
    if (declarationRoute?.scope_id) declarationQuery.set("scope", declarationRoute.scope_id);
    if (declarationRoute?.entity_id) declarationQuery.set("selected", declarationRoute.entity_id);
    const declarationHref = `${ATLAS.detail_page || location.pathname}?${declarationQuery}#${encodeURIComponent(row.declaration_id || "")}`;
    const keys = ["qualified_name", "position", "field_path", "annotation", "container_depth", "mapping_depth", "literal_mapping_arm", "native_mapping", ...(applied ? ["observed_container_depth"] : [])];
    const bindingRows = ["alias_body", "key_alias_body"].flatMap((name) => {
      const binding = selector[name];
      return !Object.hasOwn(selector, name) ? []
        : binding && typeof binding === "object" && !Array.isArray(binding) && Object.keys(binding).length
          ? Object.entries(binding).map(([key, value]) => [`${name}.${key}`, value])
          : [[name, binding]];
    });
    const selectorRows = [...keys.filter((key) => Object.hasOwn(selector, key)).map((key) => [key, selector[key]]), ...bindingRows];
    const ownerLinks = !row.routes?.length ? (row.component_ids || []).map((id) => {
      const query = new URLSearchParams({component: id, origin: "declared", view: "target"});
      return `<a href="${esc(`${ATLAS.detail_page || location.pathname}?${query}`)}">Declared owning component</a>`;
    }).join(" · ") : "";
    return `<dl class="kv">${selectorRows.map(([key, value]) => `<dt>${esc(key === "observed_container_depth" ? "Observed container depth" : key)}</dt><dd><code>${esc(typeof value === "string" ? value : JSON.stringify(value))}</code></dd>`).join("")}</dl>
      <p>${esc(row.rationale || "Rationale unavailable")} · Decided by ${esc(row.decided_by || "Unavailable")}</p>
      ${applied && selector.accepted_opacity === true ? "<p>Accepted opacity; type closure remains unproven.</p>" : ""}
      <p>Recorded ID <code>${esc(row.id)}</code></p>
      ${applied ? `<p>${esc(row.title || "Recorded applied permission")}</p><p>Declaration: ${row.declaration_id ? declarationOwner ? `<a href="${esc(declarationHref)}">${esc(row.declaration_id)}</a>` : `<code>${esc(row.declaration_id)}</code> · Navigation unavailable` : "Unavailable or ambiguous"}</p>` : `<p>Rule <code>${esc(row.rule_id)}</code> · Contract scope <code>${esc(row.contract_scope_id ?? "root")}</code> · Source <code>${esc(row.source ?? "Unavailable")}</code></p>`}
      ${["rule_ids", "fact_ids", "evidence_ids", "provenance"].map((key) => `<p>${esc(key)}: ${(row[key] || []).map(esc).join(" · ") || "Not recorded"}</p>`).join("")}
      <p>${(row.locations || []).map((item) => esc(`${item.file || "Location unavailable"}${item.line != null ? `:${item.line}` : ""} · ${item.id}`)).join("<br>") || "Source evidence location unavailable"}</p>
      <p>${(row.routes || []).map(routeLink).join(" · ")}${ownerLinks || ""}</p>
      ${!row.routes?.length && !row.component_ids?.length ? "<p>Navigation unavailable or ambiguous; retained in root audit.</p>" : ""}
      <p><a href="${esc(ATLAS.architecture_href || NAV?.architecture_href || "architecture.json")}">Complete audit JSON</a></p>
    `;
  }

  function fillBoundaryPermissionGroup(group, limit = 20, requestedId = null) {
    const state = boundaryPermissionGroups.get(group.dataset.boundaryGroup);
    if (!state) return;
    let list = group.querySelector("[data-boundary-record-list]");
    if (!list) {
      list = document.createElement("div"); list.dataset.boundaryRecordList = ""; group.appendChild(list);
    }
    const records = state.rows.slice(Number(group.dataset.boundaryLimit || 0), limit);
    if (requestedId) {
      const requested = state.rows.find((row) => row.id === requestedId);
      if (requested) records.push(requested);
    }
    for (const row of records) {
      if (!document.getElementById(row.id)) list.insertAdjacentHTML("beforeend", boundaryPermissionRecordMarkup(row, state.applied));
    }
    group.dataset.boundaryLimit = String(Math.min(limit, state.rows.length));
    let more = group.querySelector("[data-boundary-more]");
    if (limit < state.rows.length) {
      if (!more) {
        more = document.createElement("button"); more.type = "button"; more.className = "flow-fit";
        more.dataset.boundaryMore = ""; group.appendChild(more);
      }
      more.textContent = `Show next ${Math.min(20, state.rows.length - limit)} records · ${state.rows.length - limit} remaining`;
    } else if (more) {
      const hadFocus = document.activeElement === more;
      more.remove();
      if (hadFocus) list.lastElementChild?.querySelector("summary")?.focus();
    }
  }

  function fillBoundaryPermissionDetails(record) {
    if (record.dataset.boundaryLoaded) return;
    const state = boundaryPermissionGroups.get(record.closest("[data-boundary-group]")?.dataset.boundaryGroup);
    const row = state?.rows.find((item) => item.id === record.dataset.boundaryPermission);
    if (!row) return;
    record.insertAdjacentHTML("beforeend", boundaryPermissionDetails(row, state.applied));
    record.dataset.boundaryLoaded = "true";
  }

  function fillBoundaryPermissionAudit(audit) {
    if (audit.dataset.boundaryLoaded) return;
    audit.insertAdjacentHTML("beforeend", boundaryAuditMarkup);
    audit.dataset.boundaryLoaded = "true";
  }

  function openBoundaryPermissionHash(requestedId = null) {
    let id = requestedId;
    if (id === null) {
      try { id = decodeURIComponent(location.hash.slice(1)); } catch { return false; }
    }
    const entry = [...boundaryPermissionGroups].find(([, state]) => state.rows.some((row) => row.id === id));
    if (!entry) return false;
    const audit = inspectorContent.querySelector("[data-boundary-audit]");
    if (audit) { audit.open = true; fillBoundaryPermissionAudit(audit); }
    const group = inspectorContent.querySelector(`[data-boundary-group="${entry[0]}"]`);
    if (!group) return false;
    group.open = true;
    fillBoundaryPermissionGroup(group, Number(group.dataset.boundaryLimit || 20), id);
    const record = document.getElementById(id);
    record.open = true; fillBoundaryPermissionDetails(record); setTargetDetails(true);
    requestAnimationFrame(() => { if (record.isConnected) record.scrollIntoView(); });
    return true;
  }

  inspectorContent.addEventListener("toggle", (event) => {
    const target = event.target;
    if (!target.open) return;
    if (target.hasAttribute("data-boundary-audit")) fillBoundaryPermissionAudit(target);
    if (target.hasAttribute("data-boundary-group")) fillBoundaryPermissionGroup(target, Number(target.dataset.boundaryLimit || 20));
    if (target.hasAttribute("data-boundary-permission")) fillBoundaryPermissionDetails(target);
  }, true);
  inspectorContent.addEventListener("click", (event) => {
    const more = event.target.closest("[data-boundary-more]");
    if (!more) return;
    const group = more.closest("[data-boundary-group]");
    fillBoundaryPermissionGroup(group, Number(group.dataset.boundaryLimit) + 20);
  });
