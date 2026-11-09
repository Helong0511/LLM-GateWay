# -*- coding: utf-8 -*-
"""Wire Flash/confirm strings in components to i18n msg keys."""
from __future__ import annotations

from pathlib import Path

COMP = Path(r"e:/ZZZ/apps/web/src/components")


def apply(name: str, pairs: list[tuple[str, str]]) -> None:
    path = COMP / name
    text = path.read_text(encoding="utf-8")
    orig = text
    for old, new in pairs:
        if old not in text:
            print(f"WARN {name}: missing {old[:90]!r}")
            continue
        text = text.replace(old, new, 1)
    if text != orig:
        path.write_text(text, encoding="utf-8")
        print(f"OK {name}")
    else:
        print(f"NOCHANGE {name}")


# --- billing ---
apply(
    "billing-panel.tsx",
    [
        (
            'setFlash(errFlash(errorMessage(result.envelope, "下单未成功，请稍后再试")));',
            "setFlash(errFlash(errorMessage(result.envelope, t.console.billing.msg.createFail)));",
        ),
        (
            'setFlash(warnFlash("订单已创建。模拟支付需要再确认一次，不会自动入账。"));',
            "setFlash(warnFlash(t.console.billing.msg.createdMock));",
        ),
        (
            'setFlash(errFlash(errorMessage(result.envelope, "支付确认未成功，请稍后再试或联系客服")));',
            "setFlash(errFlash(errorMessage(result.envelope, t.console.billing.msg.confirmFail)));",
        ),
        (
            'setFlash(okFlash("模拟支付已确认，余额已更新。"));',
            "setFlash(okFlash(t.console.billing.msg.mockConfirmed));",
        ),
        (
            "if (!window.confirm(`确认取消订单 ${orderNo}？`)) {",
            "if (!window.confirm(t.console.billing.msg.confirmCancel.replace(\"{orderNo}\", orderNo))) {",
        ),
        (
            'setFlash(resultFlash(result.ok, "订单已取消。", errorMessage(result.envelope, "订单取消未成功，请刷新后重试")));',
            "setFlash(resultFlash(result.ok, t.console.billing.msg.cancelled, errorMessage(result.envelope, t.console.billing.msg.cancelFail)));",
        ),
    ],
)

apply(
    "admin-refunds.tsx",
    [
        (
            'setFlash(resultFlash(result.ok, "退款已发起，需要另一名财务复核。", errorMessage(result.envelope, "退款发起未成功，请核对订单与原因后重试")));',
            "setFlash(resultFlash(result.ok, t.admin.pages.refunds.msg.requested, errorMessage(result.envelope, t.admin.pages.refunds.msg.requestFail)));",
        ),
        (
            'if (!window.confirm("确认复核这张退款单？")) {',
            "if (!window.confirm(t.admin.pages.refunds.msg.confirmReview)) {",
        ),
        (
            'setFlash(resultFlash(result.ok, "已复核，等待另一人执行。", errorMessage(result.envelope, "退款复核未成功，请确认是否为另一名财务")));',
            "setFlash(resultFlash(result.ok, t.admin.pages.refunds.msg.reviewed, errorMessage(result.envelope, t.admin.pages.refunds.msg.reviewFail)));",
        ),
        (
            'if (!window.confirm("确认拒绝这张退款单？")) {',
            "if (!window.confirm(t.admin.pages.refunds.msg.confirmReject)) {",
        ),
        (
            'setFlash(resultFlash(result.ok, "退款单已拒绝。", errorMessage(result.envelope, "退款拒绝未成功，请刷新后重试")));',
            "setFlash(resultFlash(result.ok, t.admin.pages.refunds.msg.rejected, errorMessage(result.envelope, t.admin.pages.refunds.msg.rejectFail)));",
        ),
        (
            'if (!window.confirm("确认执行退款？执行后会记一笔反向流水。")) {',
            "if (!window.confirm(t.admin.pages.refunds.msg.confirmExecute)) {",
        ),
        (
            'setFlash(resultFlash(result.ok, "退款已执行。", errorMessage(result.envelope, "退款执行未成功，请确认复核人不是自己")));',
            "setFlash(resultFlash(result.ok, t.admin.pages.refunds.msg.executed, errorMessage(result.envelope, t.admin.pages.refunds.msg.executeFail)));",
        ),
    ],
)

