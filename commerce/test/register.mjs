/**
 * D-172 Phase 2 — native unit-test loader registration (`npm test`), mirroring
 * `control-plane/test/register.mjs`. No dependency is added: `node:module` is a
 * built-in.
 */
import { register } from 'node:module';

register(new URL('./alias-resolver.mjs', import.meta.url));
