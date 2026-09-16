# base-py

个人 Python 3.14 工程模板，使用 uv、Ruff、mypy 和 pytest。

## 初始化

```bash
uv sync --locked --dev
git config core.hooksPath .githooks
```

## 运行

```bash
uv run --locked python src/main.py
```

## 格式化 / 修复

```bash
uv run --locked ruff check --fix .
uv run --locked ruff format .
```

## 检查

```bash
uv run --locked python scripts/check.py
```

完整检查包含 Ruff format/lint、mypy strict 和 pytest，且不会修改或暂存源码。

基于此模板建立具体项目后，请按实际项目重写 README 和 AGENTS.md。

## License

Apache-2.0
