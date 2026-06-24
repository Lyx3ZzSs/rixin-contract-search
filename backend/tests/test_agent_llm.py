def test_runtime_agent_llm_has_no_rule_based_fallback():
    import app.services.agent.llm as llm

    assert not hasattr(llm, "RuleBasedAgentLlm")


def test_openai_compatible_llm_plan_fills_fixed_metadata_when_model_omits_it():
    from app.services.agent.llm import OpenAICompatibleAgentLlm

    agent_llm = OpenAICompatibleAgentLlm.__new__(OpenAICompatibleAgentLlm)
    agent_llm._json = lambda _system, _payload: {
        "conditions": [
            {
                "id": "gpu_storage_purchase",
                "description": "采购了GPU服务器和存储服务器",
                "operator": "semantic_match",
                "value": "GPU服务器和存储服务器",
                "qmd_queries": ["GPU服务器 存储服务器 采购 合同"],
                "evidence_required": 1,
                "structured": False,
            }
        ]
    }

    plan = agent_llm.plan("哪份合同采购了GPU服务器和存储服务器？")

    assert plan.target == "qmd_document"
    assert plan.decision_policy == "phase1_keyword_candidate_uncertain_on_structured_comparison"
    assert plan.conditions[0].id == "gpu_storage_purchase"


def test_openai_compatible_llm_plan_accepts_plan_wrapper():
    from app.services.agent.llm import OpenAICompatibleAgentLlm

    agent_llm = OpenAICompatibleAgentLlm.__new__(OpenAICompatibleAgentLlm)
    agent_llm._json = lambda _system, _payload: {
        "plan": {
            "conditions": [
                {
                    "id": "gpu_storage_purchase",
                    "description": "采购了GPU服务器和存储服务器",
                    "operator": "semantic_match",
                    "value": "GPU服务器和存储服务器",
                    "qmd_queries": ["GPU服务器 存储服务器 采购 合同"],
                    "evidence_required": 1,
                    "structured": False,
                }
            ]
        }
    }

    plan = agent_llm.plan("哪份合同采购了GPU服务器和存储服务器？")

    assert plan.conditions[0].id == "gpu_storage_purchase"


def test_openai_compatible_llm_plan_repairs_schema_echo_response():
    from app.services.agent.llm import OpenAICompatibleAgentLlm

    responses = [
        {
            "task": "将用户筛选要求拆成可检索的合同筛选条件。",
            "raw_query": "哪份合同采购了GPU服务器和存储服务器？",
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
        {
            "conditions": [
                {
                    "id": "gpu_storage_purchase",
                    "description": "采购了GPU服务器和存储服务器",
                    "operator": "semantic_match",
                    "value": "GPU服务器和存储服务器",
                    "qmd_queries": ["GPU服务器 存储服务器 采购 合同"],
                    "evidence_required": 1,
                    "structured": False,
                }
            ]
        },
    ]
    payloads = []
    agent_llm = OpenAICompatibleAgentLlm.__new__(OpenAICompatibleAgentLlm)

    def fake_json(_system, payload):
        payloads.append(payload)
        return responses.pop(0)

    agent_llm._json = fake_json

    plan = agent_llm.plan("哪份合同采购了GPU服务器和存储服务器？")

    assert plan.conditions[0].id == "gpu_storage_purchase"
    assert len(payloads) == 2
    assert payloads[1]["task"] == "修复上一轮合同筛选计划JSON。"
    assert "invalid_response" in payloads[1]


def test_openai_compatible_llm_plan_reports_diagnostic_when_conditions_missing_after_repair():
    from app.services.agent.llm import AgentLlmPlanError, OpenAICompatibleAgentLlm

    agent_llm = OpenAICompatibleAgentLlm.__new__(OpenAICompatibleAgentLlm)
    agent_llm._json = lambda _system, _payload: {"task": "echoed prompt"}

    try:
        agent_llm.plan("哪份合同采购了GPU服务器和存储服务器？")
    except AgentLlmPlanError as exc:
        assert "conditions" in str(exc)
        assert "returned prompt metadata" in str(exc)
    else:
        raise AssertionError("expected AgentLlmPlanError")
