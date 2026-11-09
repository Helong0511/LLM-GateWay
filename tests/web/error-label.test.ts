import { describe, expect, it } from "vitest";

import { en } from "../../apps/web/src/content/en";
import { zhCN } from "../../apps/web/src/content/zh-CN";
import { zhTW } from "../../apps/web/src/content/zh-TW";
import { apiErrorLabel } from "../../apps/web/src/lib/error-label";

describe("apiErrorLabel", () => {
  it("EN 下不展示 API 默认中文 message（注册发信失败）", () => {
    const envelope = {
      ok: false,
      error: {
        code: "MAIL_SEND_FAILED",
        message: "邮件暂时发不出去，请稍后再试；若持续出现请联系客服",
      },
    };
    expect(apiErrorLabel(en, envelope, "Registration failed")).toBe(en.errors.MAIL_SEND_FAILED);
    expect(apiErrorLabel(en, envelope, "Registration failed")).not.toMatch(/邮件/);
  });

  it("按语言取同一错误码", () => {
    const envelope = {
      error: { code: "AUTH_BAD_CREDENTIALS", message: "邮箱或密码不正确" },
    };
    expect(apiErrorLabel(en, envelope, "x")).toBe(en.errors.AUTH_BAD_CREDENTIALS);
    expect(apiErrorLabel(zhCN, envelope, "x")).toBe(zhCN.errors.AUTH_BAD_CREDENTIALS);
    expect(apiErrorLabel(zhTW, envelope, "x")).toBe(zhTW.errors.AUTH_BAD_CREDENTIALS);
  });

  it("未知码不用 API 中文，回退 caller fallback", () => {
    const envelope = {
      error: { code: "SOME_NEW_CODE", message: "这里是中文兜底" },
    };
    expect(apiErrorLabel(en, envelope, "Registration failed")).toBe("Registration failed");
  });

  it("填充 details 模板", () => {
    const envelope = {
      error: {
        code: "ORDER_STATUS_FILTER_INVALID",
        message: "ignored",
        details: { status: "paid" },
      },
    };
    expect(apiErrorLabel(en, envelope, "x")).toContain("paid");
  });
});
