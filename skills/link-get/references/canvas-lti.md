# SJTU Canvas 实录 LTI 链（PAT 版）

2026-09 实测：Canvas PAT 可驱动全部实录端点，无需浏览器 cookie / 钥匙串 / fht-mba。

## 链路

1. `GET /api/v1/courses/{cid}/external_tools/sessionless_launch?id=8329`（Bearer PAT）
   → `{"url": "https://oc.sjtu.edu.cn/...session_token=..."}`
    - tool id `8329` = 「课堂视频新版」；`external_tools` 列表 API 返回 `[]` 时此端点仍可用。
    - 课程无实录入口时此调用返回非 200 / 无 `url` 字段。
2. GET sessionless URL（跟随重定向，CookieJar 收 `_normandy_session` 等 5 个 Set-Cookie）→ 落地 HTML 含 OIDC auto-submit form。
3. POST OIDC form → 返回 id_token auto-submit form → POST（**不跟随**）
   → 302 `Location: ...#jwt_token=...`（fragment 或 `?` 参数里）。
4. `GET {RES}/lms/launch-context`（header `jwt-token`）→ `data.canvasRecord.teachingClassId`（`launchType` 应为 `CANVAS_RECORD`）。
5. `GET {RES}/v1/subject_vod_list_new?teclIds={tecl}&page.pageIndex=1&page.pageSize=1000&page.orders[0].field=courBeginTime&page.orders[0].asc=true`→ `data.records[]`（过滤 `vodEnable==0`；`vodClickEnable==0` 多半还在转码）。
6. `GET {RES}/v1/course_vod_urls_new?courseId={courId}`→ `data.courseVodViewList[].url`（签名 mp4，下载只需 `Referer: https://v.sjtu.edu.cn/`）。

`RES = https://v.sjtu.edu.cn/jy-application-resourcemanage`
jwt_token 是 session 级凭证，每次运行重新 launch 即可；实测不按课程隔离（donor token 可查其它 teclId）。

## play-center 分享链接

`play-center?<b64>` 的 query 是前端 crypto-js AES-128-CBC 密文：

- key = `"jy-resource-qry1"` → hex `6a792d7265736f757263652d71727931`
- iv = `"jy-query-iv-0001"` → hex `6a792d71756572792d69762d30303031`
- 明文形如 `__encrypted_query__:teclId=NNN&target=video`

本地 `openssl enc -d -aes-128-cbc` 解出 teclId 后，借任一在选课的 LTI token 走第 5、6 步。

## 字段速查

| 字段               | 含义                                          |
| ------------------ | --------------------------------------------- |
| viewNum 5          | PPT 录屏（screen，笔记首选）                  |
| viewNum 6          | 电子白板（screen）                            |
| viewNum 1-4, 7     | 教室机位（classroom）                         |
| vodEnable 0        | 无点播资源（过滤掉）                          |
| vodClickEnable 0   | 转码中/未发布（列出但标注）                   |
| record.id / courId | 讲次 id，作 `course_vod_urls_new` 的 courseId |
