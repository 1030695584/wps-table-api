# wps-table-api

一个基于 WPS OpenAPI 的多维表格 Python 客户端项目，当前使用应用授权（client_credentials）方式访问 WPS 365 多维表格接口，并内置 KSO-1 签名。

## 功能特性

- 支持应用授权获取 access_token
- 支持 KSO-1 请求签名
- 支持多维表格 Schema 查询
- 支持数据表、字段、记录、视图、附件等常用接口封装
- 支持通过 `.env` 管理运行配置
- 使用标准 Python 包结构，便于维护和扩展

## 项目结构

```text
wps-table-api/
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
├── wps_sheets.py
└── wps_table/
    ├── __init__.py
    ├── api.py
    ├── config.py
    └── runner.py
```

## 运行环境

- Python 3.10+

## 安装方式

```bash
pip install -r requirements.txt
```

## 配置说明

复制 `.env.example` 为 `.env`，并填写以下内容：

```env
WPS_CLIENT_ID=你的应用ID
WPS_CLIENT_SECRET=你的应用密钥
WPS_FILE_ID=你的多维表格文件ID
```

## 使用方式

```bash
python wps_sheets.py
```

## 输出说明

程序启动后会：

1. 从 `.env` 加载配置
2. 使用应用授权获取 access_token
3. 请求多维表格 Schema
4. 输出接口返回结果

## 依赖说明

- `requests`：HTTP 请求
- `loguru`：日志输出
- `python-dotenv`：加载 `.env` 配置

## 后续可扩展方向

- 增加更多 API 示例入口
- 增加异常码映射与更清晰的错误提示
- 增加单元测试与集成测试
- 增加中文乱码处理与日志格式优化
