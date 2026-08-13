from __future__ import annotations

import re
from collections import Counter

from ..evidence import EvidenceIndex
from ..policies import ReviewPolicy
from ..schemas import (
    DimensionScore, ReviewFinding, ReviewInput, ReviewReport, Severity, TechnicalDisclosure
)


WEIGHTS = {Severity.critical: 20, Severity.major: 10, Severity.minor: 4, Severity.note: 1}


class RuleEngine:
    def __init__(self, policy: ReviewPolicy) -> None:
        self.policy = policy
        self.legal = policy.legal_references

    def review(self, review_input: ReviewInput) -> ReviewReport:
        disclosure = review_input.disclosure
        evidence = EvidenceIndex(review_input)
        findings: list[ReviewFinding] = []
        findings += self._structure(disclosure)
        findings += self._title(disclosure)
        findings += self._problem_solution_effect(disclosure, evidence)
        findings += self._enablement(disclosure, evidence)
        findings += self._drafting_style(disclosure)
        findings += self._consistency(disclosure)
        findings += self._drawings(disclosure)
        findings += self._evidence_coverage(disclosure, evidence)
        findings += self._eligible_subject_matter(disclosure)
        findings += self._ai_disclosure(disclosure)
        findings += self._known_disclosure_gaps(review_input)
        findings += self._claim_support(disclosure)
        findings += self._ambiguous_language(disclosure)

        counts = Counter(item.dimension for item in findings)
        dimensions = []
        for dimension in self.policy.get("dimensions", sorted(counts)):
            penalty = sum(WEIGHTS[item.severity] for item in findings if item.dimension == dimension)
            dimensions.append(DimensionScore(dimension=dimension, score=max(0, 100 - penalty), finding_count=counts[dimension]))
        score = max(0, 100 - sum(WEIGHTS[item.severity] for item in findings))
        blocking = any(item.severity in (Severity.critical, Severity.major) for item in findings)
        return ReviewReport(
            legal_baseline=self.policy.baseline,
            score=score,
            passed=score >= int(self.policy.get("pass_score", 75)) and not blocking,
            findings=findings,
            dimensions=dimensions,
            human_review_checklist=[
                "确认申请主体、发明人及公开时间等程序性信息",
                "确认拟保护主题及必要技术特征，最终权利要求由专利代理师审核",
                "确认新增实施方式、参数范围和技术效果均有原始材料支持",
                "在提交前按国家知识产权局现行表格和电子申请格式进行终检",
            ],
            limitations=[
                "本工具审查对象是技术交底书，不替代权利要求撰写、专利性检索或法律意见。",
                "规则检查只能识别可形式化风险；创造性、保护范围和等同侵权判断须人工完成。",
            ],
        )

    def _finding(self, *, dimension: str, severity: Severity, code: str, section: str, path: str,
                 issue: str, risk: str, suggestion: str, legal: str = "", original: str = "",
                 evidence_ids: list[str] | None = None, auto: bool = False, confirm: bool = False) -> ReviewFinding:
        return ReviewFinding(
            finding_id=f"F-{code}", dimension=dimension, severity=severity, code=code,
            legal_basis=[legal] if legal else [], target_section=section, target_path=path,
            original_text=original, issue=issue, risk=risk, evidence_ids=evidence_ids or [],
            suggested_revision=suggestion, auto_fixable=auto, requires_inventor_confirmation=confirm,
        )

    def _structure(self, d: TechnicalDisclosure) -> list[ReviewFinding]:
        required = {
            "technical_field": ("技术领域", "明确发明所属或直接应用的具体技术领域"),
            "background": ("背景技术", "补充最接近现有技术及其客观缺陷"),
            "technical_problem": ("要解决的技术问题", "从现有技术缺陷导出明确技术问题"),
            "overall_solution": ("技术方案", "补充包含必要技术特征的完整总体方案"),
            "beneficial_effects": ("有益效果", "逐项说明技术特征带来的可验证效果"),
            "embodiments": ("具体实施方式", "补充至少一个可重复实施的完整实施例"),
        }
        findings = []
        for field, (section, suggestion) in required.items():
            if not getattr(d, field):
                findings.append(self._finding(
                    dimension="完整性与形式", severity=Severity.critical, code=f"MISSING_{field.upper()}",
                    section=section, path=field, issue=f"缺少{section}",
                    risk="说明书基础材料不完整，可能无法满足清楚、完整公开要求。",
                    suggestion=suggestion, legal=self.legal.get("necessary_sections", ""), confirm=True,
                ))
        return findings

    def _title(self, d: TechnicalDisclosure) -> list[ReviewFinding]:
        if not d.invention_title:
            return [self._finding(dimension="完整性与形式", severity=Severity.major, code="TITLE_EMPTY",
                    section="发明名称", path="invention_title", issue="发明名称为空",
                    risk="无法准确表明申请主题。", suggestion="使用简明、准确、反映主题和类型的技术名称。", confirm=True)]
        max_chars = int(self.policy.get("title_max_chars", 25))
        if len(d.invention_title) > max_chars:
            return [self._finding(dimension="完整性与形式", severity=Severity.minor, code="TITLE_LONG",
                    section="发明名称", path="invention_title", issue=f"发明名称为{len(d.invention_title)}字，超过常规{max_chars}字控制值",
                    risk="名称可能不够简明。", suggestion="压缩非必要修饰语，同时保留主题和技术类型。", original=d.invention_title)]
        return []

    def _problem_solution_effect(self, d: TechnicalDisclosure, evidence: EvidenceIndex) -> list[ReviewFinding]:
        findings = []
        if d.overall_solution and len(d.detailed_steps) < int(self.policy.get("minimum_steps", 3)):
            findings.append(self._finding(dimension="技术逻辑闭环", severity=Severity.major, code="SOLUTION_UNDERDETAILED",
                section="技术方案", path="detailed_steps", issue="总体方案未分解为足够的可执行步骤或结构关系",
                risk="必要技术特征可能遗漏，难以支撑后续权利要求。", suggestion="按输入、处理、约束、输出补齐步骤及步骤间关系。",
                legal=self.legal.get("clear_complete", ""), evidence_ids=evidence.ids_for(d.overall_solution), confirm=True))
        if d.technical_problem and not d.prior_art_defects:
            findings.append(self._finding(dimension="技术逻辑闭环", severity=Severity.major, code="PROBLEM_NO_DEFECT",
                section="背景技术", path="prior_art_defects", issue="技术问题缺少对应的现有技术缺陷来源",
                risk="问题、方案和效果之间的因果链条不清楚。", suggestion="客观描述最接近现有技术在具体场景下的缺陷。", confirm=True))
        if d.beneficial_effects and not (d.detailed_steps or d.overall_solution):
            findings.append(self._finding(dimension="技术逻辑闭环", severity=Severity.major, code="EFFECT_NO_FEATURE",
                section="有益效果", path="beneficial_effects", issue="有益效果未与技术特征建立对应关系",
                risk="效果性表述可能缺乏方案支撑。", suggestion="逐项说明由何种技术特征、通过何种机理产生该效果。"))
        return findings

    def _enablement(self, d: TechnicalDisclosure, evidence: EvidenceIndex) -> list[ReviewFinding]:
        findings = []
        if len(d.embodiments) < int(self.policy.get("minimum_embodiments", 1)):
            findings.append(self._finding(dimension="充分公开", severity=Severity.critical, code="NO_EMBODIMENT",
                section="具体实施方式", path="embodiments", issue="缺少可实施的具体实施例",
                risk="所属技术领域技术人员可能无法据此实现发明。", suggestion="基于原始论文补充流程、参数、数据处理和输出的完整实例。",
                legal=self.legal.get("clear_complete", ""), confirm=True))
        elif sum(len(x) for x in d.embodiments) < 120:
            findings.append(self._finding(dimension="充分公开", severity=Severity.major, code="EMBODIMENT_THIN",
                section="具体实施方式", path="embodiments", issue="实施方式细节偏少",
                risk="关键步骤、条件或参数可能未充分公开。", suggestion="结合论文证据补充输入条件、处理步骤、参数定义和结果验证；无证据内容标为待发明人确认。",
                legal=self.legal.get("clear_complete", ""), evidence_ids=evidence.ids_for(" ".join(d.embodiments)), confirm=True))
        if not d.alternatives:
            findings.append(self._finding(dimension="保护范围支撑", severity=Severity.note, code="NO_ALTERNATIVES",
                section="替代实施方式", path="alternatives", issue="未整理可替换技术手段或参数范围",
                risk="交底材料对权利要求层级和合理概括的支撑有限。", suggestion="由发明人确认等效结构、可选步骤及参数上下限。",
                legal=self.legal.get("claims_support", ""), confirm=True))
        return findings

    def _drafting_style(self, d: TechnicalDisclosure) -> list[ReviewFinding]:
        findings = []
        for field, value in d.model_dump().items():
            text = " \n".join(value) if isinstance(value, list) else str(value)
            for term in sorted(self.policy.get("forbidden_paper_voice", []), key=len, reverse=True):
                if term.lower() in text.lower():
                    findings.append(self._finding(dimension="专利文体", severity=Severity.minor, code=f"PAPER_VOICE_{field.upper()}",
                        section=field, path=field, issue=f"存在论文式表述“{term}”", risk="交底书文体不规范且主体指代不清。",
                        suggestion="改为“本发明”“本实施方式”或直接陈述技术事实。", original=term, auto=True))
                    break
            for term in self.policy.get("absolute_terms", []):
                if term in text:
                    findings.append(self._finding(dimension="专利文体", severity=Severity.major, code=f"ABSOLUTE_{field.upper()}",
                        section=field, path=field, issue=f"存在缺乏限定的绝对化表述“{term}”", risk="技术效果可能无法由证据支持。",
                        suggestion="改为与实验条件和技术特征相对应的客观效果表述。", original=term, confirm=True))
                    break
        return findings

    def _consistency(self, d: TechnicalDisclosure) -> list[ReviewFinding]:
        findings = []
        for item in d.terminology:
            if "/" in item or "又称" in item or "也称" in item:
                findings.append(self._finding(dimension="一致性", severity=Severity.minor, code=f"TERM_ALIAS_{len(findings)+1}",
                    section="术语表", path="terminology", issue=f"术语可能存在多个名称：{item}",
                    risk="同一技术特征名称不统一会造成保护范围解释风险。", suggestion="选择一个规范名称并在首次出现时定义简称。",
                    legal=self.legal.get("terminology", ""), original=item, confirm=True))
        return findings

    def _drawings(self, d: TechnicalDisclosure) -> list[ReviewFinding]:
        text = " \n".join(d.drawing_descriptions + d.embodiments + d.detailed_steps)
        cited = bool(re.search(r"图\s*[1-9一二三四五六七八九]", text))
        if cited and not d.drawing_descriptions:
            return [self._finding(dimension="附图一致性", severity=Severity.major, code="DRAWING_DESCRIPTION_MISSING",
                section="附图说明", path="drawing_descriptions", issue="正文引用附图但缺少附图说明",
                risk="图文关系不清，附图标记无法核对。", suggestion="逐图说明图名，并统一正文、附图和标记表中的标号。",
                legal=self.legal.get("drawings", ""), confirm=True)]
        return []

    def _evidence_coverage(self, d: TechnicalDisclosure, evidence: EvidenceIndex) -> list[ReviewFinding]:
        findings = []
        checks = [
            ("overall_solution", d.overall_solution, "技术方案"),
            ("beneficial_effects", " ".join(d.beneficial_effects), "有益效果"),
            ("embodiments", " ".join(d.embodiments), "具体实施方式"),
        ]
        for field, text, section in checks:
            matched_ids = evidence.ids_for_field(field, text)
            if text and not matched_ids:
                findings.append(self._finding(dimension="证据可追溯性", severity=Severity.major, code=f"NO_EVIDENCE_{field.upper()}",
                    section=section, path=field, issue=f"{section}未匹配到论文或Generator证据片段",
                    risk="内容可能属于无依据新增，存在超出原始公开的风险。", suggestion="绑定原文证据；无法绑定的内容不得自动写入最终稿，并列为发明人确认项。", confirm=True))
        return findings

    def _known_disclosure_gaps(self, review_input: ReviewInput) -> list[ReviewFinding]:
        unsupported = review_input.generator_metadata.get("unsupported_items", [])
        confirmation = review_input.disclosure.inventor_confirmation_items
        gaps = list(dict.fromkeys([*unsupported, *confirmation]))
        if not gaps:
            return []
        preview = "；".join(gaps[:4])
        if len(gaps) > 4:
            preview += f"；另有{len(gaps) - 4}项"
        return [self._finding(dimension="充分公开", severity=Severity.major, code="KNOWN_TECHNICAL_GAPS",
            section="实现边界与发明人确认", path="inventor_confirmation_items",
            issue=f"Generator已识别出{len(gaps)}项原始材料未充分披露的技术细节",
            risk="若这些细节属于实现发明不可缺少的条件，当前材料可能无法满足充分公开或权利要求支持要求。",
            suggestion=f"逐项向发明人确认并补充证据；当前重点包括：{preview}",
            legal=self.legal.get("clear_complete", ""), confirm=True)]

    def _eligible_subject_matter(self, d: TechnicalDisclosure) -> list[ReviewFinding]:
        solution = " ".join([d.overall_solution, *d.detailed_steps, *d.key_innovations])
        business_terms = ("商业规则", "商业模式", "营销", "计费规则", "管理规则", "游戏规则")
        technical_terms = ("设备", "系统", "处理器", "存储器", "网络", "传感器", "数据处理", "模型", "算法")
        if any(term in solution for term in business_terms) and not any(term in solution for term in technical_terms):
            return [self._finding(dimension="可专利客体", severity=Severity.major, code="RULE_ONLY_SUBJECT",
                section="技术方案", path="overall_solution", issue="方案主要表现为规则或商业目的，未识别出配套技术手段",
                risk="可能落入智力活动规则和方法，而非利用技术手段解决技术问题并获得技术效果的方案。",
                suggestion="核实并写明计算机、网络或其他技术资源如何受具体规则约束并产生技术效果。", confirm=True)]
        return []

    def _ai_disclosure(self, d: TechnicalDisclosure) -> list[ReviewFinding]:
        all_text = " ".join(str(value) if not isinstance(value, list) else " ".join(value)
                            for value in d.model_dump().values())
        ai_terms = ("人工智能", "神经网络", "深度学习", "机器学习", "大模型", "模型训练", "推理模型", "算法")
        if not any(term in all_text for term in ai_terms):
            return []
        findings = []
        details = " ".join(d.detailed_steps + d.system_implementation + d.data_and_interfaces + d.embodiments)
        if not any(term in details for term in ("输入", "样本", "训练数据", "特征", "数据集")):
            findings.append(self._finding(dimension="AI算法专项", severity=Severity.major, code="AI_INPUT_UNCLEAR",
                section="技术方案", path="data_and_interfaces", issue="未清楚限定模型或算法的输入数据及其技术含义",
                risk="输入数据与技术问题之间的关联不清，难以判断技术方案和实施条件。",
                suggestion="基于原始材料说明输入数据类型、来源、预处理和各字段/特征含义。", confirm=True))
        if not any(term in details for term in ("输出", "结果", "预测", "生成", "控制信号")):
            findings.append(self._finding(dimension="AI算法专项", severity=Severity.major, code="AI_OUTPUT_UNCLEAR",
                section="技术方案", path="data_and_interfaces", issue="未清楚限定模型或算法输出及其后续技术用途",
                risk="输入—模型—输出关系不完整，方案可能无法实施。",
                suggestion="说明输出数据格式、生成过程及其在具体技术场景中的使用方式。", confirm=True))
        if not d.system_implementation:
            findings.append(self._finding(dimension="AI算法专项", severity=Severity.major, code="AI_MODEL_DISCLOSURE_THIN",
                section="具体实施方式", path="system_implementation", issue="缺少模型结构、训练/推理过程或软硬件部署说明",
                risk="若上述内容是实现发明不可缺少的条件，可能构成公开不充分。",
                suggestion="结合论文证据补充模型组成、层级或模块连接、训练步骤、损失函数/约束及推理部署条件。", confirm=True))
        effects = " ".join(d.beneficial_effects + d.experimental_evidence)
        if effects and not any(term in effects for term in ("准确", "时延", "内存", "带宽", "计算", "鲁棒", "收敛", "吞吐", "能耗", "多样")):
            findings.append(self._finding(dimension="AI算法专项", severity=Severity.minor, code="AI_EFFECT_CAUSALITY",
                section="有益效果", path="beneficial_effects", issue="算法特征与可验证技术效果之间的因果关系不明确",
                risk="仅描述业务效果或主观效果时，难以体现方案的技术贡献。",
                suggestion="说明具体算法特征如何改善计算机内部性能或特定应用领域的技术指标。", confirm=True))
        return findings

    def _claim_support(self, d: TechnicalDisclosure) -> list[ReviewFinding]:
        findings = []
        if not d.key_innovations:
            findings.append(self._finding(dimension="保护范围支撑", severity=Severity.major, code="NO_ESSENTIAL_FEATURES",
                section="关键创新点", path="key_innovations", issue="未提炼相对于技术问题的关键技术特征",
                risk="难以区分必要技术特征和可选特征，也难以形成有层级的权利要求。",
                suggestion="从技术问题出发，逐项确认不可缺少的技术特征及其相互关系。",
                legal=self.legal.get("claims_support", ""), confirm=True))
        if len(d.technical_problem) > 1 and len(d.key_innovations) > 1:
            problem_tokens = set(EvidenceIndex._tokens(" ".join(d.technical_problem)))
            feature_tokens = set(EvidenceIndex._tokens(" ".join(d.key_innovations)))
            if problem_tokens and len(problem_tokens & feature_tokens) / len(problem_tokens) < 0.05:
                findings.append(self._finding(dimension="单一性", severity=Severity.note, code="UNITY_MANUAL_REVIEW",
                    section="技术方案", path="key_innovations", issue="多个技术问题与多个创新点之间缺少可机械识别的共同技术联系",
                    risk="可能需要确认是否属于一个总的发明构思，或是否应拆分申请。",
                    suggestion="人工确认各创新点是否具有相同或相应的特定技术特征，并共同形成对现有技术的贡献。",
                    legal=self.legal.get("unity", ""), confirm=True))
        return findings

    def _ambiguous_language(self, d: TechnicalDisclosure) -> list[ReviewFinding]:
        findings = []
        for field, value in d.model_dump().items():
            text = " \n".join(value) if isinstance(value, list) else str(value)
            matched = [term for term in self.policy.get("uncertain_terms", []) if term in text]
            if matched:
                findings.append(self._finding(dimension="专利文体", severity=Severity.minor,
                    code=f"AMBIGUOUS_{field.upper()}", section=field, path=field,
                    issue=f"存在可能导致边界不清的相对或不确定用语：{'、'.join(matched[:4])}",
                    risk="若无测量方法、参照对象或范围限定，技术特征可能不清楚。",
                    suggestion="在原始材料支持范围内补充参照对象、计算方式、阈值或数值范围。",
                    legal=self.legal.get("terminology", ""), original="、".join(matched), confirm=True))
        return findings
