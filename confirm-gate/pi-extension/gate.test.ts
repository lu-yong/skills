import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, existsSync, mkdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { homedir, tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

import { decide, dialogFor, issueTicket, loadAction, stateDir, type GateUI, type PendingAction } from './gate.ts';

const GATE_PY = join(dirname(fileURLToPath(import.meta.url)), '..', 'scripts', 'gate.py');

function tempState(): string {
  return mkdtempSync(join(tmpdir(), 'confirm-gate-ts-'));
}

function writeAction(dir: string, overrides: Partial<PendingAction> = {}): PendingAction {
  const action: PendingAction = {
    version: 1,
    created_at: Date.now() / 1000,
    id: '0123456789ab',
    kind: 'demo-write',
    digest: 'd'.repeat(64),
    question: '是否执行？',
    summary: '摘要第一行\n摘要第二行',
    approve_label: '确认执行',
    decline_label: '取消，不执行',
    ...overrides,
  };
  mkdirSync(join(dir, 'actions'), { recursive: true });
  writeFileSync(join(dir, 'actions', `${action.id}.json`), JSON.stringify(action));
  return action;
}

/** A UI that answers with `answer` and records what it was asked. */
function fakeUI(answer: string | undefined, hasUI = true): GateUI & { asked: Array<{ title: string; options: string[] }> } {
  const asked: Array<{ title: string; options: string[] }> = [];
  return {
    hasUI,
    asked,
    select: async (title, options) => {
      asked.push({ title, options });
      return answer;
    },
  };
}

/** Run a snippet against ../scripts/gate.py with `gate` bound to the module. */
function python(dir: string, body: string): { status: number | null; stdout: string; stderr: string } {
  const script = [
    'import importlib.util, json, sys',
    `spec = importlib.util.spec_from_file_location("gate", ${JSON.stringify(GATE_PY)})`,
    'gate = importlib.util.module_from_spec(spec)',
    'spec.loader.exec_module(gate)',
    body,
  ].join('\n');
  const result = spawnSync('python3', ['-c', script], {
    encoding: 'utf8',
    env: { ...process.env, CONFIRM_GATE_STATE_DIR: dir },
  });
  return { status: result.status, stdout: result.stdout, stderr: result.stderr };
}

test('stateDir follows the override, then XDG_STATE_HOME, then ~/.local/state', () => {
  assert.equal(stateDir({ CONFIRM_GATE_STATE_DIR: '/x/gate', XDG_STATE_HOME: '/x/state' }), '/x/gate');
  assert.equal(stateDir({ XDG_STATE_HOME: '/x/state' }), '/x/state/confirm-gate');
  assert.equal(stateDir({}), join(homedir(), '.local', 'state', 'confirm-gate'));
  assert.equal(stateDir({ XDG_STATE_HOME: '' }), join(homedir(), '.local', 'state', 'confirm-gate'));
});

test('stateDir matches state_dir() in gate.py for the same environment', () => {
  for (const env of [{ XDG_STATE_HOME: '/x/state' }, {}] as Array<Record<string, string>>) {
    const result = spawnSync(
      'python3',
      [
        '-c',
        [
          'import importlib.util',
          `spec = importlib.util.spec_from_file_location("gate", ${JSON.stringify(GATE_PY)})`,
          'gate = importlib.util.module_from_spec(spec)',
          'spec.loader.exec_module(gate)',
          'print(gate.state_dir())',
        ].join('\n'),
      ],
      { encoding: 'utf8', env: { PATH: process.env.PATH, HOME: process.env.HOME, ...env } },
    );
    assert.equal(result.status, 0, result.stderr);
    assert.equal(result.stdout.trim(), stateDir({ HOME: process.env.HOME, ...env }));
  }
});

test('loadAction accepts a well-formed action and nothing else', () => {
  const dir = tempState();
  try {
    const action = writeAction(dir);
    assert.deepEqual(loadAction(dir, action.id), action);

    assert.equal(loadAction(dir, 'ffffffffffff'), undefined, 'no such file');
    assert.equal(loadAction(dir, '../actions/0123456789ab'), undefined, 'path traversal');
    assert.equal(loadAction(dir, '0123456789AB'), undefined, 'uppercase id');
    assert.equal(loadAction(dir, undefined as never), undefined, 'non-string id');

    writeAction(dir, { id: 'aaaaaaaaaaaa', summary: '' });
    assert.equal(loadAction(dir, 'aaaaaaaaaaaa'), undefined, 'empty summary');

    writeAction(dir, { id: 'bbbbbbbbbbbb', approve_label: '同', decline_label: '同' });
    assert.equal(loadAction(dir, 'bbbbbbbbbbbb'), undefined, 'indistinguishable options');

    writeFileSync(join(dir, 'actions', 'cccccccccccc.json'), JSON.stringify({ ...action, id: '0123456789ab' }));
    assert.equal(loadAction(dir, 'cccccccccccc'), undefined, 'id does not match file name');

    writeFileSync(join(dir, 'actions', 'dddddddddddd.json'), 'not json');
    assert.equal(loadAction(dir, 'dddddddddddd'), undefined, 'unparsable');

    writeAction(dir, { id: 'eeeeeeeeeeee', created_at: Date.now() / 1000 - 86401 });
    assert.equal(loadAction(dir, 'eeeeeeeeeeee'), undefined, 'expired action');
    writeAction(dir, { id: 'abababababab', created_at: Infinity });
    assert.equal(loadAction(dir, 'abababababab'), undefined, 'non-finite timestamp');
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('the dialog shows the recorded summary and question, with decline preselected', () => {
  const action = writeAction(tempState());
  assert.deepEqual(dialogFor(action), {
    title: '摘要第一行\n摘要第二行\n\n是否执行？',
    options: ['取消，不执行', '确认执行'],
  });
});

test('approval issues a private ticket bound to the action digest', async () => {
  const dir = tempState();
  try {
    const action = writeAction(dir);
    const ui = fakeUI(action.approve_label);
    const outcome = await decide(dir, action.id, ui);

    assert.equal(outcome.decision, 'approved');
    assert.match(outcome.text, /^approved: /);
    assert.deepEqual(ui.asked, [dialogFor(action)]);
    const path = join(dir, 'tickets', `${action.id}.json`);
    const ticket = JSON.parse(readFileSync(path, 'utf8'));
    assert.equal(ticket.action_id, action.id);
    assert.equal(ticket.digest, action.digest);
    assert.ok(Math.abs(ticket.issued_at - Date.now() / 1000) < 5);
    assert.equal(statSync(path).mode & 0o777, 0o600);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('anything other than the approve option issues no ticket', async () => {
  const cases: Array<[string | undefined, string]> = [
    ['取消，不执行', 'declined'],
    [undefined, 'cancelled'],
    ['Yes', 'cancelled'],
    ['确认执行 ', 'cancelled'],
  ];
  for (const [answer, expected] of cases) {
    const dir = tempState();
    try {
      const action = writeAction(dir);
      issueTicket(dir, action);
      const outcome = await decide(dir, action.id, fakeUI(answer));
      assert.equal(outcome.decision, expected, `answer ${JSON.stringify(answer)}`);
      assert.ok(outcome.text.startsWith(`${expected}: `));
      assert.equal(existsSync(join(dir, 'tickets', `${action.id}.json`)), false);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  }
});

test('a session without UI is never asked and gets no ticket', async () => {
  const dir = tempState();
  try {
    const action = writeAction(dir);
    const ticket = issueTicket(dir, action);
    const ui = fakeUI(action.approve_label, false);
    const outcome = await decide(dir, action.id, ui);
    assert.equal(outcome.decision, 'unavailable');
    assert.deepEqual(ui.asked, []);
    assert.equal(existsSync(ticket), false);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('a UI error or abort clears existing approval and cannot issue another', async () => {
  const dir = tempState();
  try {
    const action = writeAction(dir);
    const ticket = issueTicket(dir, action);
    const brokenUI: GateUI = { hasUI: true, select: async () => { throw new Error('UI disconnected'); } };
    assert.equal((await decide(dir, action.id, brokenUI)).decision, 'unavailable');
    assert.equal(existsSync(ticket), false);

    const retry = writeAction(dir, { id: "abcdef012345" });
    const retryTicket = issueTicket(dir, retry);
    const controller = new AbortController();
    const lateUI: GateUI = {
      hasUI: true,
      select: async () => {
        controller.abort();
        return retry.approve_label;
      },
    };
    assert.equal((await decide(dir, retry.id, lateUI, controller.signal)).decision, 'cancelled');
    assert.equal(existsSync(retryTicket), false);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('a concurrent decline invalidates a ticket or a still-open approval', async () => {
  for (const approveFirst of [true, false]) {
    const dir = tempState();
    try {
      const action = writeAction(dir);
      let approve!: (value: string) => void;
      let decline!: (value: string) => void;
      const approval = decide(dir, action.id, { hasUI: true, select: () => new Promise((resolve) => { approve = resolve; }) });
      const refusal = decide(dir, action.id, { hasUI: true, select: () => new Promise((resolve) => { decline = resolve; }) });
      if (approveFirst) {
        approve(action.approve_label);
        assert.equal((await approval).decision, 'approved');
      }
      decline(action.decline_label);
      assert.equal((await refusal).decision, 'declined');
      if (!approveFirst) {
        approve(action.approve_label);
        assert.equal((await approval).decision, 'unknown_action');
      }
      assert.equal(loadAction(dir, action.id), undefined);
      assert.equal(existsSync(join(dir, 'tickets', `${action.id}.json`)), false);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  }
});

test('approval is refused if the action changes while the dialog is open', async () => {
  const dir = tempState();
  try {
    const action = writeAction(dir);
    const ui: GateUI = {
      hasUI: true,
      select: async () => {
        writeAction(dir, { summary: '修改后的摘要' });
        return action.approve_label;
      },
    };
    assert.equal((await decide(dir, action.id, ui)).decision, 'unknown_action');
    assert.equal(existsSync(join(dir, 'tickets', `${action.id}.json`)), false);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('an unknown action is reported without asking the user', async () => {
  const dir = tempState();
  try {
    const ui = fakeUI('确认执行');
    const outcome = await decide(dir, '0123456789ab', ui);
    assert.equal(outcome.decision, 'unknown_action');
    assert.deepEqual(ui.asked, []);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('issueTicket replaces an earlier ticket for the same action', () => {
  const dir = tempState();
  try {
    const action = writeAction(dir);
    issueTicket(dir, action, 1000);
    const path = issueTicket(dir, action, 2000);
    assert.equal(JSON.parse(readFileSync(path, 'utf8')).issued_at, 2);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('gate.py accepts a ticket issued here, once, for an action it registered', async () => {
  const dir = tempState();
  try {
    const created = python(
      dir,
      'action = gate.create_action("demo-write", {"n": 1, "文本": "值"}, question="是否执行？", summary="摘要", approve_label="确认执行")\nprint(action["id"])',
    );
    assert.equal(created.status, 0, created.stderr);
    const id = created.stdout.trim();

    const authorize = `
try:
    gate.authorize(${JSON.stringify(id)}, "demo-write", {"n": 1, "文本": "值"})
    print("authorized")
except gate.GateError as error:
    print(error.code)
`;
    assert.equal(python(dir, authorize).stdout.trim(), 'no_ticket', 'refused before the user confirms');


    assert.equal((await decide(dir, id, fakeUI('确认执行'))).decision, 'approved');
    assert.equal(python(dir, authorize).stdout.trim(), 'authorized', 'accepted after the user confirms');
    assert.equal(python(dir, authorize).stdout.trim(), 'no_ticket', 'a ticket authorizes once');
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('gate.py refuses a ticket issued here once the live state has changed', async () => {
  const dir = tempState();
  try {
    const created = python(
      dir,
      'action = gate.create_action("demo-write", {"n": 1}, question="是否执行？", summary="摘要", approve_label="确认执行")\nprint(action["id"])',
    );
    const id = created.stdout.trim();
    assert.equal((await decide(dir, id, fakeUI('确认执行'))).decision, 'approved');
    const changed = python(
      dir,
      `
try:
    gate.authorize(${JSON.stringify(id)}, "demo-write", {"n": 2})
    print("authorized")
except gate.GateError as error:
    print(error.code)
`,
    );
    assert.equal(changed.stdout.trim(), 'changed');
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
