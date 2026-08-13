# PatentReviewer

PatentReviewer 是 PatentClaw 的交底书审查与修订模块。它接收 PatentGenerator
生成的结构化技术交底书初稿和原始论文，输出初审意见、修订计划、证据约束下的
最终版交底书、变更记录与终审意见。

当前实现面向中国发明专利技术交底书。它用于发现材料风险和辅助整理，不替代专利
代理师的权利要求撰写、专利性检索、法律意见或国家知识产权局的正式审查。

## 功能概览

- 对照原始论文和 Generator 证据，检查事实一致性、证据可追溯性和无依据扩写。
- 检查交底书章节完整性、问题-方案-效果闭环、充分公开和可实施性。
- 检查保护范围支撑、必要技术特征、替代实施方式、单一性和可专利客体风险。
- 检查术语、附图、专利文体、绝对化表述和不确定用语。
- 对 AI/算法方案检查输入输出、模型结构、训练/推理边界及技术效果因果关系。
- 支持确定性离线审查，以及基于 OpenAI 兼容 Responses API 的在线语义审查和改稿。
- 输出 JSON、Markdown 和 DOCX，保留问题、证据及修改前后内容以便人工复核。

## 与 PatentGenerator 的协作

两个模块通过文件契约协作，不直接导入彼此的 Python 包：

```text
原始 LaTeX ───────────────────────────────┐
                                         │
原始 LaTeX → PatentGenerator → job.json ─┼→ PatentReviewer
                                         │       │
                                         │       ├→ 初审意见
                                         │       ├→ 修订计划
                                         │       ├→ 最终交底书
                                         │       └→ 终审意见
                                         │
                                         └→ 原文证据核对
```

`--generator-job` 可传入以下任意一种路径：

- PatentGenerator 的 `job.json`；
- 包含 `job.json` 的 `artifacts/` 目录；
- 包含 `artifacts/job.json` 的 Generator 任务目录。

Generator 的 `job.json` 必须包含结构化 `disclosure`。Reviewer 优先使用其中的
`evidence`、`evidence_mapping` 和 `unsupported_items`；若不存在 `evidence`，则从
原始 LaTeX 的章节建立后备证据片段。

`--source` 当前支持：

- 单个 `.tex` 文件；
- 包含 LaTeX 项目的目录；
- LaTeX `.zip` 包；
- `\input{}` 和 `\include{}` 引用的子文件。

Word 和 PDF 输入尚未接入当前 loader，不能仅通过修改文件扩展名使用。

## 数据流

在线模式的完整流程如下：

```text
Generator job.json + 原始 LaTeX
                │
                ▼
        输入解析、标准化和校验
                │
                ▼
     ReviewInput（初稿 + 原文 + 证据）
                │
                ├→ 确定性规则初审
                └→ 在线模型语义初审
                         │
                         ▼
                合并问题并计算初审分
                         │
                         ▼
                    生成修订计划
                         │
                         ▼
              在线模型执行证据约束改稿
                         │
                         ▼
                 生成字段级变更记录
                         │
                         ├→ 确定性规则复检
                         └→ 在线模型语义终审
                                  │
                                  ▼
                         计算终审分并导出
```

离线模式不调用模型，只执行确定性规则，并只应用白名单内的机械文本替换。涉及技术
事实、参数、保护范围或效果的问题会保留原文并进入待确认列表。

## 评分规则

分数不是由模型直接生成。规则引擎和在线模型都只产生结构化问题
`ReviewFinding`，程序再按照严重程度统一扣分：

| 严重程度 | 每条扣分 | 典型含义 |
| --- | ---: | --- |
| `critical` | 20 | 缺少核心章节、缺少可实施方案等阻断性问题 |
| `major` | 10 | 公开不充分、证据不支持、必要技术特征不清等重大问题 |
| `minor` | 4 | 术语、附图或表述边界等一般问题 |
| `note` | 1 | 建议补充的提醒项 |

```text
总分 = max(0, 100 - 全部问题扣分之和)
维度分 = max(0, 100 - 该维度问题扣分之和)
```

通过条件同时满足：

1. 总分不低于政策配置中的 `pass_score`，当前为 75；
2. 不存在任何 `critical` 或 `major` 问题。

维度分用于定位风险，不再参与总分加权。模型返回的 `confidence` 当前也不参与扣分。
评分是材料风险指标，不代表专利授权概率。

## 审查基线

政策配置位于
[`patent_reviewer/policies/default_cn_invention.yaml`](patent_reviewer/policies/default_cn_invention.yaml)，
其中版本化保存检查维度、阈值、文体词表和法律依据。当前基线主要参考：

- 《中华人民共和国专利法》第二十六条、第三十一条；
- 《中华人民共和国专利法实施细则》；
- 《专利审查指南》中有关说明书、计算机程序和人工智能申请的要求；
- 《人工智能相关发明专利申请指引（试行）》。

政策配置是工程审查基线。法规和审查指南可能更新，提交前仍须核对国家知识产权局
现行要求并由专业人员复核。

## 目录结构

