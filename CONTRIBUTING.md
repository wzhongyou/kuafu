# Contributing to kuafu

感谢你对 kuafu 的关注！欢迎贡献代码、报告问题或提出建议。

## 报告问题

- 在 [GitHub Issues](https://github.com/wzhongyou/kuafu/issues) 提交
- 包含：Python 版本、操作系统、复现步骤、预期行为

## 提交 PR

1. Fork 仓库
2. 创建特性分支：`git checkout -b feature/my-feature`
3. 编写代码 + 测试
4. 确保通过所有检查：
   ```bash
   pytest tests/ -v
   ruff check src/
   ```
5. 提交 PR，描述变更内容和原因

## 代码规范

- Python 3.10+，使用 type hints
- 代码风格：ruff（配置在 pyproject.toml）
- 行宽：100 字符
- 异步代码使用 asyncio
- 日志使用 structlog，不使用 print（ConsolePipeline 除外）
- 新功能需附带测试

## 开发环境

```bash
# 安装全部依赖
pip install -e ".[dev,web]"

# 运行测试
pytest tests/ -v

# 代码检查
ruff check src/

# 类型检查
mypy src/
```

## Commit 规范

使用简洁的英文描述：

- `add: ...` 新功能
- `fix: ...` 修复
- `refactor: ...` 重构
- `docs: ...` 文档
- `test: ...` 测试

## 项目结构

详见 [docs/design.md](docs/design.md) 和 [README.md](README.md)。
