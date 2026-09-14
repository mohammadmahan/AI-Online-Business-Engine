#!/usr/bin/env node
'use strict';
// One-shot generator: builds the M3/M4 error-router workflow JSON with the
// canonical modules embedded BYTE-IDENTICALLY into the Code node (the parity
// invariant the M3/M4 test suites assert):
//   1. local/canonical/n8n_failure_taxonomy.js  (D-052 classify, D-045 redact)
//   2. local/canonical/n8n_dead_letter_sink.js  (D-052 terminal-route router)
// The sink reuses the taxonomy's hoisted `D052` table in the embedded context
// and requires it standalone under Node.
//
// Emit contract (M4): every execution emits one engine.log.v1 line on stdout
// (D-053 logging standard). Terminal classes (B/C/D/E) additionally emit one
// `engine.deadletter.v1` line, tagged <<<DEADLETTER>>> — the transport read
// by local/scripts/dead_letter_bridge.py, which materializes the item into
// the HITL verification queue with D-026 provenance.
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const TAX_PATH = path.join(ROOT, 'local', 'canonical', 'n8n_failure_taxonomy.js');
const SINK_PATH = path.join(ROOT, 'local', 'canonical', 'n8n_dead_letter_sink.js');
const outPath = path.join(ROOT, 'local', 'n8n', 'workflows',
  'GREEN-OPS-ERROR-GLOBAL_FAILURE_ROUTER.json');

const taxonomy = fs.readFileSync(TAX_PATH, 'utf8');
const sink = fs.readFileSync(SINK_PATH, 'utf8');

const T_BEGIN = '=== BEGIN canonical failure taxonomy (byte-identical embed) ===';
const T_END = '=== END canonical failure taxonomy — source: local/canonical/n8n_failure_taxonomy.js ===';
const S_BEGIN = '=== BEGIN canonical dead-letter sink (byte-identical embed) ===';
const S_END = '=== END canonical dead-letter sink — source: local/canonical/n8n_dead_letter_sink.js ===';

const harnessHead = `'use strict';
// ${T_BEGIN}
`;

const tail = `
// ${T_END}
// ${S_BEGIN}
${sink}
// ${S_END}
const __errData = $input.first().json;
const __executionId = (typeof $execution !== 'undefined' && $execution && $execution.id) ? String($execution.id) : '';
const __line = buildErrorLog(__errData, __executionId);
const __route = routeFailure(__line);
if (__route.route === 'retry_backoff') {
  // Class A: retry policy governs; no dead-letter line is emitted.
  console.log('<<<ENGINETRACE>>>' + JSON.stringify(__line));
  return [{ json: __line }];
}
// Terminal class (B/C/D/E): dead-letter line for the bridge -> HITL queue.
console.log('<<<DEADLETTER>>>' + JSON.stringify(__route.dead_letter));
return [{ json: Object.assign({}, __line, { dead_letter: __route.dead_letter }) }];
`;

const jsCode = harnessHead + taxonomy + tail;

const workflow = {
  name: 'GREEN-OPS-ERROR-GLOBAL_FAILURE_ROUTER',
  id: 'e4d7a12b-8c43-4f91-b630-1d89e5a7c001',
  nodes: [
    {
      parameters: {},
      id: 'e4d7a12b-8c43-4f91-b630-1d89e5a7c002',
      name: 'Error Trigger',
      type: 'n8n-nodes-base.errorTrigger',
      typeVersion: 1,
      position: [260, 300]
    },
    {
      parameters: { jsCode: jsCode },
      id: 'e4d7a12b-8c43-4f91-b630-1d89e5a7c003',
      name: 'Classify, Redact & Route Error Payload',
      type: 'n8n-nodes-base.code',
      typeVersion: 2,
      position: [500, 300]
    }
  ],
  pinData: {},
  connections: {
    'Error Trigger': {
      main: [[{ node: 'Classify, Redact & Route Error Payload', type: 'main', index: 0 }]]
    }
  },
  active: false,
  settings: { executionOrder: 'v1' },
  versionId: 'f9b8c23d-4190-4a82-9e23-7a19d854e120',
  meta: { templateCredsSetupCompleted: true },
  tags: [{ name: 'GREEN' }, { name: 'OPS' }, { name: 'ERROR-ROUTER' }, { name: 'PHASE5-M4' }]
};

fs.writeFileSync(outPath, JSON.stringify(workflow, null, 2) + '\n', 'utf8');
console.log('wrote ' + path.relative(ROOT, outPath));
