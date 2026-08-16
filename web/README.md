# PatentClaw 展示页

两个静态页：`index.html` 首页，`example.html` 一次真实运行的逐项记录。
两页共用 `style.css`（设计系统、导航、按钮、章节骨架）。`example.html` 的数据在
`example-data.js`，由 `tools/build_example_data.py` 从 `../patentclaw_data` 生成。
首页内嵌 42 秒演示视频，成片与封面在 `assets/`（源工程 `promo-video/` 约 119MB，不进仓库）。
部署时 `index.html`、`example.html`、`style.css`、`example-data.js`、`assets/` 要一起放，`tools/` 不用。


## 配色

改色动 `style.css` 里的 `:root` 就够（只有这一处）。纸底 `--paper #fbfaf8` / `--paper-2 #f4f1ea`，墨 `--ink #1c1a17`，
朱砂 `--seal #a8352c`（§ 编号、标题、印章、主按钮），黛绿 `--jade #4f6f58`（只给已完成/已映射），
细线 `--rule #e2dcd1` / `--rule-2 #cfc7b8`。Georgia 只用于拉丁文字，避免中文宋体伪粗体。



