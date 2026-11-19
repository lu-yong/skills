/**
 * Gerrit review pushes belong to the commit-gerrit skill, whose submit script
 * pushes only with a confirmation ticket. A `git push ... refs/for/...` typed
 * straight into the bash tool would skip that check, so it is blocked here.
 *
 * The script's own push is a subprocess of the script, not a bash tool call,
 * so this never sees it. Commands the user runs themselves with `!` are not
 * tool calls either.
 */

// Recognize literal simple commands without interpreting shell expansions.
const SHELL_TOKEN = /(?:'[^']*'|"(?:[^"\\]|\\.)*"|\\[^\n]|[^\s;&|'"\\])+|[\n;&|]+/g;
const GIT_OPTIONS_WITH_VALUE = new Set(['-C', '-c', '--git-dir', '--work-tree', '--namespace', '--config-env']);

export const REVIEW_PUSH_BLOCK_REASON =
  'Blocked direct Gerrit review push (refs/for/...) in the pi bash tool. ' +
  'The commit-gerrit script requests approval through confirm_gate before pushing. ' +
  'Stop and report this; the user can invoke commit-gerrit, or run the push themselves.';

function isReviewPush(words: string[]): boolean {
  let index = 0;
  while (/^[A-Za-z_]\w*=/.test(words[index] ?? '')) index++;
  if (!/(^|\/)git$/.test(words[index] ?? '')) return false;
  index++;
  while (words[index]?.startsWith('-')) {
    const option = words[index++];
    if (GIT_OPTIONS_WITH_VALUE.has(option)) index++;
  }
  return words[index] === 'push' && words.slice(index + 1).some((word) =>
    /(^|:)refs\/for\/.+/.test(word.replace(/['"]/g, '')));
}

export function reviewPushBlockReason(command: unknown): string | undefined {
  if (typeof command !== 'string') return undefined;
  let words: string[] = [];
  for (const token of command.match(SHELL_TOKEN) ?? []) {
    if (/^[\n;&|]/.test(token)) {
      if (isReviewPush(words)) return REVIEW_PUSH_BLOCK_REASON;
      words = [];
    } else {
      words.push(token);
    }
  }
  return isReviewPush(words) ? REVIEW_PUSH_BLOCK_REASON : undefined;
}
