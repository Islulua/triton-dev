from alembic import context
from triton_dev.platform.models import metadata


def run(connection):
    context.configure(connection=connection, target_metadata=metadata)
    with context.begin_transaction():
        context.run_migrations()


if context.config.attributes.get("connection") is not None:
    run(context.config.attributes["connection"])
else:
    raise RuntimeError("Supply a managed connection for migrations")
