"use client";

import { useEffect, useMemo, useState } from "react";

import { useI18n } from "@/components/locale-provider";
import { getJson } from "@/lib/api-client";

type CatalogModel = {
  publicName: string;
  displayName: string;
  providerName: string;
};

/** 公开名前缀 → 厂商；用于「供应商 → 厂商 → 模型」逐级筛选。 */
const VENDORS: { label: string; match: RegExp }[] = [
  { label: "OpenAI", match: /^(gpt-|o1-|o3-|o4-|text-embedding|tts-|whisper|dall-e|sora)/i },
  { label: "Anthropic", match: /^claude/i },
  { label: "Google", match: /^gemini/i },
  { label: "DeepSeek", match: /^deepseek/i },
  { label: "Qwen", match: /^(qwen|qwq|qvq)/i },
  { label: "GLM", match: /^glm/i },
  { label: "Kimi", match: /^kimi/i },
  { label: "MiniMax", match: /^minimax/i },
  { label: "xAI", match: /^grok/i },
  { label: "Llama", match: /^llama/i },
  { label: "Doubao", match: /^(doubao|seedance|seedream)/i },
  { label: "Video/Image", match: /^(wan|viduq|z-image|veo)/i },
];

const OTHER_VENDOR = "Other";

function vendorOf(publicName: string): string {
  for (const rule of VENDORS) {
    if (rule.match.test(publicName)) {
      return rule.label;
    }
  }
  return OTHER_VENDOR;
}

function readModels(value: unknown): CatalogModel[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((item) => {
    if (!item || typeof item !== "object") {
      return [];
    }
    const row = item as Record<string, unknown>;
    const publicName = typeof row.public_name === "string" ? row.public_name : "";
    if (!publicName) {
      return [];
    }
    return [
      {
        publicName,
        displayName:
          typeof row.display_name === "string" && row.display_name ? row.display_name : publicName,
        providerName: typeof row.provider_name === "string" ? row.provider_name : "",
      },
    ];
  });
}

/** 已上架模型列表在页面生命周期内只拉一次；失败则下次重试。 */
let catalogCache: Promise<CatalogModel[]> | null = null;

function fetchCatalog(): Promise<CatalogModel[]> {
  if (catalogCache === null) {
    catalogCache = getJson("/api/console/models").then((result) => {
      if (!result.ok || !Array.isArray(result.envelope.data?.models)) {
        catalogCache = null;
        return [] as CatalogModel[];
      }
      return readModels(result.envelope.data.models);
    });
  }
  return catalogCache;
}

export type ModelPickerProps = {
  /** 当前允许的模型公开名。 */
  value: string[];
  onChange: (next: string[]) => void;
  /** cascade：管理员，供应商→厂商→模型逐级选择；simple：顾客，直接选择模型。 */
  mode: "cascade" | "simple";
  disabled?: boolean;
};

