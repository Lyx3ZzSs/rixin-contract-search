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
