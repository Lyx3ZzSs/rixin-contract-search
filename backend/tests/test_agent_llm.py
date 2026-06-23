def test_runtime_agent_llm_has_no_rule_based_fallback():
    import app.services.agent.llm as llm

    assert not hasattr(llm, "RuleBasedAgentLlm")
