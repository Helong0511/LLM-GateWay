"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { useI18n } from "@/components/locale-provider";
import type { Messages } from "@/content/messages";
import type { Envelope } from "@/lib/api-client";
import { apiErrorLabel } from "@/lib/error-label";
import { cn } from "@/lib/utils";

export type FlashLevel = "info" | "success" | "warning" | "error";

export type AuthDeliveryKind = "sent" | "unconfigured" | "accepted" | "already_verified";

export type SecurityMsgKey = keyof Messages["console"]["security"]["msg"];

/**
 * 文案要么是固定 text，要么用 errorCode / authDelivery / securityMsg 在渲染时按当前语言解析，
 * 这样切换 EN/简/繁时提示会跟着变，而不是卡在提交时那一版语言。
 */
export type FlashMessage = {
  text?: string;
  level: FlashLevel;
  errorCode?: string;
  errorDetails?: Record<string, unknown>;
  fallback?: string;
  authDelivery?: AuthDeliveryKind;
  /** auth 区简单文案键，渲染时按当前语言取 t.auth[key] */
  authCopy?: "totpHint" | "resetOk" | "verifyOk";
  /** 控制台安全页成功/提示文案键 */
  securityMsg?: SecurityMsgKey;
  /** API 失败时按当前语言取的 security.msg 兜底键 */
  securityFailKey?: SecurityMsgKey;
};

const LEVEL_CLASS: Record<FlashLevel, string> = {
  info: "border-[hsl(var(--info)/0.35)] bg-[hsl(var(--info)/0.1)] text-[hsl(var(--info-fg))]",
  success: "border-[hsl(var(--success)/0.4)] bg-[hsl(var(--success)/0.12)] text-[hsl(var(--success-fg))]",
  warning: "border-[hsl(var(--warning)/0.45)] bg-[hsl(var(--warning)/0.14)] text-[hsl(var(--warning-fg))]",
  error: "border-[hsl(var(--danger)/0.45)] bg-[hsl(var(--danger)/0.12)] text-[hsl(var(--danger-fg))]",
};

export function infoFlash(text: string): FlashMessage {
  return { text, level: "info" };
}

export function okFlash(text: string): FlashMessage {
  return { text, level: "success" };
}

export function warnFlash(text: string): FlashMessage {
  return { text, level: "warning" };
}

export function errFlash(text: string): FlashMessage {
  return { text, level: "error" };
}

/** 登录/注册等：存稳定码，Banner 按当前 locale 取 t.errors。 */
export function errFlashFromApi(envelope: Envelope, fallback: string): FlashMessage {
  return {
    level: "error",
    errorCode: (envelope.error?.code || "").trim() || undefined,
    errorDetails: envelope.error?.details,
    fallback,
  };
}

export function errFlashFromApiSecurity(
  envelope: Envelope,
  securityFailKey: SecurityMsgKey,
): FlashMessage {
  return {
    level: "error",
    errorCode: (envelope.error?.code || "").trim() || undefined,
    errorDetails: envelope.error?.details,
    securityFailKey,
  };
}

export function deliveryFlash(value: unknown): FlashMessage | null {
  if (value === "sent") {
    return { level: "success", authDelivery: "sent" };
  }
  if (value === "unconfigured") {
    return { level: "warning", authDelivery: "unconfigured" };
  }
  if (value === "accepted") {
    return { level: "info", authDelivery: "accepted" };
  }
  if (value === "already_verified") {
    return { level: "info", authDelivery: "already_verified" };
  }
  return null;
}

export function resultFlash(ok: boolean, success: string, fail: string): FlashMessage {
  return ok ? okFlash(success) : errFlash(fail);
}

export function resultFlashFromApi(ok: boolean, success: string, envelope: Envelope, fallback: string): FlashMessage {
  return ok ? okFlash(success) : errFlashFromApi(envelope, fallback);
}

export function securityFlash(level: FlashLevel, key: SecurityMsgKey): FlashMessage {
  return { level, securityMsg: key };
}

export function resultSecurityFlash(
  ok: boolean,
  successKey: SecurityMsgKey,
  envelope: Envelope,
  failKey: SecurityMsgKey,
): FlashMessage {
  return ok ? securityFlash("success", successKey) : errFlashFromApiSecurity(envelope, failKey);
}

