# Mac Developer ID 签名与 Apple 公证

适用于本项目通过 GitHub/网页分发 `.app` + DMG（不是 App Store 上架）。
签名确认开发者身份；公证由 Apple 自动检查软件并签发 ticket。当前构建入口
已支持完整流程；缺少账号/证书时只能生成 ad-hoc 测试包。

## 1. 证书类型

选择 **Developer ID Application**，用于应用、动态库、辅助可执行文件及 DMG。
本项目没有 `.pkg` 安装器，因此当前不需要 Developer ID Installer。
需要 Apple Developer Program 会员；个人开发者可使用个人团队。
官方：[Developer ID certificates](https://developer.apple.com/help/account/certificates/create-developer-id-certificates/)。

## 2. 在本机配置证书

1. Xcode → Settings → Accounts → 添加已加入开发者计划的 Apple Account。
2. 选择团队 → Manage Certificates → `+` → Developer ID Application。
   若团队权限不允许创建，需 Account Holder 在开发者网站创建/授权。
3. 在 Keychain Access 的 login 钥匙串中确认该证书下带有 private key。
   只有 `.cer` 没有对应私钥无法签名。
4. 终端运行 `security find-identity -v -p codesigning`，应列出
   `Developer ID Application: 你的姓名或组织 (TEAMID)`。

私钥留在本机钥匙串。聊天与仓库不需要密码、私钥或 `.p12`。

## 3. 配置公证凭据

在 Apple Account 网站创建 app-specific password；在自己的终端运行：

```bash
xcrun notarytool store-credentials "apt-notary"
```

按交互提示输入 Apple Account、Team ID 与 app-specific password，保存至
Keychain。交互输入不会作为命令字面量写入仓库；配置后脚本只使用 profile 名。
如改用 App Store Connect API key，按 Apple 文档在本机配置同名 profile；
当前不需要把凭据上传 GitHub Secrets，先本机签署最终同源候选。

## 4. 构建、签名、公证与装订

在源码已提交、工作区干净时运行（把身份替换为步骤2查到的完整名称）：

```bash
cd /Users/leonis/Documents/ai-physics-tracker-ejp
APT_CODESIGN_IDENTITY='Developer ID Application: YOUR NAME (TEAMID)' \
APT_NOTARY_PROFILE='apt-notary' \
bash packaging/build_macos.sh
```

现有脚本完成：独立环境构建 → 包内 Mach-O 签名（hardened runtime + timestamp）
→ 原生 smoke → App ZIP提交 Apple → 状态必须 Accepted → App装订/校验
→ DMG创建/签名 → DMG提交 Apple → Accepted → DMG装订/校验
→ Gatekeeper评估 → 生成最后修改后的SHA清单。失败不记为已公证。
Apple实际处理耗时不由脚本预估；日志中的 submission ID可查询状态/失败日志。

```bash
xcrun notarytool info SUBMISSION_ID --keychain-profile apt-notary
xcrun notarytool log SUBMISSION_ID --keychain-profile apt-notary apple-log.json
```

官方：[Customizing the notarization workflow](https://developer.apple.com/documentation/security/customizing-the-notarization-workflow)。

## 5. 真人验收与发布

检查 manifest 的 signing.status 为 developer_id_notarized，然后在干净Mac上
通过真实浏览器下载候选、正常拖装并打开；不清 quarantine，测试视频、AI环境、
训练/推理与重开。公证并不证明这些功能正常，必须保留对应 HR。
未获得用户明确“发”，不打tag、不创建GitHub Release。Windows仍暂未实机验证。
