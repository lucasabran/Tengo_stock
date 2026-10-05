const usersListEl = document.getElementById("users-list");
const rolesListEl = document.getElementById("roles-list");

let roles = [];
let catalog = [];
let editingUserId = null;
let editingRoleId = null;

// --- pestañas ---
document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b === btn));
    document.getElementById("tab-users").classList.toggle("hidden", btn.dataset.tab !== "users");
    document.getElementById("tab-roles").classList.toggle("hidden", btn.dataset.tab !== "roles");
    document.getElementById("tab-tools").classList.toggle("hidden", btn.dataset.tab !== "tools");
  });
});

// --- clave temporal ---
const secretDialog = document.getElementById("secret-dialog");
function showSecret(title, text, value) {
  document.getElementById("secret-title").textContent = title;
  document.getElementById("secret-text").textContent = text;
  document.getElementById("secret-value").textContent = value;
  secretDialog.showModal();
}
document.getElementById("secret-copy").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(document.getElementById("secret-value").textContent);
    toast("Copiada", "success", 1500);
  } catch (e) {
    toast("No se pudo copiar, seleccionala a mano", "error");
  }
});

// --- usuarios ---
function formatLastLogin(iso) {
  return iso ? `Ultimo ingreso: ${formatDateTime(iso)}` : "Nunca ingreso";
}

function renderUsers(users) {
  usersListEl.innerHTML = "";
  for (const u of users) {
    const row = document.createElement("div");
    row.className = "list-row user-row" + (u.active ? "" : " user-inactive");
    const badges = [
      u.is_owner ? '<span class="badge badge-owner">Dueño</span>' : `<span class="badge">${escapeHtml(u.role_name || "Sin rol")}</span>`,
      u.active ? "" : '<span class="badge badge-off">Desactivado</span>',
      u.must_change_password ? '<span class="badge badge-warn">Debe cambiar clave</span>' : "",
    ].join(" ");
    row.innerHTML = `
      <div>
        <div class="list-row-title">${escapeHtml(u.full_name)} <span class="card-sku">@${escapeHtml(u.username)}</span></div>
        <div class="list-row-sub">${badges}</div>
        <div class="list-row-sub">${formatLastLogin(u.last_login)}</div>
      </div>
      <div class="row-actions">
        <button type="button" class="btn-secondary" data-act="edit">Editar</button>
        <button type="button" class="btn-secondary" data-act="reset">Resetear clave</button>
      </div>
    `;
    row.querySelector('[data-act="edit"]').addEventListener("click", () => openUser(u));
    row.querySelector('[data-act="reset"]').addEventListener("click", () => resetPassword(u));
    usersListEl.appendChild(row);
  }
}

async function loadUsers() {
  renderUsers(await fetchJSON("/api/users"));
}

const userDialog = document.getElementById("user-dialog");
const userForm = document.getElementById("user-form");
const userError = document.getElementById("user-error");

function fillRoleSelect(selectedId) {
  const sel = document.getElementById("u-role");
  sel.innerHTML = roles.map((r) => `<option value="${r.id}">${escapeHtml(r.name)}</option>`).join("");
  if (selectedId) sel.value = String(selectedId);
}

function openUser(user) {
  editingUserId = user ? user.id : null;
  userError.classList.add("hidden");
  userForm.reset();
  document.getElementById("user-title").textContent = user ? `Editar ${user.username}` : "Nuevo usuario";
  const username = document.getElementById("u-username");
  username.value = user ? user.username : "";
  username.disabled = !!user;
  document.getElementById("u-fullname").value = user ? user.full_name : "";
  fillRoleSelect(user ? user.role_id : null);
  document.getElementById("u-role").disabled = !!(user && user.is_owner);
  document.getElementById("u-password-label").classList.toggle("hidden", !!user);
  const activeLabel = document.getElementById("u-active-label");
  activeLabel.classList.toggle("hidden", !user || user.is_owner);
  document.getElementById("u-active").checked = user ? user.active : true;
  userDialog.showModal();
}

document.getElementById("btn-new-user").addEventListener("click", () => openUser(null));
document.getElementById("user-cancel").addEventListener("click", () => userDialog.close());

userForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  userError.classList.add("hidden");
  const body = {
    full_name: document.getElementById("u-fullname").value.trim(),
    role_id: Number(document.getElementById("u-role").value),
  };
  try {
    if (editingUserId) {
      body.active = document.getElementById("u-active").checked;
      await fetchJSON(`/api/users/${editingUserId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      userDialog.close();
      toast("Usuario actualizado", "success");
    } else {
      body.username = document.getElementById("u-username").value.trim();
      body.password = document.getElementById("u-password").value.trim();
      const res = await fetchJSON("/api/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      userDialog.close();
      showSecret(`Usuario ${res.user.username} creado`, "Clave para el primer ingreso:", res.temp_password);
    }
  } catch (err) {
    userError.textContent = errorMessage(err);
    userError.classList.remove("hidden");
    return;
  }
  loadUsers();
  loadRoles();
});

async function resetPassword(user) {
  const ok = await confirmDialog(`Generar una clave nueva para ${user.username}? Se cierra su sesion actual.`);
  if (!ok) return;
  try {
    const res = await fetchJSON(`/api/users/${user.id}/reset-password`, { method: "POST" });
    showSecret(`Clave nueva de ${user.username}`, "Pasale esta clave:", res.temp_password);
    loadUsers();
  } catch (err) {
    toast(errorMessage(err), "error");
  }
}

// --- roles ---
function permLabel(key) {
  const p = catalog.find((x) => x.key === key);
  return p ? p.label : key;
}

function renderRoles() {
  rolesListEl.innerHTML = "";
  for (const r of roles) {
    const row = document.createElement("div");
    row.className = "list-row";
    row.innerHTML = `
      <div>
        <div class="list-row-title">${escapeHtml(r.name)} ${r.is_system ? '<span class="badge">Sistema</span>' : ""}</div>
        <div class="list-row-sub">${escapeHtml(r.description || "")}</div>
        <div class="list-row-sub">${r.permissions.length} permisos &middot; ${r.user_count} usuario(s)</div>
      </div>
      <div class="row-actions">
        <button type="button" class="btn-secondary" data-act="edit">${r.is_system ? "Ver" : "Editar"}</button>
        ${r.is_system ? "" : '<button type="button" class="btn-secondary" data-act="delete">Eliminar</button>'}
      </div>
    `;
    row.querySelector('[data-act="edit"]').addEventListener("click", () => openRole(r));
    const del = row.querySelector('[data-act="delete"]');
    if (del) del.addEventListener("click", () => deleteRole(r));
    rolesListEl.appendChild(row);
  }
}

async function loadRoles() {
  roles = await fetchJSON("/api/roles");
  renderRoles();
}

const roleDialog = document.getElementById("role-dialog");
const roleForm = document.getElementById("role-form");
const roleError = document.getElementById("role-error");
const permsEl = document.getElementById("r-perms");

function openRole(role) {
  editingRoleId = role ? role.id : null;
  roleError.classList.add("hidden");
  document.getElementById("role-title").textContent = role ? (role.is_system ? `Rol ${role.name}` : `Editar ${role.name}`) : "Nuevo rol";
  const nameEl = document.getElementById("r-name");
  nameEl.value = role ? role.name : "";
  nameEl.disabled = !!(role && role.is_system);
  document.getElementById("r-description").value = role ? role.description : "";
  const selected = new Set(role ? role.permissions : []);
  const locked = !!(role && role.is_system);
  const groups = [...new Set(catalog.map((p) => p.group))];
  permsEl.innerHTML = groups
    .map(
      (g) => `
      <fieldset class="perm-group">
        <legend>${escapeHtml(g)}</legend>
        ${catalog
          .filter((p) => p.group === g)
          .map(
            (p) => `<label class="check-row"><input type="checkbox" value="${p.key}" ${selected.has(p.key) ? "checked" : ""} ${locked ? "disabled" : ""}> ${escapeHtml(p.label)}</label>`
          )
          .join("")}
      </fieldset>`
    )
    .join("");
  roleDialog.showModal();
}

document.getElementById("btn-new-role").addEventListener("click", () => openRole(null));
document.getElementById("role-cancel").addEventListener("click", () => roleDialog.close());

roleForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  roleError.classList.add("hidden");
  const body = {
    name: document.getElementById("r-name").value.trim(),
    description: document.getElementById("r-description").value.trim(),
    permissions: [...permsEl.querySelectorAll("input:checked")].map((i) => i.value),
  };
  try {
    await fetchJSON(editingRoleId ? `/api/roles/${editingRoleId}` : "/api/roles", {
      method: editingRoleId ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (err) {
    roleError.textContent = errorMessage(err);
    roleError.classList.remove("hidden");
    return;
  }
  roleDialog.close();
  toast("Rol guardado. Los usuarios con este rol tienen que volver a ingresar.", "success");
  loadRoles();
});

async function deleteRole(role) {
  const ok = await confirmDialog(`Eliminar el rol ${role.name}?`);
  if (!ok) return;
  try {
    await fetchJSON(`/api/roles/${role.id}`, { method: "DELETE" });
    toast("Rol eliminado", "success");
    loadRoles();
  } catch (err) {
    toast(errorMessage(err), "error");
  }
}

(async function init() {
  catalog = await fetchJSON("/api/permissions");
  await loadRoles();
  await loadUsers();
})();

// --- herramientas ---
document.getElementById("wipe-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const err = document.getElementById("wipe-error");
  err.classList.add("hidden");
  const targets = [...e.target.querySelectorAll("input[type=checkbox]:checked")].map((i) => i.value);
  if (!targets.length) {
    err.textContent = "Marca que datos queres borrar";
    err.classList.remove("hidden");
    return;
  }
  if (!(await confirmDialog("Esto borra los datos seleccionados de forma permanente (queda una copia automatica en el servidor). Continuar?"))) return;
  try {
    const res = await fetchJSON("/api/admin/wipe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ targets, confirm: document.getElementById("wipe-confirm").value }),
    });
    const lines = Object.entries(res.deleted).map(([k, v]) => `${k}: ${v}`).join(", ");
    toast(`Listo. Borrado: ${lines}`, "success", 9000);
    e.target.reset();
  } catch (ex) {
    err.textContent = errorMessage(ex);
    err.classList.remove("hidden");
  }
});
