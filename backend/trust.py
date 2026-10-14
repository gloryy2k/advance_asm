"""How far the scope and policy can be trusted — shown wherever they are shown."""


AUTO_CATEGORIES = {"web", "wildcard", "ip", "cidr"}
SOURCE_LABELS = {"api": "API HackerOne (có token)", "public_page": "Trang công khai HackerOne",
                 "public_dump": "Bản sao bounty-targets-data"}


def _policy_text(policy):
    return (policy.get("policy_text") or (policy.get("program") or {}).get("policy") or "").strip()


def launch_gate(source, policy):
    """Which depths the available scope/policy data can support. Passive never touches the target.

    Light/Strong need: a structured source that is not just the public dump, policy text (from the program or pasted
    by the user), no IN/OUT item we could not classify as OUT, and at least one clearly named IN asset recon can target.
    Missing data is reported, never guessed."""
    if source != "h1":
        return {"allowed_depths": ["passive", "light", "strong"], "reasons": [], "missing": []}
    policy = policy or {}
    reasons, missing = [], []
    origin = policy.get("policy_source")
    if origin not in ("api", "public_page"):
        missing.append("nguồn có cấu trúc hiện hành")
        reasons.append("Scope chỉ lấy từ bản sao bounty-targets-data (có thể đã cũ, không kèm policy). Dùng token API, hoặc nhập scope thủ công sau khi đọc policy chính thức.")
    if not (_policy_text(policy) or (policy.get("user_policy_text") or "").strip()):
        missing.append("policy")
        reasons.append("Chưa có nội dung policy (automation/scanner/rate limit). Dán policy ở bước nhập rồi Resolve lại.")
    classification = policy.get("classification") or {}
    if any(u.get("kind") == "out" for u in classification.get("unclassified", [])):
        missing.append("OUT chưa phân loại")
        reasons.append("Có mục OUT không phân loại được nên không chắc phần nào bị loại trừ.")
    short = [f"{label} {c['fetched']}/{c['total']}" for key, label in (("in", "IN"), ("out", "OUT"))
             for c in [(policy.get("completeness") or {}).get(key)] if c and c["fetched"] < c["total"]]
    if short:
        missing.append("asset chưa đọc đủ")
        reasons.append("Trang cho biết nhiều asset hơn số đã đọc (" + ", ".join(short) + "): có thể thiếu mục IN/OUT.")
    if not any(a.get("kind") == "in" and a.get("category") in AUTO_CATEGORIES for a in policy.get("assets", [])):
        missing.append("IN phân loại rõ")
        reasons.append("Không có asset IN nào được phân loại rõ (domain/wildcard/IP/CIDR) để quét tự động.")
    return {"allowed_depths": ["passive"] if reasons else ["passive", "light", "strong"], "reasons": reasons, "missing": missing}


def scope_trust(source, handle, policy):
    policy = policy or {}
    origin = policy.get("policy_source")
    fetched = policy.get("fetched_at")
    has_text = bool((policy.get("policy_text") or "").strip() or (policy.get("program") or {}).get("policy"))
    user_text = bool((policy.get("user_policy_text") or "").strip())
    url = f"https://hackerone.com/{handle}" if handle else None
    if source != "h1":
        return {"level": "manual", "verified": False, "label": "Scope do bạn nhập tay",
                "detail": "Hệ thống không đối chiếu với nền tảng nào. Bạn chịu trách nhiệm scope đúng với program.",
                "missing": [], "checklist": [], "official_url": None}
    if origin == "api":
        return {"level": "api", "verified": True, "label": "Đã lấy qua API HackerOne",
                "detail": "Scope có phân loại IN/OUT từ API chính thức" + (" kèm policy." if has_text else ", nhưng policy trống."),
                "missing": [] if has_text else ["policy"], "checklist": [] if has_text else ["Đọc policy trên trang chính thức"], "official_url": url,
                "source": origin, "fetched_at": fetched}
    classification = policy.get("classification") or {}
    unclassified = classification.get("unclassified_count") or 0
    if origin == "public_page":
        counts = policy.get("completeness")
        short = bool(counts) and any(counts[k]["fetched"] < counts[k]["total"] for k in ("in", "out"))
        missing = ([] if has_text or user_text else ["policy"]) + ([f"{unclassified} asset chưa phân loại"] if unclassified else []) \
            + (["asset chưa đọc đủ"] if short else [])
        count_text = (f" Đối chiếu số lượng: IN {counts['in']['fetched']}/{counts['in']['total']}, OUT {counts['out']['fetched']}/{counts['out']['total']}."
                      if counts else " Chưa đối chiếu được số lượng asset với trang.")
        return {"level": "public_page", "verified": False, "label": "Trang công khai HackerOne — chưa xác minh bằng API",
                "detail": "Policy và scope có cấu trúc đọc (chỉ đọc, không cần token) từ trang program công khai"
                          + (f" lúc {fetched}." if fetched else ".") + count_text + " Chưa đối chiếu bằng API nên vẫn cần bạn đọc trang chính thức.",
                "missing": missing, "source": origin, "fetched_at": fetched,
                "checklist": ["Mở trang program chính thức và đọc policy (mục automation/scanner, rate limit).",
                              "So IN/OUT với danh sách bên dưới; asset 'Open Scope' không được tự hiểu là được quét mọi host."],
                "official_url": url}
    missing = [] if has_text or user_text else ["policy đầy đủ"]
    return {"level": "public", "source": origin, "fetched_at": fetched, "verified": False, "label": "CHƯA XÁC MINH — dữ liệu công khai",
            "detail": "Lấy từ bản sao công khai (bounty-targets-data): có thể đã cũ, thiếu policy, thiếu hướng dẫn riêng từng asset.",
            "missing": missing + ["xác nhận scope hiện hành"],
            "checklist": ["Mở trang program chính thức và đọc policy (mục automation/scanner, rate limit).",
                          "So IN/OUT từng asset với danh sách bên dưới.",
                          "Dán policy vào tab Program (hoặc dùng API token để lấy tự động)."],
            "official_url": url}