/** 列表/详情拉取：有文案视为错误，空串清空提示。 */
export function loadFlash(message: string): FlashMessage | null {
  return message ? errFlash(message) : null;
}

function resolveFlashText(
  flash: FlashMessage,
  t: ReturnType<typeof useI18n>["t"],
): string {
  if (flash.authDelivery) {
    const map: Record<AuthDeliveryKind, string> = {
      sent: t.auth.deliverySent,
      unconfigured: t.auth.deliveryUnconfigured,
      accepted: t.auth.deliveryAccepted,
      already_verified: t.auth.deliveryAlreadyVerified,
    };
    return map[flash.authDelivery];
  }
  if (flash.authCopy) {
    return t.auth[flash.authCopy];
  }
  if (flash.securityMsg) {
    return t.console.security.msg[flash.securityMsg];
  }
  if (flash.errorCode || flash.securityFailKey || flash.fallback) {
    const fallback = flash.securityFailKey
      ? t.console.security.msg[flash.securityFailKey]
      : flash.fallback || "";
    return apiErrorLabel(
      t,
      {
        error: {
          code: flash.errorCode,
          details: flash.errorDetails,
        },
      },
      fallback,
    );
  }
  return flash.text || "";
}

const AUTO_DISMISS_MS: Record<FlashLevel, number> = {
  info: 3500,
  success: 4000,
  warning: 6500,
  error: 8000,
};

export function FlashBanner({
  flash,
  className,
  compact = false,
  onDismiss,
}: {
  flash: FlashMessage | null | undefined;
  className?: string;
  /** 保留兼容；固定浮层不再依赖页面内边距 */
  compact?: boolean;
  /** 自动或手动关闭时回调，便于父级清空 flash 状态 */
  onDismiss?: () => void;
}) {
  const { t } = useI18n();
  const [mounted, setMounted] = useState(false);
  const [dismissedKey, setDismissedKey] = useState<string | null>(null);
  const onDismissRef = useRef(onDismiss);
  onDismissRef.current = onDismiss;
  const text = flash ? resolveFlashText(flash, t) : "";
  const flashKey = flash && text ? `${flash.level}:${text}` : "";

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!flashKey || !flash) {
      return;
    }
    const level = flash.level;
    const key = flashKey;
    const timer = window.setTimeout(() => {
      setDismissedKey(key);
      onDismissRef.current?.();
    }, AUTO_DISMISS_MS[level]);
    return () => window.clearTimeout(timer);
    // 仅随文案指纹重置计时，避免父级重渲染打断倒计时
    // eslint-disable-next-line react-hooks/exhaustive-deps -- flash.level 已编码进 flashKey
  }, [flashKey]);

  if (!text || !flash || (flashKey && dismissedKey === flashKey)) {
    return null;
  }

  const label =
    flash.level === "info"
      ? t.common.flashInfo
      : flash.level === "success"
        ? t.common.flashSuccess
        : flash.level === "warning"
          ? t.common.flashWarning
          : t.common.flashError;

  function dismiss() {
    if (flashKey) {
      setDismissedKey(flashKey);
    }
    onDismissRef.current?.();
  }

  const node = (
    <div
      className="pointer-events-none fixed inset-x-0 top-0 z-[60] flex justify-center px-4 pt-3 sm:pt-4"
      data-flash-host=""
      aria-live="polite"
    >
      <div
        role="status"
        data-flash-level={flash.level}
        className={cn(
          "pointer-events-auto mt-0 flex max-h-[40vh] w-full max-w-xl items-start gap-3 overflow-y-auto rounded-md border px-3 py-2 text-sm leading-6 shadow-lg backdrop-blur-md",
          "sm:mt-[3.25rem]",
          LEVEL_CLASS[flash.level],
          className,
        )}
      >
        <p className="min-w-0 flex-1">
          <span className="mr-2 inline-block font-semibold tracking-wide">{label}</span>
          {text}
        </p>
        <button
          type="button"
          className="shrink-0 rounded px-1.5 text-base leading-none opacity-70 hover:opacity-100"
          aria-label={t.common.flashDismiss}
          onClick={dismiss}
        >
          ×
        </button>
      </div>
    </div>
  );

  void compact;
  if (!mounted || typeof document === "undefined") {
    return node;
  }
  return createPortal(node, document.body);
}
