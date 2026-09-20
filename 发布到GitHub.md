# 发布到 GitHub —— 操作指南

本地仓库已就绪：`D:\桌面\kotonoha-hanhua`（分支 `main`，110 个跟踪文件，工作区干净）。
**只剩两步需要你手动做**：建远程仓库并 push；发 Release 上传两个补丁包。

---

## 第 1 步：在 GitHub 上建空仓库

网页 → New repository →
* Repository name：`kotonoha-hanhua`
* 可见性：Public（或 Private，随你）
* **不要**勾选 Add a README / .gitignore / license（本地已有内容，勾了会产生冲突）

---

## 第 2 步：push（两种凭据方式，二选一）

### 方式 A：SSH（本机推荐，已实测 `github.com:22` 可连）

```powershell
Start-Service ssh-agent          # 若报"已禁用"，需在服务里把启动类型改成手动/自动
ssh-add "$env:USERPROFILE\.ssh\id_ed25519"   # 输入一次私钥口令
cd D:\桌面\kotonoha-hanhua
git remote add origin git@github.com:fufuyin/kotonoha-hanhua.git
git push -u origin main
```

### 方式 B：HTTPS + 个人访问令牌（PAT）

在 GitHub → Settings → Developer settings → Tokens 生成一个带 `repo` 权限的 PAT，然后：

```powershell
cd D:\桌面\kotonoha-hanhua
git remote add origin https://github.com/fufuyin/kotonoha-hanhua.git
git push -u origin main
# 用户名填 fufuyin，密码位置粘贴 PAT
```

> ⚠ **务必在你自己的 PowerShell 窗口里执行**。在 DSH 沙箱内执行时，git 的凭据提示脚本会因为
> MSYS 无法创建信号管道而报 `couldn't create signal pipe, Win32 error 5`（这是沙箱边界，不是命令写错）。

---

## 第 3 步：发 Release（上传两个补丁包）

补丁包已放在 `D:\桌面\kotonoha-hanhua\dist\`，且已被 `.gitignore` 挡住、**不会进入 git 仓库**：

| 文件 | 体积 |
|---|---|
| `汉化补丁_完整版_含BepInEx.zip` | 109,302,912 B（≈104 MB） |
| `汉化补丁_纯静态版_无BepInEx.zip` | 90,409,920 B（≈86 MB） |

GitHub 单文件上限 100 MB，**所以只能走 Release**（Release 资产上限 2 GB）：

1. 仓库页 → 右侧 **Releases** → **Draft a new release**
2. Tag：`v1.0.0`（Create new tag on publish）
3. Title：`琴葉姉妹とライサント島の伝説 简体中文汉化 v1.0`
4. 把 `dist\` 下两个 zip 拖进附件区
5. 正文粘贴下面草稿 → **Publish release**

### Release 正文草稿

```markdown
《琴葉姉妹とライサント島の伝説》简体中文汉化 v1.0

在原有补丁 alpha1.2 基础上重做字库，修掉口口口、描边与行距问题。

## 下载
- **完整版（含 BepInEx，推荐）**：`汉化补丁_完整版_含BepInEx.zip`
- **纯静态版（无 BepInEx，零依赖）**：`汉化补丁_纯静态版_无BepInEx.zip`

## 安装
1. 先备份 `kotonoha_Data` 目录（安装脚本也会自动备份）
2. 解压到游戏根目录（`kotonoha.exe` 所在目录），覆盖同名文件
3. 运行游戏

## 本次做了什么
- 5 个 TMP 字体全部替换为中文可用字库（主字体 SimHei 黑体，补齐 Noto Sans CJK SC）
- 材质与图集配对沿用原补丁，描边/颜色不变
- 图集内联，不再需要 900 MB 的 .resS
- BepInEx 插件负责短标签不折行、自动缩字与布局诊断（可关，关了中文照样正常）

## 回滚
- 只停插件：`powershell -File toggle_plugin.ps1 -Off`
- 回滚资产：`powershell -File install_assetfix.ps1 -Uninstall`
- 安装包内带 `_cn_backup_<时间戳>\rollback.ps1`

## 已知问题
- 道具名「薄荷巧克力色的翅膀」显示为两行（不影响可读性）

## 声明
非官方汉化，仅供学习交流；游戏版权归 DeskClub 所有，请支持正版。
**基础补丁 alpha1.2 由原补丁作者制作** ← 发布前请在此补上署名与出处。
```

---

## 收尾自检

```powershell
cd D:\桌面\kotonoha-hanhua
git log --oneline          # 应有 2 个提交
git status --short         # 应为空
git remote -v              # 应指向你的仓库
git ls-files | Measure-Object -Line   # 112 个跟踪文件
```
