dev *options:
  DATASETTE_SECRET=abc123 \
    uv run \
      --with datasette-cluster-map \
      --with-editable . \
      --prerelease=allow \
    datasette \
      --root \
      --config example/budget_simple/datasette.yaml \
      --plugins-dir=example/budget_simple \
      --static assets:example/budget_simple/static \
      --internal internal.db  \
      test.db \
      {{options}}

dev-server:
  uv run example/budget_simple/server/demo.py