import assert from 'node:assert/strict';
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';

import confirmGate, { TOOL_NAME } from './index.ts';

type Handler = (...args: any[]) => unknown;

function load() {
  const tools = new Map<string, any>();
  const events = new Map<string, Handler>();
  const pi = {
    registerTool: (definition: { name: string }) => tools.set(definition.name, definition),
    on: (name: string, handler: Handler) => events.set(name, handler),
  };
  confirmGate(pi as never);
  return { tools, events };
}

function withState<T>(run: (dir: string) => Promise<T>): Promise<T> {
  const dir = mkdtempSync(join(tmpdir(), 'confirm-gate-index-'));
  const previous = process.env.CONFIRM_GATE_STATE_DIR;
  process.env.CONFIRM_GATE_STATE_DIR = dir;
  return run(dir).finally(() => {
    if (previous === undefined) delete process.env.CONFIRM_GATE_STATE_DIR;
    else process.env.CONFIRM_GATE_STATE_DIR = previous;
    rmSync(dir, { recursive: true, force: true });
  });
}

function writeAction(dir: string) {
  const action = {
    version: 1,
    created_at: Date.now() / 1000,
    id: '0123456789ab',
    kind: 'demo-write',
    digest: 'd'.repeat(64),
    question: '是否执行？',
    summary: '摘要',
    approve_label: '确认执行',
    decline_label: '取消，不执行',
  };
  mkdirSync(join(dir, 'actions'), { recursive: true });
  writeFileSync(join(dir, 'actions', `${action.id}.json`), JSON.stringify(action));
  return action;
}

test('the adapter registers one tool and one tool_call hook', () => {
  const { tools, events } = load();
  assert.deepEqual([...tools.keys()], [TOOL_NAME]);
  assert.deepEqual([...events.keys()], ['tool_call']);
  const tool = tools.get(TOOL_NAME);
  assert.deepEqual(tool.parameters.required, ['action_id']);
  assert.equal(tool.executionMode, 'sequential');
});

test('confirm_gate asks through ctx.ui.select and issues a ticket on approval', async () => {
  await withState(async (dir) => {
    const action = writeAction(dir);
    const asked: Array<{ title: string; options: string[] }> = [];
    const ctx = {
      hasUI: true,
      ui: {
        select: async (title: string, options: string[]) => {
          asked.push({ title, options });
          return action.approve_label;
        },
      },
    };
    const result = await load().tools.get(TOOL_NAME).execute('call-1', { action_id: action.id }, undefined, undefined, ctx);

    assert.deepEqual(asked, [{ title: '摘要\n\n是否执行？', options: ['取消，不执行', '确认执行'] }]);
    assert.equal(result.details.decision, 'approved');
    assert.match(result.content[0].text, /^approved: /);
    assert.equal(existsSync(join(dir, 'tickets', `${action.id}.json`)), true);
  });
});

test('confirm_gate without UI, or with a bad argument, issues nothing', async () => {
  await withState(async (dir) => {
    const action = writeAction(dir);
    const tool = load().tools.get(TOOL_NAME);
    const neverAsk = {
      select: async () => {
        throw new Error('must not be asked');
      },
    };

    const headless = await tool.execute('call-1', { action_id: action.id }, undefined, undefined, { hasUI: false, ui: neverAsk });
    assert.equal(headless.details.decision, 'unavailable');

    for (const params of [{}, { action_id: 42 }, { action_id: 'ffffffffffff' }]) {
      const unknown = await tool.execute('call-2', params, undefined, undefined, { hasUI: true, ui: neverAsk });
      assert.equal(unknown.details.decision, 'unknown_action');
    }
    assert.equal(existsSync(join(dir, 'tickets')), false);
  });
});

test('the tool_call hook blocks direct review pushes and nothing else', async () => {
  const hook = load().events.get('tool_call')!;

  const blocked = (await hook({ toolName: 'bash', input: { command: 'git push origin HEAD:refs/for/master' } })) as {
    block: boolean;
    reason: string;
  };
  assert.equal(blocked.block, true);
  assert.match(blocked.reason, /commit-gerrit/);

  assert.equal(await hook({ toolName: 'bash', input: { command: 'git push origin topic' } }), undefined);
  assert.equal(await hook({ toolName: 'bash', input: {} }), undefined);
  assert.equal(
    await hook({ toolName: 'write', input: { path: 'notes.md', content: 'git push origin HEAD:refs/for/master' } }),
    undefined,
  );
});
