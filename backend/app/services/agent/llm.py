import json
from typing import Any, Protocol

from app.config import settings
from app.schemas import ScreeningPlanPayload


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
        data = self._json(
            "你是合同筛选Agent的规划器。只输出JSON，不要输出解释。",
            {
                "task": "将用户筛选要求拆成可检索的合同筛选条件。",
                "raw_query": raw_query,
                "schema": {
                    "target": "qmd_document",
                    "conditions": [
                        {
                            "id": "短英文id",
                            "description": "条件中文描述",
                            "operator": "semantic_match",
                            "value": "条件值",
                            "qmd_queries": ["用于qmd检索的中文查询"],
                            "evidence_required": 1,
                            "structured": False,
                        }
                    ],
                    "decision_policy": "phase1_keyword_candidate_uncertain_on_structured_comparison",
                },
            },
        )
        return ScreeningPlanPayload.model_validate(data)

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
        content = str(response.content).strip()
        if content.startswith("```"):
            content = content.strip("`")
            if content.startswith("json"):
                content = content[4:].strip()
        return json.loads(content)


def create_agent_llm() -> AgentLlm:
    if not settings.AGENT_LLM_API_KEY:
        raise AgentLlmConfigurationError("AGENT_LLM_API_KEY is required")
    if settings.AGENT_LLM_MODEL == "fake":
        raise AgentLlmConfigurationError("AGENT_LLM_MODEL must be a real OpenAI-compatible model name")
    return OpenAICompatibleAgentLlm()
