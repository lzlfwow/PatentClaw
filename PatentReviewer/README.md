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
- 使用版本化固定检查表；模型只能逐项判定，不能自行增加维度、严重程度或检查项。
- 支持确定性离线审查，以及基于 OpenAI 兼容 Responses API 的在线固定表审查和改稿。
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
                ├→ 18项确定性规则初审
                └→ 12项在线固定检查初审
                         │
                         ▼
                合并问题并计算初审分
                         │
                         ▼
                    生成修订计划
                         │
                         ▼
          按未通过check_id创建独立问题改稿Agent
                         │
                         ├→ 每个Agent仅接收本问题和允许字段
                         ├→ 仅提交“原文片段→修订片段”补丁
                         └→ 缺少事实时返回材料阻塞项
                         │
                         ▼
              合并局部补丁并记录问题关联
                         │
                         ├→ 18项确定性规则复检
                         └→ 12项在线固定检查复检
                                  │
                         仍有问题且产生安全修改？
                           │是              │否
                           └────下一轮──────┤
                                            ▼
                                   计算终审分并导出
```

在线改稿不再使用一次全局改写。每轮将所有 `fail` 和 `needs_human_review` 检查项按
`check_id` 隔离，每项各调用一个问题改稿 Agent。即使同一检查项对应多条 finding，
也只由该检查项的 Agent 处理，不能顺便修改其他检查项。

每个 Agent 只能修改该问题 finding 中声明的 `target_path`，并且只能返回可在原字段
中唯一定位的局部文本替换。程序会拒绝跨字段修改、引用其他问题 finding、原文片段
不唯一或没有实际变化的补丁。每轮修订后重新运行完整固定检查表，尚未解决的问题在
有新修改的情况下继续进入下一轮。默认最多3轮，可通过
`PR_MAX_REVISION_ROUNDS` 调整为1至10轮；一整轮没有产生任何安全修改时提前停止。

缺少原始技术事实的问题也会获得独立 Agent 处置，但 Agent 必须返回 `blocked` 和
所需发明人材料，不能虚构挂接点、参数、公式或实验数据。这里的“逐项处理”表示每项
都有可追溯的修改或阻塞结论，不表示把缺少证据的项目强制伪装成通过。

离线模式不调用模型，只执行确定性规则，并只应用白名单内的机械文本替换。涉及技术
事实、参数、保护范围或效果的问题会保留原文并进入待确认列表。12个语义检查项会
标记为 `not_assessed`，因此离线报告不能得出“完整检查表通过”的结论。

## 固定检查表

当前检查表版本为 `cn-invention-checklist/1.0`，定义在
[`patent_reviewer/checklist.py`](patent_reviewer/checklist.py)。共30项，覆盖13个固定
维度，其中18项由确定性规则执行，12项由在线模型逐项判定。

模型不输出维度和严重程度，这些属性由检查表固定。模型必须恰好返回全部12个语义
检查项；缺项、重复项或未知 `check_id` 都会被拒绝。

| ID | 维度 | 检查项 | 执行器 | 严重程度 | 判定重点 |
| --- | --- | --- | --- | --- | --- |
| `EV-01` | 证据可追溯性 | 核心章节具有证据映射 | rule | major | 总体方案、有益效果和实施方式关联原文或Generator证据 |
| `EV-02` | 证据可追溯性 | 数值与实验结论可逐项追溯 | llm | major | 参数、样本量、结果、比较结论和统计量有直接证据 |
| `FC-01` | 事实一致性 | 技术事实与原始材料一致 | llm | major | 对象、步骤、公式、参数、模型和实验事实不改变原意 |
| `FC-02` | 事实一致性 | 机理与效果使用审慎表述 | llm | minor | 推测性解释不写成确定机理或普遍效果 |
| `UE-01` | 无依据扩写 | 不存在无依据技术扩写 | llm | major | 不补造部件、接口、参数、步骤、附图或应用范围 |
| `CF-01` | 完整性与形式 | 必要章节完整 | rule | critical | 技术领域、背景、问题、方案、效果和实施方式不缺失 |
| `CF-02` | 完整性与形式 | 发明名称简明准确 | rule | minor | 名称体现主题和类型，并符合常规长度控制 |
| `TL-01` | 技术逻辑闭环 | 技术问题来源明确 | rule | major | 技术问题可从现有技术缺陷导出 |
| `TL-02` | 技术逻辑闭环 | 总体方案形成可执行技术链 | rule | major | 方案具有足够步骤和输入、处理、输出关系 |
| `TL-03` | 技术逻辑闭环 | 问题、特征与效果形成因果闭环 | llm | major | 主要效果对应所解决问题和产生效果的技术特征 |
| `EN-01` | 充分公开 | 至少具有一个实施例 | rule | critical | 至少包含一个具体实施方式 |
| `EN-02` | 充分公开 | 实施例达到基本详尽度 | rule | major | 实施方式包含足够流程、条件、参数和结果说明 |
| `EN-03` | 充分公开 | 已知技术缺口已经处理 | rule | major | Generator缺口和发明人确认项已补充或明确处理 |
| `EN-04` | 充分公开 | 核心算法和运行步骤可重复实施 | llm | major | 输入、计算规则、关键条件、输出和异常处理足以实施 |
| `CS-01` | 保护范围支撑 | 关键必要技术特征已提炼 | rule | major | 明确不可缺少特征及其相互关系 |
| `CS-02` | 保护范围支撑 | 替代实施方式和参数层级已整理 | rule | note | 整理有依据的等效手段、可选步骤和参数范围 |
| `CS-03` | 保护范围支撑 | 概括范围受到说明书支持 | llm | major | 方法、系统、介质和上位概括有实施方式及证据支持 |
| `ES-01` | 可专利客体 | 方案属于技术性解决方案 | rule | major | 使用技术手段解决技术问题并获得技术效果 |
| `UN-01` | 单一性 | 共同技术构思可机械识别 | rule | note | 多个问题和创新点具有可识别共同技术联系 |
| `UN-02` | 单一性 | 各保护主题具有同一总的发明构思 | llm | minor | 方法、系统、介质和多个方案共享特定技术特征 |
| `CO-01` | 一致性 | 核心术语统一 | rule | minor | 同一特征使用统一名称并定义简称 |
| `DR-01` | 附图一致性 | 正文引用与附图说明对应 | rule | major | 正文引用附图时存在对应附图说明 |
| `DR-02` | 附图一致性 | 附图内容具有原始证据 | llm | major | 附图数量、节点、关系和实验图形不超过证据支持 |
| `WR-01` | 专利文体 | 使用专利技术文体 | rule | minor | 不保留“本文、作者、我们提出”等论文口吻 |
| `WR-02` | 专利文体 | 避免无条件绝对化表述 | rule | major | “最优、唯一、完全消除”等具有明确评价条件 |
| `WR-03` | 专利文体 | 相对与不确定用语边界清楚 | rule | minor | “适当、较高、大约、可能”等具有参照或范围 |
| `AI-01` | AI算法专项 | AI输入和输出定义完整 | rule | major | 明确输入数据技术含义、输出格式和用途 |
| `AI-02` | AI算法专项 | 模型结构及训练推理边界清楚 | llm | major | 说明模型模块、运行阶段、参数更新范围和部署边界 |
| `AI-03` | AI算法专项 | 算法特征披露充分 | llm | major | 公式、变量、张量位置、损失、约束和参数选择可实施 |
| `AI-04` | AI算法专项 | 算法特征与技术效果存在因果关系 | llm | minor | 算法特征对应计算性能或应用领域可验证技术效果 |

每项检查状态固定为：

- `pass`：现有材料足以确认通过；
- `fail`：存在明确问题；
- `needs_human_review`：材料不足以确认通过，且可能影响申请质量；
- `not_applicable`：该项客观上不适用；
- `not_assessed`：未执行该项，仅用于离线模式的语义检查项。

终审与初审使用相同 `check_id`，并记录 `resolved`、`unchanged`、`regressed` 或
`new_failure`，用于区分问题已解决、仍存在、从未评估项退化或终审新增失败。

## 评分规则

分数不是由模型直接生成，也不取决于模型临时生成多少条问题。程序只根据固定检查表
中状态为 `fail` 或 `needs_human_review` 的检查项扣分；同一 `check_id` 即使影响多个
章节，也最多扣分一次：

| 严重程度 | 每条扣分 | 典型含义 |
| --- | ---: | --- |
| `critical` | 20 | 缺少核心章节、缺少可实施方案等阻断性问题 |
| `major` | 10 | 公开不充分、证据不支持、必要技术特征不清等重大问题 |
| `minor` | 4 | 术语、附图或表述边界等一般问题 |
| `note` | 1 | 建议补充的提醒项 |

```text
总分 = max(0, 100 - 未通过检查项扣分之和)
维度分 = max(0, 100 - 该维度未通过检查项扣分之和)
```

通过条件同时满足：

1. 总分不低于政策配置中的 `pass_score`，当前为 75；
2. 不存在任何 `critical` 或 `major` 未通过检查项；
3. 全部30项均已执行，不能存在 `not_assessed`。

维度分用于定位风险，不再参与总分加权。模型返回的 `confidence` 不参与扣分。评分是
材料风险指标，不代表专利授权概率。

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
│   ├── checklist.py  # 版本化固定检查表与规则映射
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
PR_MAX_REVISION_ROUNDS=3
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
├── revision_attempts.json    # 每轮、每个check_id的独立改稿结果
├── final_disclosure.json     # 结构化最终交底书
├── final_disclosure.md       # Markdown 最终交底书
├── final_disclosure.docx     # Word 最终交底书
├── change_log.json           # 顶层字段修改前后对比
├── final_review.json         # 结构化终审意见
├── final_review.md           # 便于人工阅读的终审意见
└── job.json                  # 完整任务快照和产物索引
```

