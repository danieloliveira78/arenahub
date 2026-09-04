# Auth Testing Playbook (Emergent Google OAuth)

## Session model
- Backend endpoint: `POST /api/auth/session` accepts `{ session_id }` from URL fragment, calls Emergent, upserts user, stores `user_sessions` row, sets httpOnly `session_token` cookie (7 days).
- Frontend `AuthCallback` detects `#session_id=` synchronously in `location.hash`, POSTs to `/api/auth/session`, then navigates to `/dashboard`.
- Protected routes call `GET /api/auth/me` which reads cookie or `Authorization: Bearer <token>` fallback.

## Bypass for tests (create session directly in Mongo)

```
mongosh --eval "
use('test_database');
var userId = 'test-user-' + Date.now();
var sessionToken = 'test_session_' + Date.now();
db.users.insertOne({
  user_id: userId,
  email: 'test.user.' + Date.now() + '@example.com',
  name: 'Test User',
  picture: 'https://via.placeholder.com/150',
  is_admin: false,
  created_at: new Date().toISOString()
});
db.user_sessions.insertOne({
  user_id: userId,
  session_token: sessionToken,
  expires_at: new Date(Date.now() + 7*24*60*60*1000).toISOString(),
  created_at: new Date().toISOString()
});
print('Session token: ' + sessionToken);
print('User ID: ' + userId);
"
```

To create admin session:
```
mongosh --eval "
use('test_database');
var userId = 'admin-' + Date.now();
var sessionToken = 'admin_session_' + Date.now();
db.users.insertOne({
  user_id: userId,
  email: 'danieloliveira78@gmail.com',
  name: 'Daniel Admin',
  picture: '',
  is_admin: true,
  created_at: new Date().toISOString()
});
db.user_sessions.insertOne({
  user_id: userId,
  session_token: sessionToken,
  expires_at: new Date(Date.now() + 7*24*60*60*1000).toISOString(),
  created_at: new Date().toISOString()
});
print('ADMIN Session token: ' + sessionToken);
"
```

## Sending auth in requests

- curl: `-H "Authorization: Bearer <session_token>"`
- Browser test: set cookie
```
await page.context.add_cookies([{
    "name": "session_token", "value": "<token>",
    "domain": "<host>", "path": "/",
    "httpOnly": True, "secure": True, "sameSite": "None"
}])
```

## Route matrix
- Public: /, /competicoes, /competicoes/:id, /payment/*
- Auth: /dashboard, POST /api/registrations, /api/my-registrations
- Admin only: /admin, /admin/competicoes/:id and all POST/DELETE /api/competition-types, /api/competitions, /api/competitions/:id/draw, /api/competitions/:id/bracket, PUT /api/matches/:id
