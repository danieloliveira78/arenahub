# ArenaHub - Sistema de Cadastro e Gestão de Competições

## Original Problem Statement
Sistema desktop e mobile para cadastros de competições em PT-BR. Admin gerencia tipos de competição e torneios. Usuários fazem login via redes sociais (Google) e se inscrevem em torneios. Torneios possuem datas de inscrição (início/fim), datas do evento (início/fim), premiação e valor de inscrição opcional. Quando pago, integração com plataforma de pagamento (PIX/cartão). Ao confirmar inscrição, e-mail com dados do pagamento e do torneio. Tela de sorteio de duplas para inscrições individuais em torneios de duplas. Chaveamento automático até a final; montagem inicial dos confrontos sorteada. Controle de placares e vencedores por partida.

## Architecture
- Backend: FastAPI + Motor (MongoDB async). All routes under /api.
- Frontend: React 19 + React Router 7 + Tailwind + shadcn/ui (dark theme).
- Auth: Emergent-managed Google OAuth (session_token cookie, 7-day).
- Payments: Stripe claimable sandbox (test mode, BRL).
- Emails: Emergent-managed Resend (transactional confirmations).

## User Personas
- **Organizador (Admin)**: cadastra tipos de competição, cria torneios, gerencia inscritos, roda sorteio de duplas, gera chaveamento, lança placares.
- **Atleta (Usuário)**: navega torneios, se inscreve (individual ou dupla confirmada), paga via Stripe, acompanha painel.

## Core Requirements (static)
- Tipos de competição customizáveis (Futevôlei, Beach Tennis, Padel, etc).
- Torneios com todas as datas + premiação + valor + vagas + local.
- Inscrição gratuita OU paga (Stripe checkout redirect).
- E-mail transacional após inscrição/pagamento confirmado.
- Sorteio aleatório de duplas para inscritos individuais.
- Chaveamento em potência de 2 com BYEs e propagação automática do vencedor.
- Painel admin com RBAC (email OWNER_EMAIL vira admin automaticamente).

## Implemented (Feb 2026)
- Auth via Emergent Google OAuth (backend + frontend + AuthCallback).
- Rotas backend: auth/session, auth/me, logout, competition-types CRUD, competitions CRUD, registrations (grátis + pago), my-registrations, admin registrations, payments/status, stripe/webhook, teams/draw, bracket, matches PUT.
- Frontend: Landing hero, listagem de torneios filtrada, detalhe com modal de inscrição, dashboard usuário, painel admin (2 abas), painel do torneio com sorteio + chaveamento + placares editáveis, payment success/cancel.
- Design: dark tactical (emerald + amber + cyan), Outfit + Plus Jakarta Sans.
- Testes: 20/20 backend tests passando.

## Backlog (P1)
- Painel financeiro admin com totais recebidos e reembolsos.
- Notificações push/e-mail quando o sorteio é realizado.
- Export CSV de inscritos.
- QR Code de check-in no e-mail.
- Rankings / histórico de campeões por atleta.

## Next Tasks
- Testar fluxo com pagamento real (cartão 4242 4242 4242 4242).
- Coletar feedback do usuário sobre UX do sorteio e chaveamento.
