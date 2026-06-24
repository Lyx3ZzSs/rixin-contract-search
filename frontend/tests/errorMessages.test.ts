import { describe, expect, it } from 'vitest';
import { failureMessage } from '../src/lib/errorMessages';

describe('failureMessage', () => {
  it('maps LLM configuration failures to actionable setup guidance', () => {
    const message = failureMessage('agent_llm_not_configured', 'backend fallback');

    expect(message).toContain('LLM 配置不可用');
    expect(message).toContain('AGENT_LLM_API_KEY');
    expect(message).toContain('AGENT_LLM_BASE_URL');
    expect(message).toContain('AGENT_LLM_MODEL');
  });

  it('maps qmd availability failures to MCP startup guidance', () => {
    const message = failureMessage('qmd_unavailable');

    expect(message).toContain('qmd MCP 不可访问');
    expect(message).toContain('qmd mcp --http --daemon');
    expect(message).toContain('QMD_MCP_URL');
  });

  it.each([
    ['qmd_deep_read_unavailable', 'MinerU 文档内核验工具不可用'],
    ['evidence_verification_failed', '候选合同已召回，但文档内证据核验失败'],
    ['condition_verdict_invalid', '条件级判断结果格式不合法'],
    ['eval_dataset_invalid', '评测集格式不合法'],
    ['eval_run_failed', 'Agent 评测运行失败']
  ])('maps %s to actionable guidance', (code, fragment) => {
    expect(failureMessage(code)).toContain(fragment);
  });

  it('maps missing qmd collections to collection status guidance', () => {
    const message = failureMessage('qmd_collection_missing');

    expect(message).toContain('qmd 集合不存在或无文档');
    expect(message).toContain('QMD_COLLECTIONS');
    expect(message).toContain('qmd status');
  });

  it('maps unexpected worker failures to worker diagnostics', () => {
    const message = failureMessage('worker_unexpected_error');

    expect(message).toContain('worker 执行异常');
    expect(message).toContain('worker logs');
    expect(message).toContain('SimpleWorker');
    expect(message).toContain('macOS');
  });

  it('maps enqueue failures to Redis and RQ guidance', () => {
    const message = failureMessage('enqueue_failed');

    expect(message).toContain('Redis');
    expect(message).toContain('RQ');
  });

  it('uses fallback for unknown codes', () => {
    expect(failureMessage('unknown_error', '后端返回的错误')).toBe('后端返回的错误');
  });

  it('uses a generic message when code and fallback are absent', () => {
    expect(failureMessage(null, null)).toBe('任务执行失败，请查看后端日志获取更多信息。');
  });
});
