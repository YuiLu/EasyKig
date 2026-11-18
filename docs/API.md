# EasyKig 网关 API

网关处理模板 GLB、单部件参考图与 ShapeUp 任务。客户端上传 GLB 按 glTF 米单位约定，插件负责场景单位换算。输入 GLB 上限 20 MiB，PNG 上限 8 MiB。

## 认证

默认 `EASYKIG_AUTH_MODE=token`，业务接口使用 `Authorization: Bearer <EASYKIG_SERVER_TOKEN>`。

SSH 隧道可设置 `EASYKIG_AUTH_MODE=ssh`，由 `scripts/run_gateway.py` 绑定回环地址并关闭代理地址头解析。此模式接受实际回环请求。公网或 Docker 桥接连接使用 Token 模式。

## GET /health 和 GET /v1/health

`/health` 无需认证，`/v1/health` 校验凭据。返回 `status`、`name`、`version`、`auth_mode`、`authenticated_health`、`mesh_editor_enabled`、`mesh_editor_backend`、`mesh_editor_async`、`mesh_editor_requires_image` 和 `mesh_editor_text`。当前文字条件能力为 false。

## GET /v1/edit3d/health

认证后检查 ShapeUp `/readyz`。成功返回 `ready: true`，模型或 GPU 未就绪返回 503，上游凭据被拒绝返回 502。

## POST /v1/edit3d/jobs

认证后提交图像条件编辑任务。

```json
{
  "mesh_glb_base64": "<source GLB>",
  "edit_png_base64": "<component reference PNG>",
  "prompt": "optional editing notes",
  "seed": 10,
  "steps": 30,
  "watertight_resolution": 512
}
```

`seed` 为 0–4294967295，`steps` 为 1–100，`watertight_resolution` 可选 128、256、512。ShapeUp 当前只使用源网格和目标图像，`prompt` 预留给后续文字条件编辑。

返回 202 和 `{"id":"<32位十六进制任务ID>","status":"queued","backend":"shapeup"}`。队列满返回 429。

## GET /v1/edit3d/jobs/{id}

返回认证用户可查询的任务状态，状态包括 `queued`、`running`、`succeeded`、`failed`。未知任务返回 404，非法 ID 返回 422。

## GET /v1/edit3d/jobs/{id}/result

成功后返回 `model/gltf-binary`。未完成返回 409。网关在 CPU 上还原 ShapeUp 的中心和尺度。任务恢复信息由 `EASYKIG_EDIT3D_JOB_DIR` 持久化保存。

## 兼容接口

`POST /v1/edit3d` 保留已有 generic 文字 + GLB 上游协议。新的 Blender 编辑入口使用 ShapeUp 异步任务。
