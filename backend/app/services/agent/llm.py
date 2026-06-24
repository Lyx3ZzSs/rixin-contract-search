import json
from typing import Any, Protocol

from pydantic import ValidationError

from app.config import settings
from app.schemas import ScreeningPlanPayload


PLAN_OUTPUT_SCHEMA = {
    "target": "qmd_document",
    "conditions": [
        {
            "id": "short_english_id",
            "description": "条件中文描述",
            "operator": "semantic_match",
            "value": "条件值",
            "qmd_queries": ["用于qmd检索的中文查询"],
            "evidence_required": 1,
            "structured": False,
        }
    ],
    "decision_policy": "phase1_keyword_candidate_uncertain_on_structured_comparison",
}

PLAN_SYSTEM_PROMPT = (
    "你是合同筛选Agent的规划器。只输出一个JSON对象，不要输出解释、Markdown或代码块。"
    "输出对象必须只有业务计划字段：target、conditions、decision_policy。"
    "不要返回task、raw_query、schema、example、说明文字。"
    "conditions必须是非空数组，每个条件都必须包含id、description、operator、value、qmd_queries、evidence_required、structured。"
)

PLAN_REPAIR_SYSTEM_PROMPT = (
    "你是合同筛选Agent的JSON修复器。只输出修复后的业务计划JSON对象。"
    "不要复述输入，不要返回task/raw_query/schema/invalid_response。"
)


