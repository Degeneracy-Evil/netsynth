# base-py

本仓库是 Python 项目的起始模板。

- 使用 Python 3.14 和 uv。
- Ruff 负责格式化与 lint，行宽 120。
- mypy 使用 strict 模式。
- pytest 是测试框架。
- runtime dependency 默认保持为空，按项目需要再增加。
- 完整检查必须保持 non-mutating。
- pre-commit 只检查 staged snapshot，不修改文件，也不自动 stage。
- 不无理由增加重复的 formatter、linter、type checker、package manager 或 framework。

修改后执行：

```bash
uv run --locked python scripts/check.py
uv run --locked python src/main.py
```

具体项目结构建立后，请用项目自己的约定重写本文件。
