# Database migrations

Alembic is the only supported schema-management path. Apply migrations with
`alembic upgrade head`; never replace migrations with `Base.metadata.create_all()`.
