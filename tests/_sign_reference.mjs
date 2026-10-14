// Reference webhook signer, copied verbatim from the PDF Tagger server's signing function
// (signWebhook). Used by test_webhook_cross_lang.py to
// prove the Python SDK verifies a signature produced by the exact server algorithm.
//
// Usage: node _sign_reference.mjs <secret> <timestampSeconds> <body>
import { createHmac } from 'node:crypto';

const [, , secret, timestamp, body] = process.argv;
const hmac = createHmac('sha256', secret).update(`${timestamp}.${body}`, 'utf8').digest('hex');
process.stdout.write(`t=${timestamp},v1=${hmac}`);