```text
PatentReviewer/
├── patent_reviewer/
│   ├── agents/       # 在线语义初审、终审和证据约束改稿
│   ├── evidence/     # 证据索引与字段证据匹配
│   ├── exporters/    # JSON、Markdown、DOCX 导出
│   ├── ingestion/    # Generator 和 LaTeX 输入适配
│   ├── policies/     # 中国发明专利审查政策配置
│   ├── prompts/      # 审查与改稿提示词参考
│   ├── revision/     # 修订计划和离线安全修改
│   ├── rules/        # 确定性审查规则
│   ├── api.py        # FastAPI 接口
│   ├── cli.py        # 命令行入口
│   ├── pipeline.py   # 端到端流程编排
│   ├── reporting.py  # 问题合并和评分
│   └── schemas.py    # Pydantic 数据契约
├── tests/
├── .env.example
├── .gitignore
└── pyproject.toml
```

## 环境安装

Python 要求为 3.10 或更高。项目约定安装到已有 `patentclaw` Conda 环境：

```bash
conda activate patentclaw
cd /mnt/workspace/junqi_projects/Junqi_Project/PatentClaw/PatentReviewer
python -m pip install -e '.[dev]'
```

安装后提供两个命令：

- `patent-reviewer`：运行审查任务或启动 API；
- `patent-reviewer-api`：使用默认地址启动 API。

## 离线运行

```bash
patent-reviewer run \
  --generator-job /path/to/generator-task/artifacts/job.json \
  --source /path/to/paper.tex \
  --output ./data
```

离线模式适合测试输入契约、确定性规则和导出流程。它不会完成事实一致性等复杂语义
判断，产物中的 `limitations` 会明确记录这一限制。

## 在线运行

复制环境变量模板并填入本地配置：

```bash
cp .env.example .env
```

使用官方 OpenAI 端点时，只需配置密钥和可用模型：

```dotenv
PR_OPENAI_API_KEY=your_api_key
PR_OPENAI_BASE_URL=https://api.openai.com/v1
PR_OPENAI_MODEL=your_model
PR_ENABLE_SEMANTIC_REVIEW=false
```

使用 OpenAI 兼容第三方端点时，将 `PR_OPENAI_BASE_URL`、`PR_OPENAI_MODEL` 和必要
请求头改为服务商给出的值。第三方端点必须实际支持 Responses API、结构化输出、
`responses.parse` 和 `store=False`。

运行在线全链路：

```bash
patent-reviewer run \
  --generator-job /path/to/generator-task/artifacts/job.json \
  --source /path/to/paper.tex \
  --output ./data \
  --online
```

也可以设置 `PR_ENABLE_SEMANTIC_REVIEW=true`，让未显式传入 `--online` 的任务默认启用
在线模式。API 密钥只应保存在环境变量或被 Git 忽略的 `.env` 中，不要写入代码、
README、测试数据或提交记录。

## HTTP API

启动服务：

```bash
patent-reviewer serve --host 127.0.0.1 --port 8011
```

健康检查：

```bash
curl http://127.0.0.1:8011/health
```

创建任务：

```bash
curl -X POST http://127.0.0.1:8011/reviews \
  -H 'Content-Type: application/json' \
  -d '{
    "generator_job_path": "/path/to/job.json",
    "source_path": "/path/to/paper.tex",
    "output_root": "./data",
    "online": false
  }'
```

当前 API 在请求周期内同步等待整条流水线完成；尚未实现任务队列、异步轮询和持久化
数据库。

## 输出产物

每次运行创建独立任务目录：

```text
data/review-<id>/artifacts/
├── initial_review.json       # 结构化初审意见
├── initial_review.md         # 便于人工阅读的初审意见
├── revision_plan.json        # 自动动作与待确认动作
├── final_disclosure.json     # 结构化最终交底书
├── final_disclosure.md       # Markdown 最终交底书
├── final_disclosure.docx     # Word 最终交底书
├── change_log.json           # 顶层字段修改前后对比
├── final_review.json         # 结构化终审意见
├── final_review.md           # 便于人工阅读的终审意见
└── job.json                  # 完整任务快照和产物索引
```

`job.json` 信息最完整，包含标准化输入、初审、修订计划、最终稿、终审、变更记录、
模型名称和未解决问题。`data/` 是运行产物目录，默认不提交到 Git。

## 测试

```bash
python -m pytest -q
```

现有测试覆盖离线端到端导出、缺失内容不被自动编造，以及 Generator 字段证据映射。
在线测试需要有效 API 凭据，因此不作为默认单元测试运行。

## 当前限制

- 原始文件解析当前仅支持 LaTeX 文件、目录和 ZIP，尚未支持 Word/PDF。
- 在线问题的维度名称尚未强制映射到固定枚举，报告中可能出现近义维度。
- 规则和模型对同一根因使用不同表述时，可能未被完全去重。
- 在线变更日志当前为顶层字段粒度，尚未精确关联每条修改解决的 finding。
- 创造性、新颖性、权利要求范围和侵权分析不属于当前自动审查结论。

## 提交前检查

```bash
python -m pytest -q
git status --short
git diff --check
```

确认 `.env`、API 密钥、`data/`、虚拟环境、缓存、构建产物和本地 IDE 配置均未进入
暂存区后再提交。
