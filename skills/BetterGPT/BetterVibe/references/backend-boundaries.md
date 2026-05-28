# Backend Boundaries

Keep backend layers clear and side effects explicit.

## Layer Rules

- Routes/controllers/handlers: transport, validation, orchestration entry.
- Services: domain workflow and business coordination.
- Repositories/DAO/persistence: data access.

Do not let one layer quietly absorb the others.

## Data Rules

- Keep API DTOs, domain objects, and database models distinct when their responsibilities differ.
- Do not expose storage shape as the API contract by accident.
- Keep side effects such as cache, queue, third-party calls, and persistence updates visible and testable.

## Avoid

- giant controllers, handlers, or services
- one method doing validation, business rules, persistence, and response assembly
- a "service layer" that is actually the whole system hidden in one file
