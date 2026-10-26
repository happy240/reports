# 喜越尾水交互报表

Streamlit 报表：主数据为 **db3** `agromind` 喜越水肥记录；同棚 **db1** 环境/自动尾水仅作辅助参考。

## 启动

```bash
cd /Users/hyf/Projects/reports
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app/streamlit_app.py
```

`.env` 需配置 `db3`（agromind）与 `db1`（monitor）。`db1` 密码中的 `%3b` 请保持字面量，不做 URL 解码。

## Streamlit Cloud

仓库不包含 `.env`。在应用 **Settings → Secrets** 写入与本地相同的连接串：

```toml
db3 = "mysql://用户:密码@主机:端口/agromind"
db1 = "mysql://用户:密码@主机:端口/monitor"
```

## 数据说明

见 [data_catalog/xiyue/README.md](data_catalog/xiyue/README.md)。
