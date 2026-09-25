# 1-reja (Backend yadrosi) — ijro davomida qabul qilingan qarorlar

Manba: SDD jurnali. Har bir qator: qaror — sabab — noto'g'ri bo'lsa narxi.

- Ruling: Work on branch feat/backend-yadro in the same repo instead of a separate worktree — repo is brand new and has no other active work — cost if wrong: none (branch isolates changes).
- Ruling: StarletteDeprecationWarning (plan-mandated) — fix with a targeted pytest filterwarnings ignore for that exact message (or a drop-in replacement if the warning names one compatible with FastAPI TestClient) rather than pinning old starlette — cost if wrong: when starlette removes httpx TestClient support, tests break on upgrade (lock pins protect until then).
- Ruling: lock --no-index provenance — require the implementer to document exactly how the lock was produced and confirm the brief's command also works; no forced regeneration if pins are legitimate — cost if wrong: lock not bit-reproducible; Task 13 Makefile `lock` target is the canonical command.
- Ruling: mypy unused-ignore at config.py:122 — remove the ignore now (deviates from plan text) because Task 13 gates on `mypy app` — cost if wrong: none.
- Ruling: Plan 2 authored by a planning subagent (opus) from controller decisions file .superpowers/sdd/planning/plan2-decisions.md — keeps controller context small — cost if wrong: plan quality risk, mitigated by controller spot-check + per-task reviews
- Ruling: I2 — ugk_app keeps SELECT, INSERT and column-level UPDATE(status, retired_at) only; rewrap (wrapped_key rewrite) and retire-shredding (wrapped_key='') run only via CLI as ugk_migrator. Task 13 must follow this: /admin/keys/{purpose}/rotate stays (insert+status update), retire-keys and rewrap-keys CLI use get_engine("migrator") — cost if wrong: operators need migrator secret for key maintenance (acceptable, it is an ops task).
- Ruling: include cheap security minors now (header bytes in AAD, reject empty AAD, blob_version validation, DEK length check, CHECK version<=65535, keep CryptoError.reason as bare token, test gaps) — expertise-relevant and nothing persisted yet so format change is free — cost if wrong: small scope creep in Task 3.
- Ruling: middleware order RequestContext → SecurityHeaders → BodySizeLimit → app; BodySizeLimit uses flag + send-guard instead of relying on exception propagation — cost if wrong: none significant
- Ruling: keep profil_sluzhba as a template role (Обзор + export); TZ does not name the departments, so per-department roles (e.g. Служба закупок → section:zakupki) are created by the admin via /admin/roles (Task 11) — document in the admin guide (Plan 4) — cost if wrong: one-time admin setup step per department.
- Ruling: redesign audit append — HMAC-SHA256 chain with keystore Purpose.AUDIT_CHAIN (versioned per row), append only via SECURITY DEFINER core.audit_reserve()/core.audit_append(), app/etl lose INSERT/UPDATE/sequence grants, verify reports all breaks + audit_anchor for retention, retention floor 12 months, input sanitation, partition function handles default rows — see task-6-findings-r1.md — cost if wrong: more complex audit path; mitigated by tests.
- Ruling: ugk_app SELECT on core.audit_anchor approved (hash-only data, needed by verify).
- Ruling: backup codes become 12 chars "XXXX-XXXX-XXXX" (~59 bits) — cost if wrong: none (not yet used anywhere).
- Ruling: CONTEXT_WORDS keeps "parol" and adds "пароль"; test fixture changed — cost if wrong: none.
- Ruling: add signed double-submit CSRF (csrf = b64url(HMAC(pepper,"csrf",session_token))), CSRF required for all non-safe methods, require_perm() with no perms raises — cheap expertise hardening — cost if wrong: none.
- Ruling: MFA failures share failed_logins lockout; password step no longer resets counter; new challenge invalidates older ones; locked users can't use challenges; wrong current password counts + locks + revokes sessions + dedicated rate limit — cost if wrong: stricter lockouts (admin unlock via unblock).
- Ruling: include expertise-relevant minors: no raw unknown usernames in audit (hint+len+keyed fingerprint), pending TOTP secret bound to challenge, password change rotates session + kills challenges, sessions list hides expired, logout works without valid session, enroll_start rate-limited, extra tests — cost if wrong: scope growth in Task 10.
- Ruling: Task 11 admin block/reset-password/reset-2fa/position change must also invalidate the user's open MFA challenges (used_at=now, pending_secret_enc=NULL) — consistency with Task 10 hardening — cost: none.
- Ruling: no-escalation rules (grant only perms you hold; no editing own role/position; target position role ⊆ actor perms) + last-admin advisory lock + full ADMIN_GUARANTEED invariant + audit denied permission checks + input hardening — cost if wrong: stricter admin UX (only full admins can grant everything).
- Ruling: update_role cannot_modify_self is unconditional (admins cannot edit the admin role through the API; seed/CLI owns it) — cost if wrong: admin-role permission edits need DB/CLI.
- Ruling: target-user mutations require target role perms ⊆ actor perms; branch-limited actors cannot grant scope_all or branches outside their own — cost if wrong: stricter delegation.
- Ruling: target-user protection uses full-permission subset (target perms ⊆ actor perms), so a delegated admin can only manage users whose permissions they themselves hold — consistent with I3 — cost: delegated admins need the section perms of the users they manage.
- Ruling: audit verify rate limit 3/10min per user + 10/h global; export sets X-Export-Truncated — cost: none.
- Ruling: retire_unused refuses purposes with no REGISTRY columns; REENCRYPT_EXEMPT list + introspection test; commit-then-audit for key ops; grace ≥10 min; dev Caddy bound to 127.0.0.1, api on internal front network; reset dev volumes (known temp admin password leaked into report) — cost: dev data reset only.
- Ruling: runtime extra-CA trust becomes opt-in build-arg RUNTIME_EXTRA_CA (default false); CA stays in builder for pip — cost if wrong: an integration needing the corporate CA must build with the flag.
- Ruling: apply all pre-flight amendments to Plan 2 tasks by carrying amendments.md into each task dispatch (plan text unchanged) — cost if wrong: implementers must merge two sources; mitigated by explicit per-task lists.

