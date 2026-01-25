# Relace MCP

!!! warning "非官方项目"
    这是一个<strong>个人项目</strong>，与 Relace 无关联。

!!! info "AI 构建"
    完全由 AI 辅助开发（Antigravity、Codex、Cursor、Github Copilot、Windsurf）。

提供 AI 驱动的代码编辑和智能代码库探索工具。

## 核心功能

=== "Fast Apply"

    通过 Relace API 以 **10,000+ tokens/sec** 速度应用代码编辑

    - 行级精确合并
    - 保留格式
    - 自动处理冲突

=== "Agentic Search"

    自然语言代码库探索

    - 使用自然语言提问
    - 获得精确代码位置

=== "Cloud Search"

    云端仓库语义搜索

    - 同步多个仓库
    - 跨仓库搜索
    - 快速语义索引

=== "Agentic Retrieval"

    两阶段语义 + 智能代码检索。

    - 使用自然语言提问
    - 结合语义索引取得相关档案，进一步搜索获得精确代码位置

## 对比

| 没有 MCP | 使用 `fast_apply` + `agentic_search` |
|:---------|:-------------------------------------|
| 手动 grep，漏掉相关文件 | 自然提问，精确定位 |
| 编辑破坏其他导入 | 追踪导入和调用链 |
| 完整重写浪费 tokens | 描述变更，无需行号 |
| 行号错误破坏代码 | 10,000+ tokens/秒 合并 |

## 开始

5 分钟上手：

1. **安装**:
    ```json
    {
      "mcpServers": {
        "relace": {
          "command": "uv",
          "args": ["tool", "run", "relace-mcp"],
          "env": {
            "RELACE_API_KEY": "your-api-key-here",
            "MCP_BASE_DIR": "/path/to/your/project"
          }
        }
      }
    }
    ```
2. **配置**: 添加到 MCP 客户端（Cursor、Claude Desktop 等）
3. **使用**: 开始使用 AI 驱动的代码工具

[快速入门](getting-started/quick-start.md){ .md-button .md-button--primary }
[GitHub 仓库](https://github.com/possible055/relace-mcp){ .md-button }

## 文档结构

<div class="grid cards" markdown>

-   :material-clock-fast:{ .lg .middle } __开始__

    ---

    安装、配置和基本用法

    [:octicons-arrow-right-24: 快速开始](getting-started/quick-start.md)

-   :material-tools:{ .lg .middle } __工具__

    ---

    每个 MCP 工具的详细文档

    [:octicons-arrow-right-24: 工具总览](tools/index.md)

-   :material-rocket-launch:{ .lg .middle } __高级__

    ---

    仪表盘、基准测试和 API 参考

    [:octicons-arrow-right-24: 高级主题](advanced/index.md)

-   :material-account-group:{ .lg .middle } __贡献__

    ---

    开发指南和贡献准则

    [:octicons-arrow-right-24: 贡献指南](contributing/index.md)

</div>

## 社区

- **Issues**: [GitHub Issues](https://github.com/possible055/relace-mcp/issues)
- **PyPI**: [relace-mcp](https://pypi.org/project/relace-mcp/)

## 许可证

本项目采用 [MIT License](https://github.com/possible055/relace-mcp/blob/main/LICENSE) 许可。
