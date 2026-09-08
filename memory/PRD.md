# ArenaHub — SaaS Multi-Tenant de Gestão de Torneios

## Original Problem Statement (Feb 2026 - SaaS pivot)
Transformar o ArenaHub em uma plataforma B2B SaaS multi-tenant. Cada admin/cliente tem seu ambiente isolado (tenant) para gerenciar torneios, atletas e partidas. NUNCA um admin vê dados de outro. Cadastro público, plano Starter R$ 49/mês (ou R$ 490/ano), 14 dias de trial sem cartão, limites de 5 torneios ativos e 200 atletas, 7 dias de graça após falha de pagamento (view-only depois disso), Stripe Checkout + Webhooks, Super Admin com MRR e tenants.

## Architecture
- Backend: FastAPI + Motor (MongoDB async). Todas as rotas sob `/api`.
- Frontend: React 19 + React Router 7 + Tailwind + shadcn/ui (dark theme).
- Auth: (a) Email/senha com bcrypt + session cookie, (b) Emergent-managed Google OAuth. Ambos coexistem.
- Payments: Stripe Subscriptions (R$49/mo, R$490/yr) + Stripe Checkout one-off para inscrições de torneios.
- Emails: Emergent-managed Resend.

## Multi-Tenant Model
- `tenants`: `{tenant_id, slug, name, owner_user_id, subscription_status, plan, trial_end, current_period_end, stripe_customer_id, stripe_subscription_id, cancel_at_period_end, plan_lookup_key}`
- `users`: agora com `tenant_id`, `tenant_role` (admin), `platform_role` (super_admin | null)
- Todas as coleções (competition_types, competitions, registrations, teams, matches, payment_transactions) filtram por `tenant_id` vindo do token — nunca do body.
- `resolve_principal` injeta `_tenant`, `_effective_status`, `_can_write` na request.
- `require_admin` = `resolve_principal` + `is_admin | super_admin`.
- `require_active_subscription` bloqueia writes fora do trial/active/grace.
- Super Admin (email = OWNER_EMAIL) bypassa filtros de tenant.

## Plans & Billing
- `TRIAL_DAYS = 14`, `GRACE_DAYS = 7`.
- `PLAN_LIMITS = {"starter": {"tournaments": 5, "athletes": 200}}`.
- Stripe products/prices semeados via `/app/backend/setup_stripe.py` (lookup_keys: `starter_monthly`, `starter_yearly`).
- Webhooks: `customer.subscription.created/updated/deleted`, `invoice.payment_failed`.
- `effective_status`: trialing | active | past_due (→ grace_period nos 7 dias após CPE) | inactive | canceled.

## Personas
- **Super Admin** (danieloliveira78@gmail.com) — vê todos os tenants, MRR, receita.
- **Tenant Admin** — dono de uma organização, cria torneios, gerencia inscritos, roda sorteio/chaveamento.
- **Atleta** — se inscreve em torneios (público, ou logado).

## Implemented (Feb 2026 - SaaS)
- `/api/auth/signup` (email/senha + auto-provisiona tenant + trial 14 dias).
- `/api/auth/login` (email/senha, bcrypt).
- `/api/auth/session` (Emergent Google OAuth, mantido).
- `/api/plans` (lista Stripe prices ao vivo).
- `/api/me/tenant` (tenant + effective_status + can_write + limits).
- `/api/subscriptions/checkout|portal|cancel`.
- `/api/stripe/webhook` (subscription events + tournament one-off).
- `/api/platform/stats|tenants|migrate` (super_admin).
- Isolamento tenant em: competitions CRUD, competition-types CRUD, registrations CRUD, draw, bracket, matches, checkin, admin/users, admin/finance, admin/refund.
- Startup migration: promove OWNER a super_admin, seed password de `ADMIN_PASSWORD`, backfill de tenant_id em legacy docs, auto-provisiona tenants para usuários órfãos.
- Frontend: `Signup`, `Login`, `Plans`, `SubscriptionSuccess`, `MinhaAssinatura`, `SuperAdmin` + banner de trial/grace/inactive no Navbar + rota `/platform/admin` gated como `superAdminOnly`.
- **AccessGate** (`/app/frontend/src/components/AccessGate.jsx`) + hook `useSubscription`: bloqueio full-page nas rotas admin quando `can_write=false` (trial expirado/canceled/inactive), com CTA único para `/planos`.
- **Toggle Mensal/Anual** em `/planos` com selo "2 meses grátis" no anual + banner "Economize R$ 98 por ano" no card.
- **Recuperação de senha via Resend** (`/api/auth/forgot-password` + `/api/auth/reset-password`, páginas `/esqueci-senha` e `/redefinir-senha`): token com expiração de 1 hora armazenado em `password_reset_tokens`, ok:true sem vazar existência de e-mail, sessões invalidadas ao redefinir.
- **Formato "Duplas Rotativas" (Rei da Praia)**: cadastro individual, grupos de 4 jogadores × 3 rodadas com todas as combinações de duplas, pontuação individual acumulada (soma do placar do time), top-2 por grupo avança, eliminatória com re-sorteio de duplas a cada rodada. Novo painel `RotatingPanel` + endpoints `/rotating/draw-groups`, `/rotating/groups`, `/rotating/leaderboard`, `/rotating/next-knockout-round`.
- Testes: 21/21 SaaS backend + 8/8 SaaS frontend + 7/7 password reset backend + 4/4 password reset frontend + 9/9 rotativas backend + 3/3 rotativas frontend.

## Backlog (P1)
- UI de bloqueio total quando `can_write=false` (fim do período de graça).
- Onboarding do 1º admin (escolha de esporte + criação do 1º torneio).
- Toggle mensal/anual no UI de planos.

## Backlog (P2/P3)
- Métricas reais Super Admin: churn, tenants ativos por período.
- Plano Free, cupons de desconto, split de comissão nas inscrições.
- Recuperação de senha (forgot/reset via Resend email).
- App mobile, API pública, CSV import de atletas.

## Next Tasks (curto prazo)
- Testar frontend SaaS end-to-end (Signup → Plans → Stripe → Dashboard).
- Substituir /platform/migrate manual pelo startup migration (feito).
- Popular navbar com CTA "Assinar agora" quando em trial.
