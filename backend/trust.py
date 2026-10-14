"""How far the scope and policy can be trusted — shown wherever they are shown."""


def scope_trust(source, handle, policy):
    policy = policy or {}
    origin = policy.get("policy_source")
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
                "missing": [] if has_text else ["policy"], "checklist": [] if has_text else ["Đọc policy trên trang chính thức"], "official_url": url}
    missing = [] if has_text or user_text else ["policy đầy đủ"]
    return {"level": "public", "verified": False, "label": "CHƯA XÁC MINH — dữ liệu công khai",
            "detail": "Lấy từ bản sao công khai (bounty-targets-data): có thể đã cũ, thiếu policy, thiếu hướng dẫn riêng từng asset.",
            "missing": missing + ["xác nhận scope hiện hành"],
            "checklist": ["Mở trang program chính thức và đọc policy (mục automation/scanner, rate limit).",
                          "So IN/OUT từng asset với danh sách bên dưới.",
                          "Dán policy vào tab Program (hoặc dùng API token để lấy tự động)."],
            "official_url": url}
