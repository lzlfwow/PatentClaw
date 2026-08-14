from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .schemas import ReviewDimension, Severity


Evaluator = Literal["rule", "llm"]


@dataclass(frozen=True)
class CheckSpec:
    check_id: str
    dimension: ReviewDimension
    title: str
    severity: Severity
    evaluator: Evaluator
    criterion: str


CHECKLIST_VERSION = "cn-invention-checklist/1.0"

CHECKLIST: tuple[CheckSpec, ...] = (
    CheckSpec("EV-01", ReviewDimension.evidence_traceability, "核心章节具有证据映射", Severity.major, "rule", "总体方案、有益效果和实施方式应能关联原论文或Generator证据。"),
    CheckSpec("EV-02", ReviewDimension.evidence_traceability, "数值与实验结论可逐项追溯", Severity.major, "llm", "参数、样本量、实验结果、比较结论和统计量应有直接证据。"),
    CheckSpec("FC-01", ReviewDimension.factual_consistency, "技术事实与原始材料一致", Severity.major, "llm", "交底书的对象、步骤、公式、参数、模型和实验事实不得改变原意。"),
    CheckSpec("FC-02", ReviewDimension.factual_consistency, "机理与效果使用审慎表述", Severity.minor, "llm", "推测性解释不得写成已经证实的确定机理或普遍效果。"),
    CheckSpec("UE-01", ReviewDimension.unsupported_expansion, "不存在无依据技术扩写", Severity.major, "llm", "不得补造原材料未披露的部件、接口、参数、步骤、附图内容或应用范围。"),
    CheckSpec("CF-01", ReviewDimension.completeness_form, "必要章节完整", Severity.critical, "rule", "技术领域、背景技术、技术问题、技术方案、有益效果和实施方式均不得缺失。"),
    CheckSpec("CF-02", ReviewDimension.completeness_form, "发明名称简明准确", Severity.minor, "rule", "名称应体现技术主题和类型，且不超过策略配置的常规长度。"),
    CheckSpec("TL-01", ReviewDimension.technical_logic, "技术问题来源明确", Severity.major, "rule", "技术问题应能从现有技术缺陷中导出。"),
    CheckSpec("TL-02", ReviewDimension.technical_logic, "总体方案形成可执行技术链", Severity.major, "rule", "总体方案应分解为足够步骤，并明确输入、处理关系和输出。"),
    CheckSpec("TL-03", ReviewDimension.technical_logic, "问题、特征与效果形成因果闭环", Severity.major, "llm", "每项主要效果应能对应解决的问题和产生该效果的技术特征。"),
    CheckSpec("EN-01", ReviewDimension.enablement, "至少具有一个实施例", Severity.critical, "rule", "交底书至少应包含一个具体实施方式。"),
    CheckSpec("EN-02", ReviewDimension.enablement, "实施例达到基本详尽度", Severity.major, "rule", "实施方式应具有足够的流程、条件、参数和结果说明。"),
    CheckSpec("EN-03", ReviewDimension.enablement, "已知技术缺口已经处理", Severity.major, "rule", "实现发明不可缺少的Generator缺口和发明人确认项应得到补充或明确处理。"),
    CheckSpec("EN-04", ReviewDimension.enablement, "核心算法和运行步骤可重复实施", Severity.major, "llm", "算法输入、计算规则、关键条件、输出和异常处理应足以让本领域人员实现。"),
    CheckSpec("CS-01", ReviewDimension.claim_support, "关键必要技术特征已提炼", Severity.major, "rule", "应明确解决技术问题不可缺少的特征及相互关系。"),
    CheckSpec("CS-02", ReviewDimension.claim_support, "替代实施方式和参数层级已整理", Severity.note, "rule", "应整理有依据的等效手段、可选步骤和参数范围。"),
    CheckSpec("CS-03", ReviewDimension.claim_support, "概括范围受到说明书支持", Severity.major, "llm", "方法、系统、介质及上位概括均应由实施方式和证据支持。"),
    CheckSpec("ES-01", ReviewDimension.eligible_subject, "方案属于技术性解决方案", Severity.major, "rule", "方案应使用技术手段解决技术问题并获得技术效果，而非仅为规则或商业目的。"),
    CheckSpec("UN-01", ReviewDimension.unity, "共同技术构思可机械识别", Severity.note, "rule", "多个问题和创新点之间应具有可识别的共同技术联系。"),
    CheckSpec("UN-02", ReviewDimension.unity, "各保护主题具有同一总的发明构思", Severity.minor, "llm", "方法、系统、介质及多个方案应共享相同或相应的特定技术特征。"),
    CheckSpec("CO-01", ReviewDimension.consistency, "核心术语统一", Severity.minor, "rule", "同一技术特征应使用统一名称并在首次出现时定义简称。"),
    CheckSpec("DR-01", ReviewDimension.drawings, "正文引用与附图说明对应", Severity.major, "rule", "正文引用附图时应存在对应附图说明。"),
    CheckSpec("DR-02", ReviewDimension.drawings, "附图内容具有原始证据", Severity.major, "llm", "附图数量、节点、关系和实验图形不得超过原始材料支持。"),
    CheckSpec("WR-01", ReviewDimension.patent_style, "使用专利技术文体", Severity.minor, "rule", "不得保留本文、作者、我们提出等论文叙述口吻。"),
    CheckSpec("WR-02", ReviewDimension.patent_style, "避免无条件绝对化表述", Severity.major, "rule", "不得使用缺少评价条件的最优、唯一、完全消除等绝对化效果表述。"),
    CheckSpec("WR-03", ReviewDimension.patent_style, "相对与不确定用语边界清楚", Severity.minor, "rule", "适当、较高、大约、可能等词应有参照对象、测量方式或范围。"),
    CheckSpec("AI-01", ReviewDimension.ai_algorithm, "AI输入和输出定义完整", Severity.major, "rule", "应明确模型输入数据的技术含义以及输出格式和用途。"),
    CheckSpec("AI-02", ReviewDimension.ai_algorithm, "模型结构及训练推理边界清楚", Severity.major, "llm", "应说明相关模型模块、训练或推理阶段、参数更新范围及部署边界。"),
    CheckSpec("AI-03", ReviewDimension.ai_algorithm, "算法特征披露充分", Severity.major, "llm", "核心算法公式、变量、张量位置、损失或约束及参数选择应达到可实施程度。"),
    CheckSpec("AI-04", ReviewDimension.ai_algorithm, "算法特征与技术效果存在因果关系", Severity.minor, "llm", "应说明算法特征如何带来计算性能或具体应用领域的可验证技术效果。"),
)

