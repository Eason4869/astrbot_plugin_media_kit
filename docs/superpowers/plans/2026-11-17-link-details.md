# Link details and GitHub v1.3.0

Approved specification: the 2026-11-17 conversation plan.

1. Validate anonymous commerce paths; do not ship unsupported platforms.
2. Add public GitHub repository/issue/PR/release cards and bounded details,
   optional token, independent parse/image proxy options matching Twitter.
3. Add quoted-message detail command and mode-specific link quotas while
   preserving shared user quotas and existing output/permission controls.
4. Add optional on-demand Chinese summaries reusing the configured LLM
   transport, independent of translation enablement; preserve factual output
   on timeout, unavailable models, or malformed output.
5. Verify offline regressions, real public samples and card rendering; update
   version/docs, review, push main, verify/fix CI, tag v1.3.0. No Release.

Defaults: public resources only; token optional; 5-minute API cache;
30-minute summary cache; 24,000 input characters; 1,000 output characters;
30-second AI deadline; 10 latest comments, 20 PR files/release asset links.
No clone, attachment download, full-repository audit, or AI-invented prices.
