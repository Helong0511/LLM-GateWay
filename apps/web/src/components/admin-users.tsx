"use client";

import { Fragment, FormEvent, useEffect, useState } from "react";

import { useI18n } from "@/components/locale-provider";
import { useBootFlash } from "@/lib/boot-flash";
import {
  FlashBanner,
  errFlash,
  loadFlash,
  okFlash,
  warnFlash,
  type FlashMessage,
} from "@/components/ui/flash";

import { PageControls } from "@/components/page-controls";
import { ModelPicker } from "@/components/model-picker";
import { RefreshButton } from "@/components/ui/refresh-button";
import { errorMessage, deleteJson, getJson, postJson } from "@/lib/api-client";
import { apiErrorLabel } from "@/lib/error-label";
import { statusLabel } from "@/lib/status-label";

const PAGE_SIZE = 20;

type AdminUser = {
  id: string;
  email: string;
  status: string;
  roles: string[];
  allowedModels: string[];
  created_at: string;
};

/** 可分配角色（不含超级管理员；普通用户为注册默认角色，不必再分配） */
const ASSIGNABLE = ["support", "finance", "operator", "model_ops", "admin"] as const;

async function pullUsers(
  page: number,
  filters: { q: string; status: string },
  loadFail: string,
): Promise<{ users: AdminUser[]; total: number; message: string }> {
  const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
  if (filters.q.trim()) {
    params.set("q", filters.q.trim());
  }
  if (filters.status) {
    params.set("status", filters.status);
  }
  const result = await getJson(`/api/admin/users?${params.toString()}`);
  if (!result.ok || !result.envelope.data) {
    return { users: [], total: 0, message: errorMessage(result.envelope, loadFail) };
  }
  const raw = result.envelope.data.users;
  const users = Array.isArray(raw)
    ? raw.flatMap((item) => {
      if (!item || typeof item !== "object") {
        return [];
      }
      const row = item as Record<string, unknown>;
      if (typeof row.id !== "string" || typeof row.email !== "string") {
        return [];
      }
      return [
        {
          id: row.id,
          email: row.email,
          status: typeof row.status === "string" ? row.status : "",
          roles: Array.isArray(row.roles) ? row.roles.filter((value): value is string => typeof value === "string") : [],
          allowedModels: Array.isArray(row.allowed_models)
            ? row.allowed_models.filter((value): value is string => typeof value === "string")
            : [],
          created_at: typeof row.created_at === "string" ? row.created_at : "",
        },
      ];
    })
    : [];
  return {
    users,
    total: typeof result.envelope.data.total === "number" ? result.envelope.data.total : 0,
    message: "",
  };
}

