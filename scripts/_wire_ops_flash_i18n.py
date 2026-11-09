# -*- coding: utf-8 -*-
"""Inject Flash/confirm msg blocks into locale files."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(r"e:/ZZZ/apps/web/src/content")

BILLING = {
    "en": """      msg: {
        createFail: "Order was not created. Try again later.",
        createdMock: "Order created. Mock payment needs a second confirm and does not credit automatically.",
        confirmFail: "Payment confirmation failed. Try again later or contact support.",
        mockConfirmed: "Mock payment confirmed. Balance updated.",
        confirmCancel: "Cancel order {orderNo}?",
        cancelled: "Order cancelled.",
        cancelFail: "Order cancel failed. Refresh and try again.",
      }""",
    "zh-CN": """      msg: {
        createFail: "下单未成功，请稍后再试",
        createdMock: "订单已创建。模拟支付需要再确认一次，不会自动入账。",
        confirmFail: "支付确认未成功，请稍后再试或联系客服",
        mockConfirmed: "模拟支付已确认，余额已更新。",
        confirmCancel: "确认取消订单 {orderNo}？",
        cancelled: "订单已取消。",
        cancelFail: "订单取消未成功，请刷新后重试",
      }""",
    "zh-TW": """      msg: {
        createFail: "下單未成功，請稍後再試",
        createdMock: "訂單已建立。模擬支付需要再確認一次，不會自動入帳。",
        confirmFail: "支付確認未成功，請稍後再試或聯絡客服",
        mockConfirmed: "模擬支付已確認，餘額已更新。",
        confirmCancel: "確認取消訂單 {orderNo}？",
        cancelled: "訂單已取消。",
        cancelFail: "訂單取消未成功，請重新整理後重試",
      }""",
}

TICKETS = {
    "en": """      msg: {
        submitted: "Ticket submitted",
        submitFail: "Ticket was not submitted. Check the content and try again.",
        notFound: "Ticket not found or you do not have access",
        replySaved: "Reply saved",
        replyFail: "Reply failed. Check the content and try again.",
        closed: "Ticket closed",
        closeFail: "Could not close the ticket. Refresh and try again.",
      }""",
    "zh-CN": """      msg: {
        submitted: "工单已提交",
        submitFail: "工单提交未成功，请核对内容后重试",
        notFound: "工单不存在或无权查看",
        replySaved: "回复已保存",
        replyFail: "工单回复未成功，请核对内容后重试",
        closed: "工单已关闭",
        closeFail: "工单关闭未成功，请刷新后重试",
      }""",
    "zh-TW": """      msg: {
        submitted: "工單已提交",
        submitFail: "工單提交未成功，請核對內容後重試",
        notFound: "工單不存在或無權查看",
        replySaved: "回覆已儲存",
        replyFail: "工單回覆未成功，請核對內容後重試",
        closed: "工單已關閉",
        closeFail: "工單關閉未成功，請重新整理後重試",
      }""",
}

INVOICES = {
    "en": """      msg: {
        submitted: "Invoice request submitted",
        submitFail: "Invoice request failed. Check title and tax ID.",
        updated: "Invoice status updated",
        updateFail: "Update failed. Check and try again.",
        cancelled: "Invoice request cancelled",
        cancelFail: "Cancel failed (pending only). Refresh and try again.",
      }""",
    "zh-CN": """      msg: {
        submitted: "发票申请已提交",
        submitFail: "发票申请未成功，请核对抬头与税号后重试",
        updated: "发票状态已更新",
        updateFail: "操作未成功，请核对后重试",
        cancelled: "发票申请已撤销",
        cancelFail: "发票撤销未成功（仅待审核可撤），请刷新后重试",
      }""",
    "zh-TW": """      msg: {
        submitted: "發票申請已提交",
        submitFail: "發票申請未成功，請核對抬頭與稅號後重試",
        updated: "發票狀態已更新",
        updateFail: "操作未成功，請核對後重試",
        cancelled: "發票申請已撤銷",
        cancelFail: "發票撤銷未成功（僅待審核可撤），請重新整理後重試",
      }""",
}

COUPONS_CONSOLE = {
    "en": """      msg: {
        loadRedemptionsFail: "Could not load redemptions. Refresh and try again.",
        codeRequired: "Enter a coupon code",
        redeemFail: "Redeem failed. Try again later, or contact support if it persists.",
        redeemOk: "Redeemed: {code} credited {amount} {currency}",
      }""",
    "zh-CN": """      msg: {
        loadRedemptionsFail: "暂时读不到兑换记录，请刷新页面重试",
        codeRequired: "请输入优惠券码",
        redeemFail: "兑换未成功，请稍后再试；若持续出现请联系客服",
        redeemOk: "兑换成功：{code} 已入账 {amount} {currency}",
      }""",
    "zh-TW": """      msg: {
        loadRedemptionsFail: "暫時讀不到兌換記錄，請重新整理頁面重試",
        codeRequired: "請輸入優惠券碼",
        redeemFail: "兌換未成功，請稍後再試；若持續出現請聯絡客服",
        redeemOk: "兌換成功：{code} 已入帳 {amount} {currency}",
      }""",
}


def insert_before_end(
    text: str,
    section_start: str,
    end_markers: list[str],
    block: str,
    probe: str,
) -> str:
    start = text.find(section_start)
    if start < 0:
        raise SystemExit(f"missing section {section_start!r}")
    end = -1
    used = None
    for marker in end_markers:
        end = text.find(marker, start)
        if end >= 0:
            used = marker
            break
    if end < 0:
        raise SystemExit(f"missing end {end_markers!r} after {section_start!r}")
    chunk = text[start:end]
    if probe in chunk:
        print(f"  skip (has {probe})")
        return text
    print(f"  + via {used!r}")
    return text[:end] + "\n" + block + text[end:]


def inject_console():
    coupons_ends = [
        "\n    },\n  },\n} as const;",
        "\n    },\n  },\n} satisfies Messages;",
    ]
    for locale in ("en", "zh-CN", "zh-TW"):
        path = ROOT / f"{locale}.ts"
        text = path.read_text(encoding="utf-8")
        print(f"console {locale}")
        text = insert_before_end(
            text,
            "    billing: {",
            ["\n    },\n    keys: {"],
            BILLING[locale],
            "mockConfirmed:",
        )
        text = insert_before_end(
            text,
            "    tickets: {",
            ["\n    },\n    invoices: {"],
            TICKETS[locale],
            "replySaved:",
        )
        text = insert_before_end(
            text,
            "    invoices: {",
            ["\n    },\n    coupons: {"],
            INVOICES[locale],
            "cancelFail:",
        )
        text = insert_before_end(
            text,
            "    coupons: {",
            coupons_ends,
            COUPONS_CONSOLE[locale],
            "redeemOk:",
        )
        path.write_text(text, encoding="utf-8")


ADMIN = {
    "users": {
        "en": """      msg: {
        statusFail: "Account status was not updated. Check permissions.",
        roleAssignFail: "Role assignment failed. Check permissions.",
        roleRevokeFail: "Role revoke failed. Check permissions.",
        deleteFail: "Account delete failed. Check permissions.",
      }""",
        "zh-CN": """      msg: {
        statusFail: "账号状态修改未成功，请核对权限后重试",
        roleAssignFail: "角色分配未成功，请核对权限后重试",
        roleRevokeFail: "角色撤销未成功，请核对权限后重试",
        deleteFail: "账号注销未成功，请核对权限后重试",
      }""",
        "zh-TW": """      msg: {
        statusFail: "帳號狀態修改未成功，請核對權限後重試",
        roleAssignFail: "角色指派未成功，請核對權限後重試",
        roleRevokeFail: "角色撤銷未成功，請核對權限後重試",
        deleteFail: "帳號註銷未成功，請核對權限後重試",
      }""",
        "end": "\n    },\n    providers: {",
        "probe": "statusFail:",
    },
    "keys": {
        "en": """      msg: {
        confirmRevoke: "Revoke key {prefix} for {email}? Calls stop immediately.",
        revoked: "Key revoked.",
        revokeFail: "Revoke failed. Refresh and try again.",
        quotaSaved: "Quota saved. Empty means no limit.",
        quotaFail: "Quota save failed. Check the values.",
      }""",
        "zh-CN": """      msg: {
        confirmRevoke: "确认吊销 {email} 的密钥 {prefix}？吊销后立即不能调用。",
        revoked: "密钥已吊销。",
        revokeFail: "密钥吊销未成功，请刷新后重试",
        quotaSaved: "配额已保存。留空表示不设上限。",
        quotaFail: "配额保存未成功，请核对数值后重试",
      }""",
        "zh-TW": """      msg: {
        confirmRevoke: "確認吊銷 {email} 的金鑰 {prefix}？吊銷後立即不能呼叫。",
        revoked: "金鑰已吊銷。",
        revokeFail: "金鑰吊銷未成功，請重新整理後重試",
        quotaSaved: "配額已儲存。留空表示不設上限。",
        quotaFail: "配額儲存未成功，請核對數值後重試",
      }""",
        "end": "\n    },\n    orders: {",
        "probe": "confirmRevoke:",
    },
    "orders": {
        "en": """      msg: {
        confirmClose: "Close pending order {orderNo}?",
        closed: "Order closed.",
        closeFail: "Close failed (pending only). Refresh and try again.",
        batchNeedRows: "Enter at least one line: order_no amount",
        batchFail: "Batch reconcile failed. Check channel and lines.",
        batchOk: "Batch reconcile done: matched {matched}, disputed {disputed}",
      }""",
        "zh-CN": """      msg: {
        confirmClose: "确认关闭待支付订单 {orderNo}？",
        closed: "订单已关闭。",
        closeFail: "订单关闭未成功（仅待支付可关），请刷新后重试",
        batchNeedRows: "请至少填写一行：订单号 金额",
        batchFail: "批量对账未成功，请核对渠道与明细后重试",
        batchOk: "批量对账完成：匹配 {matched}，争议 {disputed}",
      }""",
        "zh-TW": """      msg: {
        confirmClose: "確認關閉待支付訂單 {orderNo}？",
        closed: "訂單已關閉。",
        closeFail: "訂單關閉未成功（僅待支付可關），請重新整理後重試",
        batchNeedRows: "請至少填寫一行：訂單號 金額",
        batchFail: "批量對帳未成功，請核對通路與明細後重試",
        batchOk: "批量對帳完成：匹配 {matched}，爭議 {disputed}",
      }""",
        "end": "\n    },\n    products: {",
        "probe": "confirmClose:",
    },
    "refunds": {
        "en": """      msg: {
        requested: "Refund requested; another finance reviewer must approve.",
        requestFail: "Refund request failed. Check order and reason.",
        confirmReview: "Confirm review of this refund?",
        reviewed: "Reviewed; waiting for another person to execute.",
        reviewFail: "Review failed. Confirm you are a different finance user.",
        confirmReject: "Reject this refund?",
        rejected: "Refund rejected.",
        rejectFail: "Reject failed. Refresh and try again.",
        confirmExecute: "Execute refund? A reverse ledger entry will be posted.",
        executed: "Refund executed.",
        executeFail: "Execute failed. Confirm the reviewer is not you.",
      }""",
        "zh-CN": """      msg: {
        requested: "退款已发起，需要另一名财务复核。",
        requestFail: "退款发起未成功，请核对订单与原因后重试",
        confirmReview: "确认复核这张退款单？",
        reviewed: "已复核，等待另一人执行。",
        reviewFail: "退款复核未成功，请确认是否为另一名财务",
        confirmReject: "确认拒绝这张退款单？",
        rejected: "退款单已拒绝。",
        rejectFail: "退款拒绝未成功，请刷新后重试",
        confirmExecute: "确认执行退款？执行后会记一笔反向流水。",
        executed: "退款已执行。",
        executeFail: "退款执行未成功，请确认复核人不是自己",
      }""",
        "zh-TW": """      msg: {
        requested: "退款已發起，需要另一名財務覆核。",
        requestFail: "退款發起未成功，請核對訂單與原因後重試",
        confirmReview: "確認覆核這張退款單？",
        reviewed: "已覆核，等待另一人執行。",
        reviewFail: "退款覆核未成功，請確認是否為另一名財務",
        confirmReject: "確認拒絕這張退款單？",
        rejected: "退款單已拒絕。",
        rejectFail: "退款拒絕未成功，請重新整理後重試",
        confirmExecute: "確認執行退款？執行後會記一筆反向流水。",
        executed: "退款已執行。",
        executeFail: "退款執行未成功，請確認覆核人不是自己",
      }""",
        "end": "\n    },\n    ordersExtra: {",
        "probe": "confirmReview:",
    },
    "audit": {
        "en": """      msg: {
        verifyFail: "Hash-chain verify failed. Try again later.",
        chainOk: "Hash chain intact; checked {checked} entries.",
        chainBroken: "Hash chain broken at sequence {seq}.",
      }""",
        "zh-CN": """      msg: {
        verifyFail: "哈希链校验未成功，请稍后重试",
        chainOk: "哈希链完整，已核对 {checked} 条。",
        chainBroken: "哈希链在序号 {seq} 断裂。",
      }""",
        "zh-TW": """      msg: {
        verifyFail: "雜湊鏈校驗未成功，請稍後重試",
        chainOk: "雜湊鏈完整，已核對 {checked} 條。",
        chainBroken: "雜湊鏈在序號 {seq} 斷裂。",
      }""",
        "end": "\n    },\n    routes: {",
        "probe": "chainOk:",
    },
    "routes": {
        "en": """      msg: {
        confirmDisable:
          "Disable route 「{name}」?\\n\\nCustomers cannot call this public name until you enable it again.",
        disabled: "Deployment disabled; this route is temporarily unavailable.",
        enabled: "Deployment enabled; route is callable again.",
        statusFail: "Route status was not updated. Refresh and try again.",
      }""",
        "zh-CN": """      msg: {
        confirmDisable:
          "确认停用路由「{name}」？\\n\\n停用后客户不能再通过该公开名调用。\\n可随时在本页重新启用。",
        disabled: "部署已停用，该路由暂时不可调用。",
        enabled: "部署已启用，路由恢复可调用。",
        statusFail: "路由状态修改未成功，请刷新后重试",
      }""",
        "zh-TW": """      msg: {
        confirmDisable:
          "確認停用路由「{name}」？\\n\\n停用後客戶不能再透過該公開名呼叫。\\n可隨時在本頁重新啟用。",
        disabled: "部署已停用，該路由暫時不可呼叫。",
        enabled: "部署已啟用，路由恢復可呼叫。",
        statusFail: "路由狀態修改未成功，請重新整理後重試",
      }""",
        "end": "\n    },\n    settings: {",
        "probe": "confirmDisable:",
    },
    "announcements": {
        "en": """      msg: {
        savedDraft: "Announcement saved, not published yet",
        saveFail: "Save failed. Check and try again.",
        published: "Published",
        unpublished: "Unpublished",
        opFail: "Operation failed. Check and try again.",
        updated: "Announcement updated",
        confirmDelete: "Delete this announcement?",
        deleted: "Announcement deleted",
        deleteFail: "Delete failed. Refresh and try again.",
      }""",
        "zh-CN": """      msg: {
        savedDraft: "公告已保存，尚未发布",
        saveFail: "保存未成功，请核对后重试",
        published: "已发布",
        unpublished: "已撤回",
        opFail: "操作未成功，请核对后重试",
        updated: "公告已更新",
        confirmDelete: "确认删除该公告？",
        deleted: "公告已删除",
        deleteFail: "删除未成功，请刷新后重试",
      }""",
        "zh-TW": """      msg: {
        savedDraft: "公告已儲存，尚未發布",
        saveFail: "儲存未成功，請核對後重試",
        published: "已發布",
        unpublished: "已撤回",
        opFail: "操作未成功，請核對後重試",
        updated: "公告已更新",
        confirmDelete: "確認刪除該公告？",
        deleted: "公告已刪除",
        deleteFail: "刪除未成功，請重新整理後重試",
      }""",
        "end": "\n    },\n    tickets: {",
        "probe": "savedDraft:",
    },
    "tickets": {
        "en": TICKETS["en"],
        "zh-CN": TICKETS["zh-CN"],
        "zh-TW": TICKETS["zh-TW"],
        "end": "\n    },\n    invoices: {",
        "probe": "submitted:",
    },
    "invoices": {
        "en": INVOICES["en"],
        "zh-CN": INVOICES["zh-CN"],
        "zh-TW": INVOICES["zh-TW"],
        "end": "\n    },\n    coupons: {",
        "probe": "submitted:",
    },
    "coupons": {
        "en": """      msg: {
        generateFail: "Code generation failed. Try again.",
        generated: "Generated code {code} (filled into the form only; Create saves it).",
        bonusRequired: "Enter a bonus amount",
        created: "Coupon created and saved{suffix}",
        createFail: "Coupon create failed. Check amount and max uses.",
        confirmRestore: "Restore this coupon? It becomes Disabled; Enable again before customers can redeem.",
        restored: "Coupon restored as Disabled. Enable it under Disabled.",
        restoreFail: "Restore failed. Refresh and try again.",
        confirmDisable:
          "Disable coupon 「{code}」?\\n\\nDisable: customers see Disabled; you can Enable again.\\nUnlike Delete: after delete you must Restore before Enable.",
        enabled: "Coupon enabled; customers can redeem.",
        disabled: "Coupon disabled. Re-enable under Disabled, or delete.",
        statusFail: "Coupon status was not updated. Refresh and try again.",
        confirmDelete:
          "Delete this coupon?\\n\\nDelete: soft-delete; redemption history remains.\\nUnlike Disable: after delete you cannot Enable directly—Restore first.",
        deleted: "Coupon deleted. Restore under Deleted (restored as Disabled).",
        deleteFail: "Delete failed. Refresh and try again.",
        updated: "Coupon updated.",
        updateFail: "Update failed. Check max uses and expiry.",
      }""",
        "zh-CN": """      msg: {
        generateFail: "券码生成未成功，请再试一次",
        generated: "已生成券码 {code}（仅填入表单，尚未保存；提交「创建」后才会落库）。",
        bonusRequired: "请填写赠送金额",
        created: "优惠券已创建并保存{suffix}",
        createFail: "优惠券创建未成功，请核对金额与次数后重试",
        confirmRestore: "确认恢复该优惠券？恢复后为停用，需再点「启用」客户才能兑换。",
        restored: "优惠券已恢复为停用。可在「已停用」中启用。",
        restoreFail: "优惠券恢复未成功，请刷新后重试",
        confirmDisable:
          "确认停用优惠券「{code}」？\\n\\n停用：客户会看到「已停用」，之后可再启用。\\n与「删除」不同：删除后须先恢复才能再启用。",
        enabled: "优惠券已启用，客户可兑换。",
        disabled: "优惠券已停用。可在「已停用」中启用，或删除。",
        statusFail: "优惠券状态更新未成功，请刷新后重试",
        confirmDelete:
          "确认删除该优惠券？\\n\\n删除：软删除，历史兑换仍保留。\\n与「停用」不同：删除后不能直接启用，须先「恢复」。",
        deleted: "优惠券已删除。可在「已删除」中恢复（恢复后为停用）。",
        deleteFail: "优惠券删除未成功，请刷新后重试",
        updated: "优惠券已更新。",
        updateFail: "优惠券更新未成功，请核对次数与到期时间后重试",
      }""",
        "zh-TW": """      msg: {
        generateFail: "券碼產生未成功，請再試一次",
        generated: "已產生券碼 {code}（僅填入表單，尚未儲存；提交「建立」後才會落庫）。",
        bonusRequired: "請填寫贈送金額",
        created: "優惠券已建立並儲存{suffix}",
        createFail: "優惠券建立未成功，請核對金額與次數後重試",
        confirmRestore: "確認恢復該優惠券？恢復後為停用，需再點「啟用」客戶才能兌換。",
        restored: "優惠券已恢復為停用。可在「已停用」中啟用。",
        restoreFail: "優惠券恢復未成功，請重新整理後重試",
        confirmDisable:
          "確認停用優惠券「{code}」？\\n\\n停用：客戶會看到「已停用」，之後可再啟用。\\n與「刪除」不同：刪除後須先恢復才能再啟用。",
        enabled: "優惠券已啟用，客戶可兌換。",
        disabled: "優惠券已停用。可在「已停用」中啟用，或刪除。",
        statusFail: "優惠券狀態更新未成功，請重新整理後重試",
        confirmDelete:
          "確認刪除該優惠券？\\n\\n刪除：軟刪除，歷史兌換仍保留。\\n與「停用」不同：刪除後不能直接啟用，須先「恢復」。",
        deleted: "優惠券已刪除。可在「已刪除」中恢復（恢復後為停用）。",
        deleteFail: "優惠券刪除未成功，請重新整理後重試",
        updated: "優惠券已更新。",
        updateFail: "優惠券更新未成功，請核對次數與到期時間後重試",
      }""",
        "end": "\n    },\n    margin: {",
        "probe": "generateFail:",
    },
    "content": {
        "en": """      msg: {
        saved: "Content-safety toggle saved",
        saveFail: "Save failed. Check and try again.",
      }""",
        "zh-CN": """      msg: {
        saved: "内容安全开关已保存",
        saveFail: "保存未成功，请核对后重试",
      }""",
        "zh-TW": """      msg: {
        saved: "內容安全開關已儲存",
        saveFail: "儲存未成功，請核對後重試",
      }""",
        "end": "\n    },\n    tasks: {",
        "probe": "saved:",
    },
    "tasks": {
        "en": """      msg: {
        pingOk: "Ping recorded",
        pingFail: "Ping failed. Try again later.",
      }""",
        "zh-CN": """      msg: {
        pingOk: "探活已记录",
        pingFail: "探活未成功，请稍后重试",
      }""",
        "zh-TW": """      msg: {
        pingOk: "探活已記錄",
        pingFail: "探活未成功，請稍後重試",
      }""",
        "end": "\n    },\n  },\n} as const;",
        "probe": "pingOk:",
        "alt_end": "\n    },\n  },\n};",
    },
}


def inject_admin():
    file_map = {"en": "admin-en.ts", "zh-CN": "admin-zh-CN.ts", "zh-TW": "admin-zh-TW.ts"}
    for locale, filename in file_map.items():
        path = ROOT / filename
        text = path.read_text(encoding="utf-8")
        print(f"admin {locale}")
        for section, spec in ADMIN.items():
            start_marker = f"    {section}: {{"
            end_marker = spec["end"]
            start = text.find(start_marker)
            if start < 0:
                raise SystemExit(f"missing {section} in {filename}")
            end = text.find(end_marker, start)
            if end < 0 and "alt_end" in spec:
                end = text.find(spec["alt_end"], start)
                end_marker = spec["alt_end"]
            if end < 0:
                raise SystemExit(f"missing end for {section} in {filename}: {end_marker!r}")
            chunk = text[start:end]
            if spec["probe"] in chunk:
                print(f"  skip {section}")
                continue
            text = text[:end] + "\n" + spec[locale] + text[end:]
            print(f"  + {section}")
        path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    inject_console()
    inject_admin()
    print("OK")