apply(
    "admin-orders.tsx",
    [
        (
            "if (!window.confirm(`确认关闭待支付订单 ${orderNo}？`)) {",
            "if (!window.confirm(t.admin.pages.orders.msg.confirmClose.replace(\"{orderNo}\", orderNo))) {",
        ),
        (
            'setFlash(resultFlash(result.ok, "订单已关闭。", errorMessage(result.envelope, "订单关闭未成功（仅待支付可关），请刷新后重试")));',
            "setFlash(resultFlash(result.ok, t.admin.pages.orders.msg.closed, errorMessage(result.envelope, t.admin.pages.orders.msg.closeFail)));",
        ),
        (
            'setFlash(warnFlash("请至少填写一行：订单号 金额"));',
            "setFlash(warnFlash(t.admin.pages.orders.msg.batchNeedRows));",
        ),
        (
            'setFlash(errFlash(errorMessage(result.envelope, "批量对账未成功，请核对渠道与明细后重试")));',
            "setFlash(errFlash(errorMessage(result.envelope, t.admin.pages.orders.msg.batchFail)));",
        ),
        (
            'setFlash(okFlash(`批量对账完成：匹配 ${String(data.matched ?? 0)}，争议 ${String(data.disputed ?? 0)}`));',
            'setFlash(okFlash(t.admin.pages.orders.msg.batchOk.replace("{matched}", String(data.matched ?? 0)).replace("{disputed}", String(data.disputed ?? 0))));',
        ),
    ],
)

apply(
    "admin-keys.tsx",
    [
        (
            "if (!window.confirm(`确认吊销 ${row.email} 的密钥 ${row.keyPrefix}？吊销后立即不能调用。`)) {",
            'if (!window.confirm(t.admin.pages.keys.msg.confirmRevoke.replace("{email}", row.email).replace("{prefix}", row.keyPrefix))) {',
        ),
        (
            'setFlash(resultFlash(result.ok, "密钥已吊销。", errorMessage(result.envelope, "密钥吊销未成功，请刷新后重试")));',
            "setFlash(resultFlash(result.ok, t.admin.pages.keys.msg.revoked, errorMessage(result.envelope, t.admin.pages.keys.msg.revokeFail)));",
        ),
        (
            'setFlash(resultFlash(result.ok, "配额已保存。留空表示不设上限。", errorMessage(result.envelope, "配额保存未成功，请核对数值后重试")));',
            "setFlash(resultFlash(result.ok, t.admin.pages.keys.msg.quotaSaved, errorMessage(result.envelope, t.admin.pages.keys.msg.quotaFail)));",
        ),
    ],
)

apply(
    "admin-users.tsx",
    [
        (
            'setFlash(errFlash(errorMessage(result.envelope, "账号状态修改未成功，请核对权限后重试")));',
            "setFlash(errFlash(errorMessage(result.envelope, t.admin.pages.users.msg.statusFail)));",
        ),
        (
            'setFlash(errFlash(errorMessage(result.envelope, "角色分配未成功，请核对权限后重试")));',
            "setFlash(errFlash(errorMessage(result.envelope, t.admin.pages.users.msg.roleAssignFail)));",
        ),
        (
            'setFlash(errFlash(errorMessage(result.envelope, "角色撤销未成功，请核对权限后重试")));',
            "setFlash(errFlash(errorMessage(result.envelope, t.admin.pages.users.msg.roleRevokeFail)));",
        ),
        (
            'setFlash(errFlash(errorMessage(result.envelope, "账号注销未成功，请核对权限后重试")));',
            "setFlash(errFlash(errorMessage(result.envelope, t.admin.pages.users.msg.deleteFail)));",
        ),
    ],
)

apply(
    "admin-audit.tsx",
    [
        (
            'setFlash(errFlash(errorMessage(result.envelope, "哈希链校验未成功，请稍后重试")));',
            "setFlash(errFlash(errorMessage(result.envelope, t.admin.pages.audit.msg.verifyFail)));",
        ),
        (
            """setFlash(
      data.ok === true
        ? okFlash(`哈希链完整，已核对 ${String(data.checked)} 条。`)
        : errFlash(`哈希链在序号 ${String(data.broken_seq)} 断裂。`),
    );""",
            """setFlash(
      data.ok === true
        ? okFlash(t.admin.pages.audit.msg.chainOk.replace("{checked}", String(data.checked)))
        : errFlash(t.admin.pages.audit.msg.chainBroken.replace("{seq}", String(data.broken_seq))),
    );""",
        ),
    ],
)