`revision_attempts.json` 记录每次问题 Agent 的轮次、`check_id`、允许字段、处理结果、
所需材料和局部变更。`change_log.json` 中每条局部修改保留对应 `finding_ids`。

`job.json` 信息最完整，包含标准化输入、初审、修订计划、逐项改稿记录、最终稿、
终审、变更记录、模型名称、终止原因和未解决问题。`data/` 是运行产物目录，默认不
提交到 Git。

## 测试

```bash
python -m pytest -q
```

现有测试覆盖离线端到端导出、缺失内容不被自动编造、Generator 字段证据映射、固定
检查表完整性、语义输出强校验、单项单次扣分、大文档上下文预算、问题级字段隔离和
多轮追修编排。真实在线测试需要有效 API 凭据，因此不作为默认单元测试运行。

## 当前限制

- 原始文件解析当前仅支持 LaTeX 文件、目录和 ZIP，尚未支持 Word/PDF。
- 固定检查表提高了同任务前后可比性，但在线模型给出的判定理由仍可能存在措辞差异。
- 缺少原始证据或发明人信息的问题只能输出材料请求，不能自动补造为通过项。
- 创造性、新颖性、权利要求范围和侵权分析不属于当前自动审查结论。

## 提交前检查

```bash
python -m pytest -q
git status --short
git diff --check
```

确认 `.env`、API 密钥、`data/`、虚拟环境、缓存、构建产物和本地 IDE 配置均未进入
暂存区后再提交。
