/**
 * Confirm gate, host side: show a pending action to the user and, when they
 * approve it, issue the ticket that the action's script requires.
 *
 * The scripts own enforcement (../scripts/gate.py): they recompute the action
 * digest from live state and consume the ticket. The extension reads the action
 * and manages tickets in the same local state directory as the scripts.
 */

import { randomUUID } from 'node:crypto';
import { mkdirSync, readFileSync, renameSync, rmSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

const ACTION_ID = /^[0-9a-f]{12}$/;
const VERSION = 1;
const ACTION_TTL_SECONDS = 24 * 3600;
const ISSUER = 'pi-confirm-gate';

export interface PendingAction {
  version: number;
  created_at: number;
  id: string;
  kind: string;
  digest: string;
  question: string;
  summary: string;
  approve_label: string;
  decline_label: string;
}

export type Decision = 'approved' | 'declined' | 'cancelled' | 'unavailable' | 'unknown_action';

export interface Outcome {
  decision: Decision;
  /** What the model reads. The script, not this text, decides whether a write runs. */
  text: string;
}

/** The slice of pi's UI the gate uses, so tests can stand in for it. */
export interface GateUI {
  hasUI: boolean;
  select(title: string, options: string[], opts?: { signal?: AbortSignal }): Promise<string | undefined>;
}

/** Must resolve to the same directory as state_dir() in ../scripts/gate.py. */
export function stateDir(env: Record<string, string | undefined> = process.env): string {
  if (env.CONFIRM_GATE_STATE_DIR) return env.CONFIRM_GATE_STATE_DIR;
  return join(env.XDG_STATE_HOME || join(homedir(), '.local', 'state'), 'confirm-gate');
}

export function loadAction(dir: string, actionId: string): PendingAction | undefined {
  if (typeof actionId !== 'string' || actionId.length !== 12 || !ACTION_ID.test(actionId)) return undefined;
  let data: unknown;
  try {
    data = JSON.parse(readFileSync(join(dir, 'actions', `${actionId}.json`), 'utf8'));
  } catch {
    return undefined;
  }
  if (typeof data !== 'object' || data === null) return undefined;
  const record = data as Record<string, unknown>;
  const fields = ['id', 'kind', 'digest', 'question', 'summary', 'approve_label', 'decline_label'];
  if (!fields.every((field) => {
    const value = record[field];
    return typeof value === 'string' && value.trim() !== '';
  })) return undefined;
  const action = record as unknown as PendingAction;
  const now = Date.now() / 1000;
  if (action.version !== VERSION || !Number.isFinite(action.created_at) ||
      action.created_at < now - ACTION_TTL_SECONDS || action.created_at > now + 5) return undefined;
  if (action.id !== actionId || action.approve_label === action.decline_label) return undefined;
  return action;
}

/** Write the single-use ticket for exactly the content the user was shown. */
export function issueTicket(dir: string, action: PendingAction, nowMs: number = Date.now()): string {
  const tickets = join(dir, 'tickets');
  mkdirSync(tickets, { recursive: true, mode: 0o700 });
  const path = join(tickets, `${action.id}.json`);
  const temporary = `${path}.${randomUUID()}.tmp`;
  const ticket = {
    version: VERSION,
    action_id: action.id,
    digest: action.digest,
    issued_at: nowMs / 1000,
    issuer: ISSUER,
  };
  try {
    writeFileSync(temporary, `${JSON.stringify(ticket, null, 2)}\n`, { flag: 'wx', mode: 0o600 });
    renameSync(temporary, path);
  } finally {
    rmSync(temporary, { force: true });
  }
  return path;
}

/**
 * The dialog. The decline option comes first: pi preselects the first option,
 * so a stray Enter declines.
 */
export function dialogFor(action: PendingAction): { title: string; options: string[] } {
  return {
    title: `${action.summary}\n\n${action.question}`,
    options: [action.decline_label, action.approve_label],
  };
}

export async function decide(dir: string, actionId: string, ui: GateUI, signal?: AbortSignal): Promise<Outcome> {
  const unknown: Outcome = {
    decision: 'unknown_action',
    text: 'unknown_action: the pending action is missing, expired, or changed. Re-run the plan step and pass the new action_id.',
  };
  if (typeof actionId !== 'string' || actionId.length !== 12 || !ACTION_ID.test(actionId)) return unknown;
  const unavailable: Outcome = {
    decision: 'unavailable',
    text: 'unavailable: the confirmation UI or ticket storage is unavailable. Stop and report.',
  };
  const cancelled: Outcome = {
    decision: 'cancelled',
    text: 'cancelled: confirmation was interrupted. Stop and report.',
  };
  const ticketPath = join(dir, 'tickets', `${actionId}.json`);
  function abandon(outcome: Outcome): Outcome {
    try {
      // Removing the plan also invalidates approval from another open dialog.
      rmSync(join(dir, 'actions', `${actionId}.json`), { force: true });
      rmSync(ticketPath, { force: true });
      return outcome;
    } catch {
      return unavailable;
    }
  }

  try {
    // Starting a new confirmation revokes any earlier approval of this plan.
    rmSync(ticketPath, { force: true });
    const action = loadAction(dir, actionId);
    if (!action) return unknown;
    if (!ui.hasUI) return abandon(unavailable);
    if (signal?.aborted) return abandon(cancelled);

    const { title, options } = dialogFor(action);
    const choice = await ui.select(title, options, { signal });
    if (signal?.aborted) return abandon(cancelled);
    if (choice === action.decline_label) {
      return abandon({
        decision: 'declined',
        text: `declined: the user chose "${action.decline_label}" for action ${action.id}. Stop and report.`,
      });
    }
    if (choice !== action.approve_label) return abandon(cancelled);

    if (JSON.stringify(loadAction(dir, actionId)) !== JSON.stringify(action)) return unknown;
    issueTicket(dir, action);
    if (JSON.stringify(loadAction(dir, actionId)) !== JSON.stringify(action)) return abandon(unknown);
    return {
      decision: 'approved',
      text: `approved: the user chose "${action.approve_label}" for action ${action.id}. Run the script's execute step for this action now.`,
    };
  } catch {
    return abandon(signal?.aborted ? cancelled : unavailable);
  }
}