export function ModelPicker({ value, onChange, mode, disabled = false }: ModelPickerProps) {
  const { t } = useI18n();
  const p = t.console.modelPicker;
  const [models, setModels] = useState<CatalogModel[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [provider, setProvider] = useState("");
  const [vendor, setVendor] = useState("");
  const [query, setQuery] = useState("");

  useEffect(() => {
    void (async () => {
      const list = await fetchCatalog();
      setModels(list);
      setFailed(list.length === 0 && catalogCache === null);
    })();
  }, []);

  const providers = useMemo(
    () => Array.from(new Set((models ?? []).map((item) => item.providerName).filter(Boolean))).sort(),
    [models],
  );

  const vendorOptions = useMemo(() => {
    const source = (models ?? []).filter((item) => !provider || item.providerName === provider);
    return Array.from(new Set(source.map((item) => vendorOf(item.publicName)))).sort();
  }, [models, provider]);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (models ?? []).filter(
      (item) =>
        (!provider || item.providerName === provider) &&
        (!vendor || vendorOf(item.publicName) === vendor) &&
        (!needle ||
          item.publicName.toLowerCase().includes(needle) ||
          item.displayName.toLowerCase().includes(needle)),
    );
  }, [models, provider, vendor, query]);

  const stale = useMemo(() => {
    if (models === null) {
      return [];
    }
    const known = new Set(models.map((item) => item.publicName));
    return value.filter((name) => !known.has(name));
  }, [models, value]);

  function toggle(name: string) {
    if (value.includes(name)) {
      onChange(value.filter((item) => item !== name));
      return;
    }
    onChange([...value, name]);
  }

  function toggleVisible() {
    const names = visible.map((item) => item.publicName);
    if (names.length === 0) {
      return;
    }
    const allSelected = names.every((name) => value.includes(name));
    if (allSelected) {
      onChange(value.filter((name) => !names.includes(name)));
      return;
    }
    onChange(Array.from(new Set([...value, ...names])));
  }

  const allVisibleSelected = visible.length > 0 && visible.every((item) => value.includes(item.publicName));

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        {mode === "cascade" ? (
          <select
            value={provider}
            disabled={disabled}
            aria-label={p.provider}
            className="rounded border border-border bg-background px-3 py-2 text-foreground"
            onChange={(event) => {
              setProvider(event.target.value);
              setVendor("");
            }}
          >
            <option value="">{p.allProviders}</option>
            {providers.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        ) : null}
        <select
          value={vendor}
          disabled={disabled}
          aria-label={p.vendor}
          className="rounded border border-border bg-background px-3 py-2 text-foreground"
          onChange={(event) => setVendor(event.target.value)}
        >
          <option value="">{p.allVendors}</option>
          {vendorOptions.map((name) => (
            <option key={name} value={name}>
              {name === OTHER_VENDOR ? p.otherVendor : name}
            </option>
          ))}
        </select>
        <input
          value={query}
          disabled={disabled}
          placeholder={p.search}
          aria-label={p.search}
          className="min-w-48 flex-1 rounded border border-border bg-transparent px-3 py-2"
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
            }
          }}
        />
        <button
          type="button"
          disabled={disabled || visible.length === 0}
          className="rounded border border-border px-3 py-2"
          onClick={toggleVisible}
        >
          {allVisibleSelected ? p.unselectVisible : p.selectVisible}
        </button>
      </div>

      <p className="text-xs text-foreground/60">
        {failed ? p.loadFail : p.selected.replace("{count}", String(value.length))}
      </p>

      {value.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {value.map((name) => {
            const isStale = stale.includes(name);
            return (
              <span
                key={name}
                className={`inline-flex items-center gap-1 rounded border px-2 py-1 text-xs ${isStale ? "border-amber-500/60 text-amber-600" : "border-border bg-foreground/5"
                  }`}
              >
                {name}
                {isStale ? <span>{p.stale}</span> : null}
                <button
                  type="button"
                  disabled={disabled}
                  aria-label={`${p.remove} ${name}`}
                  className="px-1 text-foreground/60 hover:text-foreground"
                  onClick={() => onChange(value.filter((item) => item !== name))}
                >
                  ×
                </button>
              </span>
            );
          })}
          <button
            type="button"
            disabled={disabled}
            className="text-xs text-foreground/60 underline"
            onClick={() => onChange([])}
          >
            {p.clear}
          </button>
        </div>
      ) : (
        <p className="text-xs text-foreground/60">{p.emptySelected}</p>
      )}

      <div className="max-h-64 overflow-auto rounded border border-border">
        {models === null ? (
          <p className="px-3 py-2 text-sm text-foreground/60">{p.loading}</p>
        ) : visible.length === 0 ? (
          <p className="px-3 py-2 text-sm text-foreground/60">{p.empty}</p>
        ) : (
          <ul className="divide-y divide-border text-sm">
            {visible.map((item) => (
              <li key={item.publicName}>
                <label className="flex cursor-pointer items-start gap-2 px-3 py-2 hover:bg-foreground/5">
                  <input
                    type="checkbox"
                    checked={value.includes(item.publicName)}
                    disabled={disabled}
                    className="mt-1"
                    onChange={() => toggle(item.publicName)}
                  />
                  <span className="min-w-0">
                    <span className="block">{item.displayName}</span>
                    <span className="block text-xs text-foreground/60">
                      {item.publicName}
                      {mode === "cascade" && item.providerName ? ` · ${item.providerName}` : ""}
                    </span>
                  </span>
                </label>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
