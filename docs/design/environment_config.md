# Environment Configuration Design

Memorii uses one primary runtime switch and one optional source override:

```dotenv
MEMORII_ENV=local
MEMORII_SECRET_SOURCE=local_file
```

`MEMORII_ENV` identifies the runtime profile. It controls behavior such as validation strictness, production safety checks, feature defaults, and test behavior.

`MEMORII_SECRET_SOURCE` identifies where secrets are loaded from. It is optional and exists for override cases. When it is omitted, Memorii infers the source from `MEMORII_ENV`.

## Runtime Profiles

Supported `MEMORII_ENV` values:

| Environment | Default secret source | Read mechanism |
| --- | --- | --- |
| `local` | `local_file` when `~/.config/memorii/memorii.env` exists, otherwise `process` | Dotenv-style chezmoi file or process env |
| `test` | `process` | Injected mapping or process env |
| `ci` | `github_actions` | GitHub Actions-injected process env |
| `production` | `azure_key_vault` | Azure Key Vault via managed identity |

`MEMORII_SECRET_SOURCE` can override these defaults with one of:

```text
process
local_file
github_actions
azure_key_vault
```

## Loading Flow

```text
1. Read bootstrap values from process env or an injected mapping.
2. Determine MEMORII_ENV.
3. Infer or read MEMORII_SECRET_SOURCE.
4. Load values from the selected source.
5. Return a single env-style mapping.
6. Pass that mapping into typed config parsers.
```

The rest of the application should consume ordinary env-style keys and should not care whether a value came from chezmoi, GitHub Actions, direct process env, or Azure Key Vault.

## Validation Layers

Required variables should be modeled in explicit groups:

| Layer | Examples |
| --- | --- |
| Global | `MEMORII_ENV`, `MEMORII_LLM_PROVIDER` |
| Environment-specific | `MEMORII_AKV_URL`, `MEMORII_AKV_SECRET_NAMES` for production |
| Provider-specific | `OPENAI_API_KEY` for OpenAI, `ANTHROPIC_API_KEY` for Anthropic |
| Feature-specific | live-test keys only when live tests are enabled |

The loader provides `require_environment_keys(...)` for simple required-key checks. Typed config classes should still perform domain-specific parsing and validation after loading.

## Local Development

Local development uses a chezmoi-instantiated dotenv file:

```text
~/.config/memorii/memorii.env
```

Example:

```dotenv
MEMORII_ENV=local
MEMORII_LLM_PROVIDER=openai
OPENAI_API_KEY=
```

For local files, process env values override file values. This allows one-off shell overrides without editing the chezmoi-managed file.

## GitHub Actions

GitHub Actions secrets and variables should be exposed as environment variables:

```yaml
env:
  MEMORII_ENV: ci
  MEMORII_LLM_PROVIDER: openai
  MEMORII_ENABLE_LIVE_LLM_TESTS: ${{ vars.MEMORII_ENABLE_LIVE_LLM_TESTS || 'false' }}
  OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

Memorii does not call a GitHub secrets API. It reads the process environment that GitHub Actions has already populated.

## Production

Production defaults to Azure Key Vault:

```dotenv
MEMORII_ENV=production
MEMORII_AKV_URL=https://example.vault.azure.net/
MEMORII_AKV_SECRET_NAMES=OPENAI_API_KEY,MEMORII_LLM_MODEL
```

The AKV provider fetches only configured secret names. Environment-style names such as `OPENAI_API_KEY` map to AKV secret names such as `OPENAI-API-KEY`. `MEMORII_AKV_SECRET_PREFIX` can be set when the vault uses a shared prefix.

Azure support is optional. Install the `azure` extra before selecting the `azure_key_vault` source.
