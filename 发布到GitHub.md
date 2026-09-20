# 发布到 GitHub —— 操作指南

本地仓库：`D:\桌面\kotonoha-hanhua`（分支 `main`）
远端：https://github.com/fufuyin/kotonoha-hanhua

| 步骤 | 状态 |
|---|---|
| 本地整理 + 提交 | ✅ 已完成 |
| 建远程仓库 | ✅ 已完成 |
| `git push`（3 个提交） | ✅ 已完成 |
| **发 Release（上传补丁包）** | ⬜ **就差这步** |

---

## 一、为什么网页传不上去（25 MB 限制）

| 通道 | 单文件上限 | 说明 |
|---|---|---|
| **网页界面拖拽上传** | **25 MiB** | 你遇到的限制就在这 → 104 MB / 86 MB 必然被拒 |
| **Releases API / git** | **2 GB** | 走接口上传就没这个问题 |
| git 仓库单文件 | 100 MiB | 所以补丁包本来也不该进 git（已被 `.gitignore` 排除） |

来源：[GitHub 大文件限制说明](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)、
[实测讨论：150MB 文件走网页报 max 25MB](https://github.com/orgs/community/discussions/146417)。

---

## 二、用脚本一键发（推荐）

脚本已放在 `tools\publish-release.ps1`，它会：**自动取凭据 → 建草稿 Release → 上传两个包 → 转正式 → 校验远端大小**。

**在你自己的 PowerShell 窗口里执行**（不要在 DSH 里，沙箱取凭据必失败）：

```powershell
cd D:\桌面\kotonoha-hanhua

# 先空跑一次，确认文件和正文都对（不联网）
powershell -ExecutionPolicy Bypass -File tools\publish-release.ps1 -DryRun

# 正式发布
powershell -ExecutionPolicy Bypass -File tools\publish-release.ps1
```

**关于凭据**（脚本按顺序自动尝试，一般不用你管）：

1. `-Token` 参数 → 2. 环境变量 `GITHUB_TOKEN` → 3. **Git Credential Manager 里已存的凭据**
   （就是你 `git push` 成功时用的那个）→ 4. 都没有才会提示你手动粘贴 PAT（输入隐藏）。

如果第 3 步弹出了登录窗口，登录一次即可。想改用 PAT：

```powershell
powershell -ExecutionPolicy Bypass -File tools\publish-release.ps1 -Token ghp_你的令牌
```

> 脚本细节：Release 正文从仓库根目录的 `RELEASE_NOTES.md` 读取（首行 `# ...` 会当作标题）；
> 正文以 **UTF-8 字节**发送，避免中文变乱码；先建**草稿**再上传，最后才转正式 —— 中途失败不会让访客看到半个包。

---

## 三、备选方案

### 方案 B：装 `gh` 命令行（官方工具，同样绕过 25MB）

```powershell
winget install --id GitHub.cli
gh auth login
cd D:\桌面\kotonoha-hanhua
gh release create v1.0.0 dist\*.zip --title "琴葉姉妹とライサント島の伝説 简体中文汉化 v1.0" --notes-file RELEASE_NOTES.md
```

### 方案 C：分卷压缩后走网页上传（不需要任何凭据）

把每个包切成 <25 MB 的分卷，逐个拖到 Release 附件区即可：

```powershell
cd D:\桌面\kotonoha-hanhua
tar -a -c -f dist\完整版.zip dist\汉化补丁_完整版_含BepInEx.zip   # 仅为演示，实际用下面的分卷命令
# 推荐用 7-Zip 命令行分卷（体积可调）：
# & "C:\Program Files\7-Zip\7z.exe" a -v24m dist\完整版_分卷.zip dist\汉化补丁_完整版_含BepInEx.zip
```

缺点：下载方要自己合并分卷，不如方案 A 干净。

### 方案 D：补丁放网盘，Release 里只放说明 + 链接

仓库里只留代码与文档，补丁走你原来的渠道（蓝奏云 / 123 盘等），Release 正文贴下载链接。

---

## 四、让仓库主页更好看（网页上顺手设一下）

进入仓库页 → 右上 **⚙ About**：

* **Description**（建议照抄）：
  `《琴葉姉妹とライサント島の伝説》简体中文汉化｜TMP 字库重烤 + 资产级写回，含完整技术记录`
* **Topics**（逐个添加）：
  `unity` `textmeshpro` `localization` `chinese-translation` `hanhua` `bepinex` `reverse-engineering` `asset-bundle`
* ☑ Releases、☑ Packages（把 Releases 显示在侧栏）

---

## 五、收尾自检

```powershell
cd D:\桌面\kotonoha-hanhua
git status -sb                 # 应为 ## main...origin/main，无未提交改动
git log --oneline              # 应有 4 个提交
```

发完 Release 后，打开 `https://github.com/fufuyin/kotonoha-hanhua/releases` 确认：
两个附件都在、大小与 `dist\` 下一致（脚本会自动核对并打印 `SUCCESS`）。
