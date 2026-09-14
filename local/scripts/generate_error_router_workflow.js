#!/usr/bin/env node
'use strict';
// One-shot generator: builds the M3 error-router workflow JSON with the
// canonical failure-taxonomy module embedded BYTE-IDENTICALLY into the
// Code node (the parity invariant the M3 test suite asserts).
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const corePath = path.join(ROOT, 'local', 'canonical', 'n8n_failure_taxonomy.js');
const outPath = path.join(ROOT, 'local', 'n8n', 'workflows',
  'GREEN-OPS-ERROR-GLOBAL_FAILURE_ROUTER.json');

const core = fs.readFileSync(corePath, 'utf8');

// Harness prepended inside the Code node: adapts n8n's `$input`/`$execution`
// helpers to the canonical builder, then emits one engine.log.v1 line.
const harness = `'use strict';
// === BEGIN canonical failure taxonomy (byte-identical embed) ===
`;
const harnessTail = `
// === END canonical failure taxonomy — source: local/canonical/n8n_failure_taxonomy.js ===
const __errData = $input.first().json;
const __executionId = (typeof $execution !== 'undefined' && $execution && $execution.id) ? String($execution.id) : '';
const __line = buildErrorLog(__errData, __executionId);
return [{ json: __line }];
`;

const jsCode = harness + core + harnessTail;

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
      name: 'Classify & Redact Error Payload',
      type: 'n8n-nodes-base.code',
      typeVersion: 2,
      position: [500, 300]
    }
  ],
  pinData: {},
  connections: {
    'Error Trigger': {
      main: [[{ node: 'Classify & Redact Error Payload', type: 'main', index: 0 }]]
    }
  },
  active: false,
  settings: { executionOrder: 'v1' },
  versionId: 'f9b8c23d-4190-4a82-9e23-7a19d854e120',
  meta: { templateCredsSetupCompleted: true },
  tags: [{ name: 'GREEN' }, { name: 'OPS' }, { name: 'ERROR-ROUTER' }, { name: 'PHASE5-M3' }]
};

fs.writeFileSync(outPath, JSON.stringify(workflow, null, 2) + '\n', 'utf8');
console.log('wrote ' + path.relative(ROOT, outPath));
