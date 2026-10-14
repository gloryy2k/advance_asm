import { useState } from "react";
import ReactMarkdown from "react-markdown";
import type { ReviewData } from "../api/types";
import { when } from "../lib/format";
import { TrustBadge } from "./layout";

// Advisory only: highlights wording a human should read; never decides for the user.
const KEYWORDS: [RegExp, string][] = [
  [/automat|scanner|scanning|\bbot\b|crawl/i, "tự động/scanner"],
  [/\bllm\b|\bai\b|generative|machine learning/i, "AI/LLM"],
  [/rate[- ]?limit|requests? per|req\/s|\brps\b/i, "rate limit"],
  [/\bdos\b|denial of service|ddos/i, "DoS"],
  [/social engineering|phishing/i, "social engineering"],
  [/prohibit|not allowed|forbidden|must not|do not/i, "cấm/không được"],
];

export function PolicyPanel({ review }: { review: ReviewData }) {
  const [open, setOpen] = useState(false);
  const { policy } = review;
  const text = [policy.text, policy.user_text].filter(Boolean).join("\n\n");
  const hits = KEYWORDS.filter(([re]) => re.test(text)).map(([, label]) => label);
  const source =
    policy.source === "api"
      ? "API HackerOne"
      : policy.source === "public_dump"
        ? "Nguồn công khai (có thể cũ, không đầy đủ)"
        : review.source === "raw"
          ? "Raw scope — không có policy tự động"
          : "Không rõ";
  const perAsset = review.scope.filter((e) => e.instruction);
  return (
    <section className="card" aria-labelledby="policy-h">
      <h2 id="policy-h">Policy &amp; độ tin cậy của scope</h2>
      <TrustBadge trust={review.trust} full />
      <p className="muted">
        Nguồn: {source}
        {policy.fetched_at ? ` · lấy lúc ${when(policy.fetched_at)}` : ""}
      </p>
      {!text && (
        <p className="warnbox">
          Chưa có nội dung policy. Đọc policy chính thức của program (đặc biệt phần scanner/automation) trước khi chạy
          — bạn có thể dán vào tab Program sau khi tạo.
        </p>
      )}
      {hits.length > 0 && (
        <p>
          Policy nhắc tới: {hits.map((h) => (
            <span className="badge medium" key={h}>{h}</span>
          ))}
          <small>Chỉ là gợi ý đọc nhanh — hãy tự đọc nguyên văn.</small>
        </p>
      )}
      {text && (
        <>
          <div className={"policy-text " + (open ? "open" : "")}>
            <ReactMarkdown>{text}</ReactMarkdown>
          </div>
          <button type="button" className="secondary small" onClick={() => setOpen(!open)} aria-expanded={open}>
            {open ? "Thu gọn" : "Xem đầy đủ"}
          </button>
        </>
      )}
      {perAsset.length > 0 && (
        <details>
          <summary>Hướng dẫn riêng theo asset ({perAsset.length})</summary>
          <ul>
            {perAsset.map((e) => (
              <li key={e.pattern + e.kind}>
                <code>{e.pattern}</code> — {e.instruction}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
