from __future__ import annotations

FINANCIAL_KEYTERMS: list[str] = [
    # Chinese
    "应收账款", "应付账款", "资产负债表", "损益表", "现金流量表",
    "账龄", "坏账准备", "折旧摊销", "毛利率", "净利率",
    "营业收入", "营业成本", "管理费用", "财务费用", "销售费用",
    "存货周转率", "应收账款周转率", "净资产收益率", "总资产收益率",
    "权益乘数", "流动比率", "速动比率", "资产负债率",
    # English
    "EBITDA", "ROE", "ROA", "WACC", "NPV", "IRR",
    "accounts receivable", "accounts payable", "balance sheet",
    "income statement", "cash flow statement", "aging analysis",
    "bad debt provision", "depreciation", "amortization",
    "gross margin", "net margin", "operating revenue", "cost of goods sold",
    "days sales outstanding", "inventory turnover", "working capital",
    "accrual", "cash basis", "fiscal year", "quarter",
]


def build_keyterm_list(custom_terms: list[str] | None = None) -> list[str]:
    """Combine built-in financial keyterms with custom terms, deduplicated."""
    seen = set()
    result = []
    for term in FINANCIAL_KEYTERMS + (custom_terms or []):
        if term not in seen:
            seen.add(term)
            result.append(term)
    return result
