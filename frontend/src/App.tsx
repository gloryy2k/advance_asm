import { useEffect, useState } from "react";
import { NewScan } from "./pages/NewScan";
import { Portfolio } from "./pages/Portfolio";
import { Program } from "./pages/Program";
import { Help } from "./pages/Help";
import { Profiles } from "./pages/Profiles";
import { Review } from "./pages/Review";
import { Run } from "./pages/Run";
import { Tools } from "./pages/Tools";
import { parseRoute, useHashPath } from "./lib/router";

export { Help, NewScan, Portfolio, Profiles, Program, Review, Run, Tools };

export function App() {
  const path = useHashPath();
  const [dark, setDark] = useState(() => {
    try {
      return localStorage.getItem("theme") !== "light";
    } catch {
      return true;
    }
  });
  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    try {
      localStorage.setItem("theme", dark ? "dark" : "light");
    } catch {
      /* storage can be unavailable (private mode); theme just is not remembered */
    }
  }, [dark]);
  const route = parseRoute(path);
  return (
    <div className="shell">
      <a className="skip" href="#main">Bỏ qua điều hướng</a>
      <aside>
        <a className="brand" href="#/">
          ◈ BBASM<span>Attack surface workspace</span>
        </a>
        <nav aria-label="Chính">
          <a href="#/" aria-current={route.page === "portfolio" ? "page" : undefined}>▦ Danh mục</a>
          <a href="#/new" aria-current={route.page === "new" ? "page" : undefined}>＋ Thêm program</a>
          <a href="#/profiles" aria-current={route.page === "profiles" ? "page" : undefined}>⚙ Profile quét</a>
          <a href="#/tools" aria-current={route.page === "tools" ? "page" : undefined}>⚒ Công cụ &amp; môi trường</a>
          <a href="#/help" aria-current={route.page === "help" ? "page" : undefined}>? Chức năng &amp; kết quả</a>
        </nav>
        <div className="sidebar-bottom">
          <p>
            Scope first.
            <br />
            Hunt with context.
          </p>
          <button className="secondary" onClick={() => setDark(!dark)}>
            {dark ? "☀ Chế độ sáng" : "☾ Chế độ tối"}
          </button>
        </div>
      </aside>
      <main id="main">
        {route.page === "new" ? (
          <NewScan />
        ) : route.page === "review" ? (
          <Review key={path} id={route.id} />
        ) : route.page === "run" ? (
          <Run key={path} id={route.id} />
        ) : route.page === "help" ? (
          <Help />
        ) : route.page === "profiles" ? (
          <Profiles />
        ) : route.page === "tools" ? (
          <Tools focus={route.focus} />
        ) : route.page === "program" ? (
          <Program key={route.slug} slug={route.slug} tab={route.tab} view={route.view} />
        ) : (
          <Portfolio />
        )}
        <footer>BBASM · Resolve → review → launch · Dashboard chỉ tạo thư mục và brief; bạn tự chạy agent</footer>
      </main>
    </div>
  );
}
