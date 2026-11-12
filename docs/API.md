# EasyKig Gateway API v0.1

默认网关地址：`http://127.0.0.1:8000`，对所有 POST 接口发送 `Authorization: Bearer <EASYKIG_SERVER_TOKEN>`。

## `GET /health`

无需鉴权。返回 `status`、`version`、`preview_enabled` 和 `mesh_editor_enabled`。后两个字段表示已配置相应凭据或上游地址。
同时返回 `image_model`（默认模型）和 `image_models`（允许选择的模型 ID 列表）。

## `GET /v1/image/models`

使用网关 Bearer Token 鉴权。查询参数 `provider=gateway|chatgpt_credits`，返回所选来源的 `image_models` 及默认 `image_model`。ChatGPT API credits 路径使用关联 API 组织的项目密钥从 OpenAI 查询模型。

## `POST /v1/edit/parameters`

请求：

```json
{
  "prompt": "脸颊更圆一些，眼睛大一点",
  "shape_keys": {"Eye Size": 0.2, "Cheek Fullness": 0.3},
  "ranges": {"Eye Size": [0, 1], "Cheek Fullness": [0, 1]}
}
```

响应：

```json
{
  "shape_keys": {"Eye Size": 0.38, "Cheek Fullness": 0.48},
  "changes": {"Eye Size": 0.38, "Cheek Fullness": 0.48},
  "mode": "rules",
  "message": "Rule-based edit; review visually."
}
```

仅支持现有 Shape Keys，插件端进一步裁剪值域。规则基线不代表 AI 模型。

## `POST /v1/reference/transform`

请求 `{"stage":"head|design|product","source_png_base64":"...","prompt":"..."}`，响应 `{"image_png_base64":"...","stage":"head|design|product","mode":"image_edit"}`。每张图限 8 MiB PNG。可用 `additional_png_base64` 追加最多 6 张图，按数组顺序发送给供应商。配置 `EASYKIG_REFERENCE_PROMPTS_DIR` 时按阶段发送对应的 UTF-8 预设原文，忽略请求的 `prompt`。图像模型需要 `OPENAI_IMAGE_API_KEY`。

## `POST /v1/image/reference-prompt`

请求 `{"stage":"head|design|product","prompt":"..."}`，响应 `{"prompt":"..."}`。使用和 `/v1/reference/transform` 相同的预设加载逻辑。Blender 直连图像 API 时可以单独取得 Prompt。

## `POST /v1/preview/finish`

请求 `{"white_png_base64":"...","reference_png_base64":"... (optional)","prompt":"..."}`，响应 `{"image_png_base64":"...","mode":"image_edit","warning":"..."}`。源图限 8MB PNG。

可通过 `additional_png_base64` 提供最多 3 张补充参考图。网关将白模作为第一张图，其余参考图用于配色和风格。`GET /health` 的 `multi_reference_images` 表示网关支持此字段和参考图接口的新上限。

两个图像接口都接受可选的 `provider` 和 `model`。省略 `provider` 时使用网关默认来源。显式选 `chatgpt_credits` 时请求使用 `OPENAI_SUBSCRIPTION_API_KEY`。模型可从 `/v1/image/models` 获取。

## `POST /v1/edit3d`

请求：

```json
{
  "prompt": "Make the chin shorter, keep the existing eye openings",
  "mesh_glb_base64": "<base64 of binary GLB, max 20MB>"
}
```

响应：

```json
{
  "mesh_glb_base64": "<base64 of edited binary GLB>",
  "mode": "upstream"
}
```

目前仅转发到 `EASYKIG_EDIT3D_UPSTREAM_URL`，没有现成的几何模型。未配置时返回 501。你的远端 inference server 只需实现 **同一请求/响应 JSON 协议**，网关即可转发。所有图片/模型上传均由 Blender UI 中的明确点击触发。

## 设计与安全边界

- 大请求：单输入 PNG 不超过 8 MB，输入 GLB 不超过 20 MB。
- 反向代理应限制请求体大小和超时，并配置 HTTPS 与鉴权。
- 网关仅在环境变量指定的 API/上游 URL 上发起请求；远端地址不由 Blender 上传参数控制，避免任意 SSRF。
- `Authorization` 令牌保存在用户本机 Blender 偏好设置，建议通过 HTTPS 或 SSH 隧道使用。
- 当前编辑是同步 HTTP；生产环境应增加异步任务队列、任务 ID、结果持久化和重试。
