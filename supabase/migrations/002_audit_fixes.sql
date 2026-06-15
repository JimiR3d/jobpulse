-- ═══════════════════════════════════════════════════════════════
-- JobPulse — Audit Fix Migration (L5)
-- Tightens telegram_link_codes RLS policy.
-- The old policy allowed any authenticated user to read all codes.
-- The backend uses service_role (bypasses RLS) so this has no impact
-- on functionality, but prevents potential frontend abuse.
-- ═══════════════════════════════════════════════════════════════

-- Drop the overly permissive policy
drop policy if exists "telegram_codes_all" on public.telegram_link_codes;

-- Replace with a restrictive policy (only service_role can access)
-- Frontend never reads this table directly, only backend does via service_role
create policy "telegram_codes_service_only"
  on public.telegram_link_codes
  for all
  using (false);
