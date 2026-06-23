import { ApiClientError } from './api';

const genericFailureMessage = '任务执行失败，请查看后端日志获取更多信息。';

const failureMessages: Record<string, string> = {
  agent_llm_not_configured: 'LLM 配置不可用。请检查 AGENT_LLM_API_KEY、AGENT_LLM_BASE_URL 和 AGENT_LLM_MODEL 是否已在后端环境中正确配置。',
  qmd_unavailable: 'qmd MCP 不可访问。请确认已运行 qmd mcp --http --daemon，并检查 QMD_MCP_URL 是否指向可访问的 qmd MCP 服务。',
  qmd_collection_missing: 'qmd 集合不存在或无文档。请检查 QMD_COLLECTIONS 配置，并运行 qmd status 确认集合名称和文档数量。',
  worker_unexpected_error: 'worker 执行异常。请查看 worker logs；macOS 本地开发时确认 SimpleWorker 模式是否正常运行。',
  enqueue_failed: '任务入队失败。请检查 Redis/RQ 是否可用，并确认后端 worker 队列连接正常。'
};

export function failureMessage(code?: string | null, fallback?: string | null): string {
  if (code && failureMessages[code]) return failureMessages[code];
  return fallback?.trim() || genericFailureMessage;
}

export function apiErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiClientError) return failureMessage(error.code, error.message);
  if (error instanceof Error) return error.message;
  return fallback;
}
