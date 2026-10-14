"""Review harness: desktop+mobile screenshots of every page against mock_h1_server.py.
Needs pip playwright==1.56.0 (matches preinstalled chromium-1194) and PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers."""
import os, sys
from playwright.sync_api import sync_playwright
S=os.environ.get("SCR","/tmp/bbasm-mock"); os.makedirs(f"{S}/shots",exist_ok=True); B=os.environ.get("BBASM_URL","http://127.0.0.1:18766")
def shot(page,name): page.screenshot(path=f"{S}/shots/{name}.png", full_page=True)
with sync_playwright() as p:
    b=p.chromium.launch()
    for tag,vp in (("d",{"width":1366,"height":850}),("m",{"width":390,"height":800})):
        pg=b.new_page(viewport=vp)
        pg.goto(B+"/#/"); pg.wait_for_timeout(700); shot(pg,f"{tag}1_portfolio")
        pg.goto(B+"/#/new"); pg.wait_for_timeout(300); shot(pg,f"{tag}2_new_raw")
        pg.get_by_label("Nguồn").select_option("h1"); shot(pg,f"{tag}3_new_h1")
        pg.get_by_label("HackerOne handle hoặc URL").fill("https://hackerone.com/acme")
        pg.get_by_role("button",name="Resolve & review").click(); pg.wait_for_timeout(1000); shot(pg,f"{tag}4_review")
        pg.goto(B+"/#/target/acme"); pg.wait_for_timeout(700); shot(pg,f"{tag}5_target_overview")
        for t in ("Surface","Assets","Diff","Findings","Brief","Program"):
            pg.get_by_role("button",name=t,exact=True).click(); pg.wait_for_timeout(500); shot(pg,f"{tag}6_{t.lower()}")
        pg.goto(B+"/#/scan/1"); pg.wait_for_timeout(1200); shot(pg,f"{tag}7_scanpage")
        pg.close()
    b.close()
