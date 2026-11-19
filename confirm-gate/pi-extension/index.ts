/**
 * Confirm gate extension for pi.
 *
 * Pi hooks are adapters: the dialog and ticket logic live in gate.ts, the
 * review-push rule in push-guard.ts. This file has no runtime imports from pi,
 * so `node --test` can load it without pi installed.
 *
 * Install: link this directory into ~/.pi/agent/extensions/ (see ../README.md).
 */

import type { ExtensionAPI } from '@earendil-works/pi-coding-agent';
import { decide, stateDir } from './gate.ts';
import { reviewPushBlockReason } from './push-guard.ts';

export const TOOL_NAME = 'confirm_gate';

/** Plain JSON Schema: pi validates tool arguments as JSON Schema whatever built it. */
const PARAMETERS = {
  type: 'object',
  properties: {
    action_id: {
      type: 'string',
      description: 'The action_id printed by the gate script that registered the pending action.',
    },
  },
  required: ['action_id'],
  additionalProperties: false,
};

export default function confirmGate(pi: ExtensionAPI): void {
  pi.registerTool({
    name: TOOL_NAME,
    label: 'Confirm gate',
    description:
      'Ask the user to confirm a pending write that a gate skill script has registered. ' +
      'Pass the action_id the script printed; the dialog shows the summary the script recorded. ' +
      'Returns approved, declined, cancelled, unavailable, or unknown_action. ' +
      'Only approved lets the script execute; the script itself checks the confirmation, ' +
      'so a reply typed in chat never substitutes for this tool.',
    promptSnippet: 'Ask the user to confirm a pending gated write by its action_id',
    parameters: PARAMETERS as never,
    executionMode: 'sequential',
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const actionId = (params as { action_id?: unknown }).action_id;
      const ui = {
        hasUI: ctx.hasUI,
        select: (title: string, options: string[], opts?: { signal?: AbortSignal }) =>
          ctx.ui.select(title, options, opts),
      };
      const outcome = await decide(stateDir(), typeof actionId === 'string' ? actionId : '', ui, signal);
      return {
        content: [{ type: 'text', text: outcome.text }],
        details: { decision: outcome.decision },
      };
    },
  });

  pi.on('tool_call', async (event) => {
    if (event.toolName !== 'bash') return undefined;
    const reason = reviewPushBlockReason((event.input as { command?: unknown }).command);
    return reason ? { block: true, reason } : undefined;
  });
}
