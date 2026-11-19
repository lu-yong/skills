import assert from 'node:assert/strict';
import { test } from 'node:test';

import { REVIEW_PUSH_BLOCK_REASON, reviewPushBlockReason } from './push-guard.ts';

test('direct Gerrit review pushes are blocked', () => {
  const blocked = [
    'git push origin HEAD:refs/for/master',
    'git push --receive-pack="gerrit receive-pack" --no-follow-tags origin refs/heads/topic:refs/for/sdk-release',
    'git -C /work/repo push origin HEAD:refs/for/master%topic=fix',
    'cd /work/repo && git add -A && git commit -m x && git push origin HEAD:refs/for/master',
    'GIT_TERMINAL_PROMPT=0 git push ssh://git.nationalchip.com:29418/proj HEAD:refs/for/dev',
    'echo start\ngit push origin HEAD:refs/for/master\necho done',
  ];
  for (const command of blocked) {
    assert.equal(reviewPushBlockReason(command), REVIEW_PUSH_BLOCK_REASON, command);
  }
});

test('other commands pass through', () => {
  const allowed = [
    'git push origin topic',
    'git push origin HEAD:refs/heads/topic',
    'git status --short',
    'git log --grep="push refs/for/main"',
    'printf "%s" "git push origin HEAD:refs/for/main"',
    'git log --oneline refs/for/master',
    'grep -rn "refs/for/" docs',
    'git fetch origin; ls refs/for/',
    'python3 /skills/commit-gerrit/scripts/gerrit_submit.py execute --action 0123456789ab',
    '',
  ];
  for (const command of allowed) {
    assert.equal(reviewPushBlockReason(command), undefined, command);
  }
  for (const notAString of [undefined, null, 42, { command: 'git push origin HEAD:refs/for/x' }]) {
    assert.equal(reviewPushBlockReason(notAString), undefined);
  }
});