export function AdminUsers() {
  const { t } = useI18n();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const { flash, setFlash } = useBootFlash(t.admin.pages.users.loading);
  const [pendingId, setPendingId] = useState("");
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [appliedQ, setAppliedQ] = useState("");
  const [appliedStatus, setAppliedStatus] = useState("");
  /** 展开配置模型的用户；同一时间只展开一行。 */
  const [modelsFor, setModelsFor] = useState("");
  const [modelsDraft, setModelsDraft] = useState<string[]>([]);
  const [modelsBusy, setModelsBusy] = useState(false);

  async function load() {
    const next = await pullUsers(page, { q: appliedQ, status: appliedStatus }, t.admin.pages.users.loadFail);
    setUsers(next.users);
    setTotal(next.total);
    setFlash(loadFlash(next.message));
  }

  useEffect(() => {
    void (async () => {
      const next = await pullUsers(page, { q: appliedQ, status: appliedStatus }, t.admin.pages.users.loadFail);
      setUsers(next.users);
      setTotal(next.total);
      setFlash(loadFlash(next.message));
    })();
  }, [page, appliedQ, appliedStatus]);

  function roleName(code: string): string {
    return statusLabel(t, "role", code);
  }

  async function changeStatus(user: AdminUser, status: "active" | "frozen") {
    const verb = status === "frozen" ? t.admin.actions.freeze : t.admin.actions.unfreeze;
    if (!window.confirm(`${t.admin.actions.confirm} ${verb} ${user.email}?`)) {
      return;
    }
    setPendingId(user.id);
    const result = await postJson(`/api/admin/users/${user.id}/status`, { status });
    setPendingId("");
    if (!result.ok) {
      setFlash(errFlash(apiErrorLabel(t, result.envelope, t.admin.pages.users.msg.statusFail)));
      return;
    }
    setFlash(okFlash(`${verb}: ${user.email}`));
    await load();
  }

  async function assignRole(user: AdminUser, event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formEl = event.currentTarget;
    const role = new FormData(formEl).get("role_code");
    if (typeof role !== "string") {
      return;
    }
    setPendingId(user.id);
    const result = await postJson(`/api/admin/users/${user.id}/roles`, { role_code: role });
    setPendingId("");
    if (!result.ok) {
      setFlash(errFlash(apiErrorLabel(t, result.envelope, t.admin.pages.users.msg.roleAssignFail)));
      return;
    }
    setFlash(okFlash(`${t.admin.actions.assign}: ${user.email} · ${roleName(role)}`));
    await load();
  }

  async function removeRole(user: AdminUser, role: string) {
    if (role === "user") {
      setFlash(warnFlash(t.admin.pages.users.msg.cannotRevokeUser));
      return;
    }
    if (role === "superadmin") {
      setFlash(warnFlash(t.admin.pages.users.msg.cannotRevokeSuperadmin));
      return;
    }
    const label = roleName(role);
    const confirmed = window.confirm(
      [`${t.admin.actions.confirm} ${t.admin.actions.revoke} ${user.email} · ${label}?`].join("\n"),
    );
    if (!confirmed) {
      return;
    }
    setPendingId(user.id);
    const result = await deleteJson(`/api/admin/users/${user.id}/roles/${encodeURIComponent(role)}`);
    setPendingId("");
    if (!result.ok) {
      setFlash(errFlash(apiErrorLabel(t, result.envelope, t.admin.pages.users.msg.roleRevokeFail)));
      return;
    }
    const removed = result.envelope.data?.removed === true;
    setFlash(removed ? okFlash(`${t.admin.actions.revoke}: ${label}`) : warnFlash(label));
    await load();
  }

  async function saveModels(user: AdminUser) {
    setModelsBusy(true);
    const result = await postJson(`/api/admin/users/${user.id}/models`, { allowed_models: modelsDraft });
    setModelsBusy(false);
    if (!result.ok) {
      setFlash(errFlash(apiErrorLabel(t, result.envelope, t.admin.pages.users.msg.modelsFail)));
      return;
    }
    setFlash(okFlash(`${t.admin.pages.users.msg.modelsSaved}: ${user.email}`));
    setModelsFor("");
    setModelsDraft([]);
    await load();
  }

  async function softDelete(user: AdminUser) {
    if (!window.confirm(`${t.admin.actions.confirm} ${t.admin.actions.deleteAccount} ${user.email}?`)) {
      return;
    }
    setPendingId(user.id);
    const result = await postJson(`/api/admin/users/${user.id}/delete`, {});
    setPendingId("");
    if (!result.ok) {
      setFlash(errFlash(apiErrorLabel(t, result.envelope, t.admin.pages.users.msg.deleteFail)));
      return;
    }
    setFlash(okFlash(`${t.admin.actions.deleteAccount}: ${user.email}`));
    await load();
  }

  return (
    <section className="space-y-6">
      <div>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">{t.admin.pages.users.title}</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-foreground/70">{t.admin.pages.users.lead}</p>
          </div>
          <RefreshButton onRefresh={load} />
        </div>
        {flash ? <FlashBanner flash={flash} /> : null}
      </div>
      <form
        className="flex flex-wrap items-end gap-3 text-sm"
        onSubmit={(event) => {
          event.preventDefault();
          setPage(1);
          setAppliedQ(q);
          setAppliedStatus(statusFilter);
        }}
      >
        <label>
          {t.admin.pages.users.email}
          <input
            value={q}
            onChange={(event) => setQ(event.target.value)}
            placeholder={t.admin.actions.fuzzy}
            className="mt-1 block min-w-56 rounded border border-border bg-transparent px-3 py-2"
          />
        </label>
        <label>
          {t.admin.pages.users.status}
          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
            className="mt-1 block rounded border border-border bg-background px-3 py-2 text-foreground"
          >
            <option value="">{t.labels.common.all}</option>
            <option value="active">{statusLabel(t, "user", "active")}</option>
            <option value="frozen">{statusLabel(t, "user", "frozen")}</option>
            <option value="pending_verification">{statusLabel(t, "user", "pending_verification")}</option>
            <option value="deleted">{statusLabel(t, "user", "deleted")}</option>
          </select>
        </label>
        <button type="submit" className="rounded border border-border px-3 py-2">
          {t.admin.actions.query}
        </button>
      </form>
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-foreground/70">
            <th className="py-2 pr-4 font-medium">{t.admin.pages.users.email}</th>
            <th className="py-2 pr-4 font-medium">{t.admin.pages.users.status}</th>
            <th className="py-2 pr-4 font-medium">{t.admin.pages.users.roles}</th>
            <th className="py-2 pr-4 font-medium">{t.admin.pages.users.models}</th>
            <th className="py-2 font-medium">{t.admin.pages.users.actions}</th>
          </tr>
        </thead>
        <tbody>
          {users.map((user) => (
            <Fragment key={user.id}>
              <tr className="border-b border-border">
                <td className="py-3 pr-4">{user.email}</td>
                <td className="py-3 pr-4">{statusLabel(t, "user", user.status)}</td>
                <td className="py-3 pr-4">
                  <div className="flex flex-wrap gap-2">
                    {user.roles.length === 0 ? <span>{t.admin.pages.users.noRoles}</span> : null}
                    {user.roles.map((role) => (
                      <span key={role} className="inline-flex items-center gap-1 rounded border border-border px-2 py-0.5">
                        {roleName(role)}
                        {role !== "user" && role !== "superadmin" ? (
                          <button
                            type="button"
                            className="text-xs text-foreground/60"
                            disabled={pendingId === user.id}
                            onClick={() => void removeRole(user, role)}
                            title={`${t.admin.actions.revoke} ${roleName(role)}`}
                          >
                            {t.admin.actions.revokeShort}
                          </button>
                        ) : null}
                      </span>
                    ))}
                  </div>
                </td>
                <td className="py-3 pr-4">
                  <p className="text-xs text-foreground/60">
                    {user.allowedModels.length > 0
                      ? user.allowedModels.join(", ")
                      : t.admin.pages.users.modelsInherited}
                  </p>
                  <button
                    type="button"
                    className="mt-1 rounded border border-border px-2 py-0.5 text-xs"
                    disabled={pendingId === user.id}
                    onClick={() => {
                      if (modelsFor === user.id) {
                        setModelsFor("");
                        setModelsDraft([]);
                        return;
                      }
                      setModelsFor(user.id);
                      setModelsDraft(user.allowedModels);
                    }}
                  >
                    {modelsFor === user.id ? t.admin.pages.users.collapseModels : t.admin.pages.users.editModels}
                  </button>
                </td>
                <td className="py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    {user.status === "active" || user.status === "frozen" ? (
                      <>
                        <button
                          type="button"
                          className="rounded border border-border px-3 py-1"
                          disabled={pendingId === user.id}
                          onClick={() => void changeStatus(user, user.status === "active" ? "frozen" : "active")}
                        >
                          {user.status === "active" ? t.admin.actions.freeze : t.admin.actions.unfreeze}
                        </button>
                        <button
                          type="button"
                          className="rounded border border-border px-3 py-1"
                          disabled={pendingId === user.id}
                          onClick={() => void softDelete(user)}
                        >
                          {t.admin.actions.deleteAccount}
                        </button>
                      </>
                    ) : null}
                    <form className="flex gap-2" onSubmit={(event) => void assignRole(user, event)}>
                      <select name="role_code" className="rounded border border-border bg-background px-2 py-1 text-foreground" defaultValue="support">
                        {ASSIGNABLE.map((code) => (
                          <option key={code} value={code}>
                            {roleName(code)}
                          </option>
                        ))}
                      </select>
                      <button type="submit" className="rounded border border-border px-3 py-1" disabled={pendingId === user.id}>
                        {t.admin.actions.assign}
                      </button>
                    </form>
                  </div>
                </td>
              </tr>
              {modelsFor === user.id ? (
                <tr className="border-b border-border bg-foreground/5">
                  <td colSpan={5} className="py-4">
                    <p className="mb-2 text-xs text-foreground/60">{t.admin.pages.users.modelsHint}</p>
                    <ModelPicker
                      mode="cascade"
                      value={modelsDraft}
                      onChange={setModelsDraft}
                      disabled={modelsBusy}
                    />
                    <div className="mt-3 flex gap-2 text-sm">
                      <button
                        type="button"
                        className="rounded border border-border px-3 py-1"
                        disabled={modelsBusy}
                        onClick={() => void saveModels(user)}
                      >
                        {t.admin.actions.save}
                      </button>
                      <button
                        type="button"
                        className="rounded border border-border px-3 py-1"
                        disabled={modelsBusy}
                        onClick={() => {
                          setModelsFor("");
                          setModelsDraft([]);
                        }}
                      >
                        {t.admin.actions.cancel}
                      </button>
                    </div>
                  </td>
                </tr>
              ) : null}
            </Fragment>
          ))}
        </tbody>
      </table>
      <PageControls page={page} pageSize={PAGE_SIZE} total={total} onPageChange={setPage} />
    </section>
  );
}
