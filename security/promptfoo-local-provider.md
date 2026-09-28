# Promptfoo 0.123.1 local-provider findings

The pinned CLI was inspected and started successfully. `promptfoo redteam
generate -c security/promptfooconfig.yaml` reaches the remote red-team
generation path and then prompts for work-email verification before generating
cases. This is an account/hosted-generation gate, not an InsightHub `/chat`
call and not a result from grading the local target. No verification was
bypassed or automated.

The installed version supports an explicit adversarial-test provider through
the `redteam generate --provider <provider>` option. Its remote-generation
logic also recognizes:

```text
PROMPTFOO_DISABLE_REDTEAM_REMOTE_GENERATION=true
```

and the broader:

```text
PROMPTFOO_DISABLE_REMOTE_GENERATION=true
```

The first is the preferred setting when using a user-supplied provider for
red-team generation. Strategies or plugins that inherently require Promptfoo
Cloud/remote generation may still be unavailable; that must be reported as a
tooling limitation rather than silently substituted.

The remaining local-provider command shape is:

```powershell
$env:OPENAI_API_KEY = '<set outside the repository>'
$env:PROMPTFOO_DISABLE_REDTEAM_REMOTE_GENERATION = 'true'
promptfoo redteam generate `
  -c security/promptfooconfig.yaml `
  --provider openai:chat:<model> `
  -o security/evidence/promptfoo-generated.yaml
```

The model/provider identifier must be selected by the operator and supported
by the installed Promptfoo provider implementation. Keys must remain in the
process environment or an ignored local secrets file; they must not be put in
committed YAML, JSON, prompt logs, or evidence.

InsightHub is a separate provider configuration. Its real path requires
`RAG_MODE=real`, a real `LLM_PROVIDER`, the provider-specific chat model and
credential, and—when retrieval is enabled—a real `EMBEDDING_PROVIDER`,
embedding model, credential, and matching embedding dimension. The current
fixture index must not be treated as a real-provider index: documents need to
be re-ingested with the selected embedding identity. There must be no silent
fallback to fixture mode.

Promptfoo grading is a separate concern from adversarial generation. The
operator must configure a local/user-supplied grader or a supported local
assertion path and verify that the selected red-team plugins do not request
remote grading. This repository has not claimed real-provider generation or
grading because no provider credential/model is configured.
