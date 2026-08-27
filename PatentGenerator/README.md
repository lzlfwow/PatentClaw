# PatentGenerator

一个只负责“**LaTeX论文 → 中文技术交底书**”环节的独立后端Agent项目。前端团队只需要调用HTTP API，不需要理解模型编排和文档生成细节。

## 为什么采用多个Sub-Agent

论文转技术交底书不是一次普通改写。论文强调研究贡献和实验表现，技术交底书要求明确技术问题、必要技术特征、步骤关系、替代方案、实施例和证据支持。因此本项目将正式生成流程拆分给五个专业Sub-Agent，并把文件解析和文档导出保留为确定性工具。独立审查默认启用且不进入正式交底书正文，可通过环境变量显式关闭。

```text
LaTeX / ZIP
   │
   ▼
LaTeX Parser Tool ── 展开input/include、解析章节/公式/图注、建立证据账本
   │
   ▼
01 Paper Understanding Agent ── 研究目标、输入、步骤、输出、实验结论
   │
   ▼
02 Invention Mining Agent ───── 技术问题、发明构思、必要特征、替代方案
   │
   ▼
03 Technical Solution Agent ─── S101式步骤、组件、数据流、参数关系
   │
   ▼
04 Embodiment & Evidence Agent  实施例、实验支持、附图规划、证据映射
   │
   ▼
05 Disclosure Writer Agent ──── 电通类技术交底书完整草案
   │
   ▼
06 Independent Review Agent ─── 支持性、完整性、公式规范、一致性和虚构风险审查
   │
   ▼
Patent Figure Generator ─────── 黑白专利附图PNG + 可编辑Mermaid源文件
   │
   ▼
Export Tool ─────────────────── JSON / Markdown / DOCX / 附图包
```

### Sub-Agent职责

`PaperUnderstandingAgent`负责忠实理解论文，不进行专利判断。它只提取技术领域、研究目标、输入、处理步骤、输出和实验结论，并记录证据编号。

`InventionMiningAgent`按照“技术问题—技术手段—技术效果”识别可专利化特征，区分必要特征与优选特征，提出不超过25个汉字的发明名称，并形成发明人待确认问题。

`TechnicalSolutionAgent`将论文叙述重构为可实施的技术链条，生成S101开始的方法步骤、系统组件、数据流、参数约束和替代路径。

`EmbodimentEvidenceAgent`将实验、算法、公式和图注组织为实施例、实验依据、附图计划与“技术特征—论文证据”映射，不受支持的内容必须进入待确认清单。

`DisclosureWriterAgent`按照中国电通类技术交底书的五大栏目组织正文，并以分节方式覆盖技术领域、背景技术、现有技术缺陷、技术问题、详细方案、创新点、有益效果、实施例、实验依据、附图说明、系统实现、数据与接口、术语、实施边界、替代方案和待确认事项。公式使用LaTeX标记进入导出器后转换为可编辑的Word原生公式，向量、花体符号以及上下标按数学规范排版。

`IndependentReviewAgent`不参与正文撰写；默认独立检查标题长度、中文化、章节完整性、缺陷与方案及优点的对应关系、公式记法、实验表图、术语一致性、证据支持、实施充分性和虚构风险。审查结果保留在任务JSON中，不写入正式DOCX正文；设置`L2D_ENABLE_REVIEW=false`可显式关闭。

### 专利附图重绘

系统不会把论文中的PNG、JPG或PDF原图插入技术交底书。论文图注只作为技术证据线索；附图生成器依据结构化技术方案重新组织节点和连线，生成白底黑线、带S101步骤号或模块标号的中文专利附图。

每幅附图同时提供PNG和Mermaid `.mmd` 源文件。Mermaid是开源且便于人工编辑的图形描述格式；生产运行时使用本项目的Pillow确定性渲染器生成PNG，因此不要求额外安装Node.js、Chromium或Graphviz，也不会因外部渲染服务不可用而回退到论文原图。附图包中的`manifest.json`记录每幅图的类型、文件名和来源策略。

## 输入能力

- 单个`.tex`文件；
- 包含完整LaTeX工程的`.zip`文件；
- CLI可以直接传入工程目录；
- 支持递归展开`\input{}`和`\include{}`；
- 提取标题、摘要、章节、公式、表格、算法、图注和参考文献标题；
- 防止ZIP路径穿越、超大解压包和循环include。

## 安装与离线验证

```powershell
cd F:\下载\PatentGenerator
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest -q
```

离线运行示例：

```powershell
$env:L2D_OFFLINE_MODE="true"
latex2disclosure examples\sample.tex
```

离线模式用于验证解析、Sub-Agent接口、状态流转和导出，不调用模型API。其文本质量是结构验证级别，不应作为正式专利申请文件。

## 在线模型模式

```powershell
$env:L2D_OFFLINE_MODE="false"
$env:OPENAI_API_KEY="你的服务端Key"
$env:L2D_MODEL="gpt-5.4-mini"
$env:L2D_REVIEW_MODEL="gpt-5.4"
$env:L2D_ENABLE_REVIEW="true"
```

所有Sub-Agent通过`ModelGateway`请求Pydantic结构化输出。模型密钥只存在后端环境变量中，不能由前端上传或保存。

## 启动API

```powershell
latex2disclosure-api
```

默认地址：`http://127.0.0.1:8100`，接口文档：`http://127.0.0.1:8100/docs`。

## 前端对接

创建任务：

```http
POST /api/jobs/upload
Content-Type: multipart/form-data

file=<paper.tex或project.zip>
```

返回：

```json
{"job_id":"l2d-xxxxxxxxxxxx","status":"queued"}
```

轮询状态：

```http
GET /api/jobs/{job_id}
```

前端可以使用`events`字段展示LaTeX解析、五个正文Sub-Agent、独立审查和导出工具的实时阶段状态；显式关闭独立审查时不产生审查阶段。

下载产物：

```http
GET /api/jobs/{job_id}/artifacts/json
GET /api/jobs/{job_id}/artifacts/markdown
GET /api/jobs/{job_id}/artifacts/docx
GET /api/jobs/{job_id}/artifacts/figures
```

其他接口：

```http
GET /api/health
GET /api/jobs
```

## 核心目录

```text
latex2disclosure/
├── agents/                  # 五个正文Sub-Agent + 一个可选审查Agent
│   ├── base.py              # AgentContext、ModelGateway、统一接口
│   ├── paper_understanding.py
│   ├── invention_mining.py
│   ├── technical_solution.py
│   ├── embodiment_evidence.py
│   ├── disclosure_writer.py
│   └── reviewer.py
├── latex_parser.py          # LaTeX/ZIP解析和证据账本
├── schemas.py               # 全部阶段的数据契约
├── pipeline.py              # Pipeline编排、状态和失败处理
├── patent_figures.py        # 专利附图规格、Mermaid输出和黑白PNG重绘
├── exporter.py              # Markdown、JSON、DOCX导出
├── storage.py               # 原子化任务状态持久化
├── api.py                   # 供前端调用的FastAPI接口
└── cli.py                   # 命令行入口
```

## 生产化注意事项

当前文件存储和FastAPI BackgroundTasks适合单机原型。多人使用时应替换为PostgreSQL、对象存储和Celery/RQ等任务队列，并加入登录、项目权限、调用费用上限、审计日志和数据保留策略。正式专利使用前必须由发明人确认技术事实，并由专利代理师执行专业检索和法律审阅。