# ops-panels: larger set
OPS = [
    (
        'return { data: null, message: errorMessage(result.envelope, "暂时读不到数据，请刷新后重试") };',
        "return { data: null, message: errorMessage(result.envelope, loadFail) };",
    ),
    (
        "async function pull(path: string): Promise<{ data: Row | null; message: string }> {",
        "async function pull(path: string, loadFail: string): Promise<{ data: Row | null; message: string }> {",
    ),
    (
        "function useData(path: string) {\n  const [data, setData] = useState<Row | null>(null);\n  const [flash, setFlash] = useState<FlashMessage | null>(null);\n  const [page, setPage] = useState(1);\n  const [version, setVersion] = useState(0);\n\n  useEffect(() => {\n    void (async () => {\n      const next = await pull(withPage(path, page));\n      setData(next.data);\n      setFlash(loadFlash(next.message));\n    })();\n  }, [path, page, version]);",
        "function useData(path: string, loadFail?: string) {\n  const { t } = useI18n();\n  const fail = loadFail ?? t.admin.actions.loadFail;\n  const [data, setData] = useState<Row | null>(null);\n  const [flash, setFlash] = useState<FlashMessage | null>(null);\n  const [page, setPage] = useState(1);\n  const [version, setVersion] = useState(0);\n\n  useEffect(() => {\n    void (async () => {\n      const next = await pull(withPage(path, page), fail);\n      setData(next.data);\n      setFlash(loadFlash(next.message));\n    })();\n  }, [path, page, version, fail]);",
    ),
    # tickets
    (
        'setFlash(resultFlash(result.ok, "工单已提交", errorMessage(result.envelope, "工单提交未成功，请核对内容后重试")));',
        "setFlash(resultFlash(result.ok, t.admin.pages.tickets.msg.submitted, errorMessage(result.envelope, t.admin.pages.tickets.msg.submitFail)));",
    ),
    (
        'setFlash(errFlash(errorMessage(result.envelope, "工单不存在或无权查看")));',
        "setFlash(errFlash(errorMessage(result.envelope, t.admin.pages.tickets.msg.notFound)));",
    ),
    (
        'setFlash(resultFlash(result.ok, "回复已保存", errorMessage(result.envelope, "工单回复未成功，请核对内容后重试")));',
        "setFlash(resultFlash(result.ok, t.admin.pages.tickets.msg.replySaved, errorMessage(result.envelope, t.admin.pages.tickets.msg.replyFail)));",
    ),
    (
        'setFlash(resultFlash(result.ok, "工单已关闭", errorMessage(result.envelope, "工单关闭未成功，请刷新后重试")));',
        "setFlash(resultFlash(result.ok, t.admin.pages.tickets.msg.closed, errorMessage(result.envelope, t.admin.pages.tickets.msg.closeFail)));",
    ),
    # invoices
    (
        'setFlash(resultFlash(result.ok, "发票申请已提交", errorMessage(result.envelope, "发票申请未成功，请核对抬头与税号后重试")));',
        "setFlash(resultFlash(result.ok, t.admin.pages.invoices.msg.submitted, errorMessage(result.envelope, t.admin.pages.invoices.msg.submitFail)));",
    ),
    (
        'setFlash(resultFlash(result.ok, "发票状态已更新", errorMessage(result.envelope, "操作未成功，请核对后重试")));',
        "setFlash(resultFlash(result.ok, t.admin.pages.invoices.msg.updated, errorMessage(result.envelope, t.admin.pages.invoices.msg.updateFail)));",
    ),
    (
        'setFlash(resultFlash(result.ok, "发票申请已撤销", errorMessage(result.envelope, "发票撤销未成功（仅待审核可撤），请刷新后重试")));',
        "setFlash(resultFlash(result.ok, t.admin.pages.invoices.msg.cancelled, errorMessage(result.envelope, t.admin.pages.invoices.msg.cancelFail)));",
    ),
    # coupon redeem
    (
        'setFlash(warnFlash(errorMessage(result.envelope, "暂时读不到兑换记录，请刷新页面重试")));',
        "setFlash(warnFlash(errorMessage(result.envelope, t.console.coupons.msg.loadRedemptionsFail)));",
    ),
    (
        'setFlash(warnFlash("请输入优惠券码"));',
        "setFlash(warnFlash(t.console.coupons.msg.codeRequired));",
    ),
    (
        'errorMessage(result.envelope, "兑换未成功，请稍后再试；若持续出现请联系客服"),',
        "errorMessage(result.envelope, t.console.coupons.msg.redeemFail),",
    ),
    (
        "setFlash(okFlash(`兑换成功：${shown} 已入账 ${text(data.bonus_amount)} ${text(data.currency)}`));",
        'setFlash(okFlash(t.console.coupons.msg.redeemOk.replace("{code}", shown).replace("{amount}", text(data.bonus_amount)).replace("{currency}", text(data.currency))));',
    ),
    # admin coupons
    (
        'setFlash(errFlash(errorMessage(result.envelope, "券码生成未成功，请再试一次")));',
        "setFlash(errFlash(errorMessage(result.envelope, t.admin.pages.coupons.msg.generateFail)));",
    ),
    (
        "setFlash(okFlash(`已生成券码 ${next}（仅填入表单，尚未保存；提交「创建」后才会落库）。`));",
        'setFlash(okFlash(t.admin.pages.coupons.msg.generated.replace("{code}", next)));',
    ),
    (
        'setFlash(warnFlash("请填写赠送金额"));',
        "setFlash(warnFlash(t.admin.pages.coupons.msg.bonusRequired));",
    ),
    (
        """setFlash(
      resultFlash(
        result.ok,
        `优惠券已创建并保存${typeof result.envelope.data?.formatted === "string" ? `：${result.envelope.data.formatted}` : ""}`,
        errorMessage(result.envelope, "优惠券创建未成功，请核对金额与次数后重试"),
      ),
    );""",
        """setFlash(
      resultFlash(
        result.ok,
        t.admin.pages.coupons.msg.created.replace(
          "{suffix}",
          typeof result.envelope.data?.formatted === "string" ? `：${result.envelope.data.formatted}` : "",
        ),
        errorMessage(result.envelope, t.admin.pages.coupons.msg.createFail),
      ),
    );""",
    ),
    (
        "if (!window.confirm(`确认恢复该优惠券？恢复后为停用，需再点「启用」客户才能兑换。`)) {",
        "if (!window.confirm(t.admin.pages.coupons.msg.confirmRestore)) {",
    ),
    (
        """setFlash(
                            resultFlash(
                              result.ok,
                              "优惠券已恢复为停用。可在「已停用」中启用。",
                              errorMessage(result.envelope, "优惠券恢复未成功，请刷新后重试"),
                            ),
                          );""",
        """setFlash(
                            resultFlash(
                              result.ok,
                              t.admin.pages.coupons.msg.restored,
                              errorMessage(result.envelope, t.admin.pages.coupons.msg.restoreFail),
                            ),
                          );""",
    ),
    (
        """const ok = window.confirm(
                                [
                                  `确认停用优惠券「${text(item.formatted) || text(item.code)}」？`,
                                  "",
                                  "停用：客户会看到「已停用」，之后可再启用。",
                                  "与「删除」不同：删除后须先恢复才能再启用。",
                                ].join("\\n"),
                              );""",
        """const ok = window.confirm(
                                t.admin.pages.coupons.msg.confirmDisable.replace(
                                  "{code}",
                                  text(item.formatted) || text(item.code),
                                ),
                              );""",
    ),
    (
        """setFlash(
                              resultFlash(
                                result.ok,
                                nextEnabled
                                  ? "优惠券已启用，客户可兑换。"
                                  : "优惠券已停用。可在「已停用」中启用，或删除。",
                                errorMessage(result.envelope, "优惠券状态更新未成功，请刷新后重试"),
                              ),
                            );""",
        """setFlash(
                              resultFlash(
                                result.ok,
                                nextEnabled
                                  ? t.admin.pages.coupons.msg.enabled
                                  : t.admin.pages.coupons.msg.disabled,
                                errorMessage(result.envelope, t.admin.pages.coupons.msg.statusFail),
                              ),
                            );""",
    ),
    (
        """if (
                              !window.confirm(
                                [
                                  "确认删除该优惠券？",
                                  "",
                                  "删除：软删除，历史兑换仍保留。",
                                  "与「停用」不同：删除后不能直接启用，须先「恢复」。",
                                ].join("\\n"),
                              )
                            ) {""",
        """if (!window.confirm(t.admin.pages.coupons.msg.confirmDelete)) {""",
    ),
    (
        """setFlash(
                              resultFlash(
                                result.ok,
                                "优惠券已删除。可在「已删除」中恢复（恢复后为停用）。",
                                errorMessage(result.envelope, "优惠券删除未成功，请刷新后重试"),
                              ),
                            );""",
        """setFlash(
                              resultFlash(
                                result.ok,
                                t.admin.pages.coupons.msg.deleted,
                                errorMessage(result.envelope, t.admin.pages.coupons.msg.deleteFail),
                              ),
                            );""",
    ),
    (
        """setFlash(
                        resultFlash(
                          result.ok,
                          "优惠券已更新。",
                          errorMessage(result.envelope, "优惠券更新未成功，请核对次数与到期时间后重试"),
                        ),
                      );""",
        """setFlash(
                        resultFlash(
                          result.ok,
                          t.admin.pages.coupons.msg.updated,
                          errorMessage(result.envelope, t.admin.pages.coupons.msg.updateFail),
                        ),
                      );""",
    ),
    # announcements
    (
        'setFlash(resultFlash(result.ok, "公告已保存，尚未发布", errorMessage(result.envelope, "保存未成功，请核对后重试")));',
        "setFlash(resultFlash(result.ok, t.admin.pages.announcements.msg.savedDraft, errorMessage(result.envelope, t.admin.pages.announcements.msg.saveFail)));",
    ),
    (
        'setFlash(resultFlash(result.ok, (published ? "已发布" : "已撤回"), errorMessage(result.envelope, "操作未成功，请核对后重试")));',
        "setFlash(resultFlash(result.ok, published ? t.admin.pages.announcements.msg.published : t.admin.pages.announcements.msg.unpublished, errorMessage(result.envelope, t.admin.pages.announcements.msg.opFail)));",
    ),
    (
        'setFlash(resultFlash(result.ok, "公告已更新", errorMessage(result.envelope, "操作未成功，请核对后重试")));',
        "setFlash(resultFlash(result.ok, t.admin.pages.announcements.msg.updated, errorMessage(result.envelope, t.admin.pages.announcements.msg.opFail)));",
    ),
    (
        'if (!window.confirm("确认删除该公告？")) {',
        "if (!window.confirm(t.admin.pages.announcements.msg.confirmDelete)) {",
    ),
    (
        'setFlash(resultFlash(result.ok, "公告已删除", errorMessage(result.envelope, "删除未成功，请刷新后重试")));',
        "setFlash(resultFlash(result.ok, t.admin.pages.announcements.msg.deleted, errorMessage(result.envelope, t.admin.pages.announcements.msg.deleteFail)));",
    ),
    # routes
    (
        """const ok = window.confirm(
        [
          `确认停用路由「${text(item.display_name) || text(item.model)}」？`,
          "",
          "停用后客户不能再通过该公开名调用。",
          "可随时在本页重新启用。",
        ].join("\\n"),
      );""",
        """const ok = window.confirm(
        t.admin.pages.routes.msg.confirmDisable.replace(
          "{name}",
          text(item.display_name) || text(item.model),
        ),
      );""",
    ),
    (
        """setFlash(
      resultFlash(
        result.ok,
        next === "disabled" ? "部署已停用，该路由暂时不可调用。" : "部署已启用，路由恢复可调用。",
        errorMessage(result.envelope, "路由状态修改未成功，请刷新后重试"),
      ),
    );""",
        """setFlash(
      resultFlash(
        result.ok,
        next === "disabled" ? t.admin.pages.routes.msg.disabled : t.admin.pages.routes.msg.enabled,
        errorMessage(result.envelope, t.admin.pages.routes.msg.statusFail),
      ),
    );""",
    ),
    # content / tasks
    (
        'setFlash(resultFlash(result.ok, "内容安全开关已保存", errorMessage(result.envelope, "保存未成功，请核对后重试")));',
        "setFlash(resultFlash(result.ok, t.admin.pages.content.msg.saved, errorMessage(result.envelope, t.admin.pages.content.msg.saveFail)));",
    ),
    (
        'setFlash(resultFlash(result.ok, "探活已记录", errorMessage(result.envelope, "探活未成功，请稍后重试")));',
        "setFlash(resultFlash(result.ok, t.admin.pages.tasks.msg.pingOk, errorMessage(result.envelope, t.admin.pages.tasks.msg.pingFail)));",
    ),
]

apply("ops-panels.tsx", OPS)
print("done")
