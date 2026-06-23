import { afterEach, describe, expect, it } from 'vitest';
import { getReviewerName, setReviewerName } from '../src/lib/reviewer';

describe('reviewer storage', () => {
  afterEach(() => {
    localStorage.clear();
  });

  it('returns an empty name when no reviewer has been stored', () => {
    expect(getReviewerName()).toBe('');
  });

  it('stores trimmed non-empty reviewer names', () => {
    setReviewerName('  张三  ');

    expect(localStorage.getItem('contract-agent-reviewer-name')).toBe('张三');
    expect(getReviewerName()).toBe('张三');
  });

  it('ignores empty reviewer names after trimming', () => {
    localStorage.setItem('contract-agent-reviewer-name', '李四');

    setReviewerName('   ');

    expect(getReviewerName()).toBe('李四');
  });
});
