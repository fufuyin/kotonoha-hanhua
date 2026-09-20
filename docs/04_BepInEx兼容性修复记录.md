# BepInEx 兼容性修复记录（本作专用）

> 结论：BepInEx 5.4.23 在本作**无法开箱可用**，原因是它自身的 Harmony 运行时修复与本作的 Mono 不兼容；
> 已用外科式 IL 补丁修复，**不需要改动游戏任何资源**。

---

## 一、故障现象链（实测，逐步排除）

| 阶段 | 现象 | 排除结论 |
|---|---|---|
| 1 | 部署后完全没有 BepInEx 日志 | 代理 `winhttp.dll` 是 **x64**，而游戏是 **32 位（i386）** → 换 x86 代理 |
| 2 | 换 x86 后仍无 `LogOutput.log` | 找错日志了：BepInEx 的日志名是 `preloader_<时间戳>.log`（仅异常时写出） |
| 3 | `preloader_*.log` 报错 | `HarmonyException: IL Compile Error` → NRE at `StackTraceFixes.OnILChainRefresh` ← **真正病灶** |
| 4 | 尝试关 `ApplyRuntimePatches` | 绕过 `ConsoleSetOutFix`，但死在 `HarmonyInteropFix`（该调用不受此开关控制） |
| 5 | 怀疑"路径含非 ANSI 字符"（HarmonyX#108） | **被证据推翻**：系统 ANSI = gb2312/cp936，日文路径可无损往返（0 个 `?`） |
| 6 | 根因确认 | 本作 `kotonoha_Data\Managed` 带 `System.Diagnostics.StackTrace.dll`（**Unity mscorlib 被裁剪**的标志）→ HarmonyX 的 `StackTraceFixes` 在裁剪版 corlib 上必抛 NRE |

**关键事实**：这些 Harmony 调用位于预加载器 `try` 块最前面，异常被 catch 后**整个预加载中止**，
永远到不了 `AssemblyPatcher.PatchAndLoad()` → Chainloader 未注入 → 插件不加载。

## 二、修复方式（已实施）

用 BepInEx 自带的 **Mono.Cecil** 对 `BepInEx\core\BepInEx.Preloader.dll` 做外科 IL 补丁，
把 3 处致命 Harmony 调用改成 `nop`：

| 方法 | 偏移 | 被 nop 的调用 |
|---|---|---|
| `PreloaderRunner::PreloaderMain` | IL_000c | `XTermFix::Apply()` |
| `PreloaderRunner::PreloaderMain` | IL_0011 | `ConsoleSetOutFix::Apply()` |
| `Preloader::Run` | IL_0005 | `HarmonyInteropFix::Apply()` |

* 被 nop 的三者功能分别是终端修复、控制台输出重定向、Harmony 互操作垫片 —— **均与"加载插件"无关**，
  且我们的字体插件**不使用 Harmony**，故无副作用。
* 未动 `UnityPatches::Apply()`（它包在 `TryDo` 里，失败只产生警告，不致命）。
* 备份：`BepInEx\core\BepInEx.Preloader.dll.bak`；补丁脚本 `_hanhua/tools/patch_bepinex.ps1`（可重复执行 + `-VerifyOnly` 校验）。

## 三、其他两个环境坑（已解决，打包时需注意）

1. **Mark-of-the-Web**：从网上下载的 DLL 带 `Zone.Identifier`，.NET/PowerShell 会拒绝加载
   （HRESULT `0x80131515`）。已对 72 个文件执行 `Unblock-File`。**发布补丁时应提示用户解除锁定**，
   或在发布版里避免依赖被标记的程序集加载。
2. **PowerShell 5.1 读取无 BOM 的 UTF-8 脚本会按 ANSI 解码**，脚本里出现中文/日文路径字面量会变成乱码并报错。
   → 本目录下所有 `.ps1` 一律**纯 ASCII**，路径通过 `$PSScriptRoot` 推导。

## 四、打包补丁时需要一并分发的内容

```
kotonoha\
├─ winhttp.dll                        # 32 位 Doorstop 代理（必须 x86！）
├─ doorstop_config.ini
├─ .doorstop_version
├─ steam_appid.txt                    # 内容: 1569180（从非 Steam 路径直接启动时需要）
├─ BepInEx\
│  ├─ core\*                          # 含打过补丁的 BepInEx.Preloader.dll
│  ├─ config\BepInEx.cfg              # ApplyRuntimePatches = false
│  └─ plugins\KotonohaCNFont.dll      # 自研中文 TMP 字体回退插件
└─ kotonoha_Data\...                  # 中文文本资源（前作者的补丁内容）
```

> 注意：**不使用 XUnity.AutoTranslator**——它的自动翻译会覆盖已翻译好的中文文本。