class AgentLlm(Protocol):
    def plan(self, raw_query: str) -> ScreeningPlanPayload:
        raise NotImplementedError

    def refine_queries(self, raw_query: str, plan: ScreeningPlanPayload, missing_condition_ids: list[str]) -> dict[str, list[str]]:
        raise NotImplementedError

    def classify_document(self, plan: ScreeningPlanPayload, document: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class AgentLlmConfigurationError(RuntimeError):
    def __init__(self, message: str):
        super().__init__(message)
        self.code = "agent_llm_not_configured"


class AgentLlmPlanError(ValueError):
    pass


class OpenAICompatibleAgentLlm:
    def __init__(self):
        from langchain_openai import ChatOpenAI

        self.model = ChatOpenAI(
            model=settings.AGENT_LLM_MODEL,
            api_key=settings.AGENT_LLM_API_KEY,
            base_url=settings.AGENT_LLM_BASE_URL,
            temperature=settings.AGENT_LLM_TEMPERATURE,
        )

    def plan(self, raw_query: str) -> ScreeningPlanPayload:
        payload = {
            "task": "将用户筛选要求拆成可检索的合同筛选条件。",
            "raw_query": raw_query,
            "required_output_schema": PLAN_OUTPUT_SCHEMA,
            "rules": [
                "只返回required_output_schema形状的JSON对象。",
                "conditions必须根据raw_query生成，不能使用示例占位值。",
                "每个qmd_queries条目应是可直接用于合同库检索的中文查询。",
            ],
        }
        data = self._json(PLAN_SYSTEM_PROMPT, payload)
        try:
            return _validate_plan_response(data)
        except AgentLlmPlanError as first_error:
            repaired = self._json(
                PLAN_REPAIR_SYSTEM_PROMPT,
                {
                    "task": "修复上一轮合同筛选计划JSON。",
                    "raw_query": raw_query,
                    "required_output_schema": PLAN_OUTPUT_SCHEMA,
                    "invalid_response": data,
                    "validation_error": str(first_error),
                },
            )
            try:
                return _validate_plan_response(repaired)
            except AgentLlmPlanError as second_error:
                raise AgentLlmPlanError(f"{second_error}; first_attempt_error={first_error}") from second_error

    def refine_queries(self, raw_query: str, plan: ScreeningPlanPayload, missing_condition_ids: list[str]) -> dict[str, list[str]]:
        data = self._json(
            "你是合同检索查询改写器。只输出JSON，不要输出解释。",
            {
                "task": "为证据不足的条件补充更具体的qmd检索查询。",
                "raw_query": raw_query,
                "plan": plan.model_dump(),
                "missing_condition_ids": missing_condition_ids,
                "schema": {"condition_id": ["补充查询1", "补充查询2"]},
            },
        )
        return {str(key): [str(item) for item in value if str(item).strip()] for key, value in data.items() if isinstance(value, list)}

    def classify_document(self, plan: ScreeningPlanPayload, document: dict[str, Any]) -> dict[str, Any]:
        data = self._json(
            "你是合同筛选分类器。只能基于给定证据判断；证据不足必须输出uncertain。只输出JSON。",
            {
                "task": "判断该文档是否满足筛选条件。",
                "plan": plan.model_dump(),
                "document": document,
                "schema": {
                    "decision": "included|excluded|uncertain",
                    "reason": "128字以内原因码或短句",
                    "matched_conditions": ["condition_id"],
                    "missing_conditions": ["condition_id"],
                    "evidence": [{"page": 1, "text": "证据原文", "source": "qmd", "score": 0.9, "condition_id": "condition_id", "artifact_ref": "qmd://..."}],
                    "confidence": 0.0,
                },
            },
        )
        return data

    def _json(self, system: str, payload: dict[str, Any]) -> dict[str, Any]:
        from langchain_core.messages import HumanMessage, SystemMessage

        response = self.model.invoke([SystemMessage(content=system), HumanMessage(content=json.dumps(payload, ensure_ascii=False))])
        content = _extract_json_text(str(response.content))
        return json.loads(content)


def _validate_plan_response(data: Any) -> ScreeningPlanPayload:
    candidate = _extract_plan_candidate(data)
    try:
        return ScreeningPlanPayload.model_validate(candidate)
    except ValidationError as exc:
        raise AgentLlmPlanError(f"invalid screening plan JSON: {exc}") from exc


def _extract_plan_candidate(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise AgentLlmPlanError(f"expected JSON object with conditions, got {type(data).__name__}")

    if "conditions" in data:
        return _normalize_plan_shape(data)

    for key in ("plan", "screening_plan", "result", "output"):
        value = data.get(key)
        if isinstance(value, dict) and "conditions" in value:
            return _normalize_plan_shape(value)

    if "condition" in data and isinstance(data["condition"], dict):
        candidate = dict(data)
        candidate["conditions"] = [candidate.pop("condition")]
        return _normalize_plan_shape(candidate)

    if "filters" in data and isinstance(data["filters"], list):
        candidate = dict(data)
        candidate["conditions"] = candidate.pop("filters")
        return _normalize_plan_shape(candidate)

    prompt_keys = {"task", "raw_query", "schema", "required_output_schema"}
    if prompt_keys & data.keys():
        raise AgentLlmPlanError("conditions field is required; model returned prompt metadata instead of the screening plan")
    raise AgentLlmPlanError("conditions field is required in screening plan JSON")


def _normalize_plan_shape(data: dict[str, Any]) -> dict[str, Any]:
    candidate = dict(data)
    conditions = candidate.get("conditions")
    if isinstance(conditions, dict):
        conditions = list(conditions.values())
    if isinstance(conditions, list):
        candidate["conditions"] = [_normalize_condition(item) for item in conditions]
    return candidate


def _normalize_condition(item: Any) -> Any:
    if not isinstance(item, dict):
        return item
    condition = dict(item)
    if "operator" not in condition:
        condition["operator"] = "semantic_match"
    if "structured" not in condition:
        condition["structured"] = False
    if "value" not in condition and isinstance(condition.get("description"), str):
        condition["value"] = condition["description"]
    if "qmd_queries" not in condition:
        for key in ("queries", "search_queries", "qmd_query", "query"):
            value = condition.get(key)
            if value:
                condition["qmd_queries"] = value
                break
    if isinstance(condition.get("qmd_queries"), str):
        condition["qmd_queries"] = [condition["qmd_queries"]]
    return condition


def _extract_json_text(content: str) -> str:
    content = content.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        content = "\n".join(lines).strip()
    if content.startswith("json"):
        content = content[4:].strip()
    if not content.startswith("{"):
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            content = content[start : end + 1]
    return content


def create_agent_llm() -> AgentLlm:
    if not settings.AGENT_LLM_API_KEY:
        raise AgentLlmConfigurationError("AGENT_LLM_API_KEY is required")
    if settings.AGENT_LLM_MODEL == "fake":
        raise AgentLlmConfigurationError("AGENT_LLM_MODEL must be a real OpenAI-compatible model name")
    return OpenAICompatibleAgentLlm()