## Kechiktirilgan kichik topilmalar (yakuniy tekshiruv: hammasi KEEP-DEFERRED)

- Task 1: minor (deferred): Settings.redis_url, empty db_app_password, prod empty redis_password not directly tested
- Task 1: minor (deferred): lock-file header shows --no-index (pip-tools 7.6.1 header quirk) — consider a note near the lock files
- Task 2: minor (deferred): no ALTER DEFAULT PRIVILEGES — each table migration must GRANT explicitly (plan does this)
- Task 2: minor (deferred): 0001 downgrade DROP SCHEMA without CASCADE (fine per-revision)
- Task 3: minor (deferred): refresh-on-miss cost for retired versions (rate-limit), KEK rotation runbook/transition, 0002 downgrade destroys DEKs, label delimiter in keyed_hash/blind_index, nonce budget/rotation cadence doc → Plan 4 security docs
- Task 4: minor (deferred): overflow after response already started → truncated response (accepted edge case)
- Task 5: minor (deferred): ORM uses Python default= where migration has DB DEFAULT (no create_all used)
- Task 6: minor (deferred): record() still calls hmac_key/encrypt_str under head lock — use ring = get_keyring() before txn and ring.encrypt inside
- Task 6: minor (deferred): add zero-rows verify test (migrator txn + rollback); nextval denial test; cache failed key versions within one verify run
- Task 6: minor (deferred): ugk_app INSERT on crypto_keys lets a compromised app insert bogus keys (DoS of load_keyring) — pre-existing; document; consider moving ensure_keys/rotate to a definer function
- Task 6: minor (deferred): ±5 min p_ts window requires NTP sync between app and DB hosts — ops note (Plan 4)
- Task 7: minor (deferred): _BACKUP_RE accepts I/L/O/0/1 chars not in alphabet (harmless — hash won't match)
- Task 8: minor (deferred): reset()/ping() ignore _last_failure backoff; readyz 503 on Redis down while limiter is fail-open (probe design note for Plan 4); _last_failure unlocked global
- Task 9: minor (deferred): password-change allowlist by raw path (brittle under root_path; fails closed); document that data dependencies must depend on Ctx (RLS)
- Task 9: minor (deferred): CSRF failures are not rate-limited (check before ratelimit)
- Task 10: minor (deferred): revoke already-revoked own session → 204+audit; audit written before request commit may disagree with session table; small timing diff on wrong-password branch
- Task 10: minor (deferred): shared failed_logins counter lets an unauthenticated attacker pre-load 4 failures so one password-change typo locks + revokes (consequence of ruling)
- Task 10: minor (deferred): challenges dead via attempts cap keep pending_secret_enc until superseded
- Task 11: minor (deferred): conflicts not audited as denied; update_role no session revoke; create_user IntegrityError mapping; branch_ids existence (Plan 2 FK)
- Task 11: minor (deferred): login/verify ignore position.is_active (empty perms anyway); admin role editable only via seed/DB; log_event second connection under locks
- Task 11: minor (deferred): position role_id has no scope check (covered at user placement)
- Task 12: minor (deferred): 429 on verify not audited; per-user counter increments when global limit trips
- Task 13: minor (deferred): API rotation locks whole table (batch commits later); key version 65535 cap; caddy runs as root in dev (Plan 4 fixes)
- Task 13: minor (deferred): set_keyring_for_process only docstring-guarded; _retire failure audit not per-purpose