CHECKS_BY_ID = {item.check_id: item for item in CHECKLIST}
RULE_CHECKS = tuple(item for item in CHECKLIST if item.evaluator == "rule")
SEMANTIC_CHECKS = tuple(item for item in CHECKLIST if item.evaluator == "llm")
SEVERITY_WEIGHTS = {Severity.critical: 20, Severity.major: 10, Severity.minor: 4, Severity.note: 1}


def check_for_rule_code(code: str) -> CheckSpec:
    mappings = (
        ("MISSING_", "CF-01"), ("TITLE_", "CF-02"),
        ("SOLUTION_UNDERDETAILED", "TL-02"), ("PROBLEM_NO_DEFECT", "TL-01"),
        ("EFFECT_NO_FEATURE", "TL-02"), ("NO_EMBODIMENT", "EN-01"),
        ("EMBODIMENT_THIN", "EN-02"), ("NO_ALTERNATIVES", "CS-02"),
        ("PAPER_VOICE_", "WR-01"), ("ABSOLUTE_", "WR-02"),
        ("TERM_ALIAS_", "CO-01"), ("DRAWING_DESCRIPTION_MISSING", "DR-01"),
        ("NO_EVIDENCE_", "EV-01"), ("KNOWN_TECHNICAL_GAPS", "EN-03"),
        ("RULE_ONLY_SUBJECT", "ES-01"), ("AI_INPUT_UNCLEAR", "AI-01"),
        ("AI_OUTPUT_UNCLEAR", "AI-01"), ("AI_MODEL_DISCLOSURE_THIN", "EN-02"),
        ("AI_EFFECT_CAUSALITY", "TL-02"), ("NO_ESSENTIAL_FEATURES", "CS-01"),
        ("UNITY_MANUAL_REVIEW", "UN-01"), ("AMBIGUOUS_", "WR-03"),
    )
    for prefix, check_id in mappings:
        if code.startswith(prefix):
            return CHECKS_BY_ID[check_id]
    raise KeyError(f"Rule code {code} is not mapped to the fixed checklist")
