// Nonproduction recipe feasibility implementation, independent of the Python oracle.
import fs from 'node:fs';
import crypto from 'node:crypto';

const input = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const result = {};
function digest(name, fields) {
  const chunks = [];
  for (const field of fields) {
    const bytes = Buffer.from(String(field), 'utf8');
    const length = Buffer.alloc(8);
    length.writeBigUInt64BE(BigInt(bytes.length));
    chunks.push(length, bytes);
  }
  const preimage = Buffer.concat(chunks);
  const sha256 = crypto.createHash('sha256').update(preimage).digest('hex');
  result[name] = {preimage_hex: preimage.toString('hex'), sha256};
  return sha256;
}
const ordered = (rows, key) => [...rows].sort((a, b) => Buffer.compare(Buffer.from(key(a)), Buffer.from(key(b))));
const packageRows = ordered(input.package_files, row => row.relative_path);
const P = digest('P', ['memorii.observation-activation.package-payload.v1',
  ...packageRows.flatMap(row => [row.relative_path, row.size, row.sha256])]);
const env = input.environment;
const distributions = ordered(env.distributions, row => row.name);
const files = ordered(env.installed_files, row => `${row.distribution}\0${row.path}`);
const E = digest('E', ['memorii.observation-activation.environment.v1',
  env.python_implementation, env.python_version, env.platform_tag,
  env.install_policy, env.cache_policy, env.origin_policy, distributions.length,
  ...distributions.flatMap(row => [row.name, row.version, row.wheel_sha256,
    row.record_sha256, row.top_level_roots.length,
    ...[...row.top_level_roots].sort((a,b) => Buffer.compare(Buffer.from(a),Buffer.from(b)))]),
  files.length, ...files.flatMap(row => [row.distribution, row.path, row.size, row.sha256])]);
const entries = ordered(input.entries, row => `${row.schema_id}\0${row.schema_version}`);
const prefix = [P, E, input.publication_digest, input.registry_digest,
  input.decoder_source_manifest_digest, entries.length];
const fields = row => [row.schema_id, row.schema_version, row.schema_fingerprint,
  row.binding_digest, row.entry_digest];
digest('schema', ['memorii.observation-activation.schema.v1', ...prefix,
  ...entries.flatMap(fields)]);
digest('codec', ['memorii.observation-activation.ledger-codec.v1', ...prefix,
  ...entries.flatMap(row => [...fields(row), row.decoder_id, row.implementation_source_digest])]);
digest('writer', ['memorii.observation-activation.writer.v1', P, E, input.memorii_wheel_sha256]);
process.stdout.write(JSON.stringify(result));
